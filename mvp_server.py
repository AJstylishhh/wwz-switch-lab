#!/usr/bin/env python3
"""Experimental WWZ TLS/protobuf responder. NOT a playable game server.

Python 3.10+ standard library. The original server.py capture logger is unchanged.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import os
from pathlib import Path
import re
import secrets
import ssl
import threading
import uuid
from urllib.parse import urlsplit

from wwz_wire import ENVIRONMENT_ROUTE, environment_result, describe_environment_request
from queue_state import ENQUEUE_ROUTE, QueueState, inspect_enqueue
from auth_dequeue import DEQUEUE_ROUTE, AuthSessions
from post_login import ROUTES as POST_LOGIN_ROUTES, PostLogin
from request_shape import unknown_request_summary, REDLYNX_ENVIRONMENT

LOG = logging.getLogger("wwz.mvp")
GUID_ROUTE = re.compile(r"^/[0-9a-f]{32}\.svc/[0-9a-f]{32}$", re.I)


def normalize(path):
    return urlsplit(path).path.lower()


def read_routes(config_path: Path):
    if not config_path.is_file():
        raise FileNotFoundError(config_path)
    obj = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise ValueError("routes must be JSON object")
    routes = {}
    for route, conf in obj.items():
        route = normalize("/" + route.lstrip("/"))
        if not GUID_ROUTE.fullmatch(route) or not isinstance(conf, dict):
            raise ValueError("invalid GUID route or config")
        if sum(k in conf for k in ("handler", "response_hex", "response_file")) != 1:
            raise ValueError("choose exactly one response mode")
        status = int(conf.get("status", 200))
        if not 100 <= status <= 599:
            raise ValueError("invalid HTTP status")
        if "handler" in conf:
            if route == ENVIRONMENT_ROUTE and conf["handler"] == "environment_list":
                data = environment_result(conf["address"], conf["port"], conf["name"],
                                          conf["environment_id"], conf["region"],
                                          datacenter_id=conf.get("datacenter_id"),
                                          include_retcode=conf.get("include_retcode", True),
                                          datacenters=conf.get("datacenters"),
                                          date_ms=(int(datetime.now(timezone.utc).timestamp() * 1000)
                                                   if conf.get("date_ms") == "now"
                                                   else conf.get("date_ms")),
                                          include_maintenance_flag=conf.get(
                                              "include_maintenance_flag", True))
            elif route == ENQUEUE_ROUTE and conf["handler"] == "enqueue":
                data = None  # Generate a short-lived queue token for each request.
            elif route == DEQUEUE_ROUTE and conf["handler"] == "dequeue":
                data = {"address": conf["address"], "port": int(conf["port"]), "name": conf["name"],
                        "provider_environment": conf.get("provider_environment")}
                if (not isinstance(data["address"], str) or not data["address"] or
                        not isinstance(data["name"], str) or not data["name"] or
                        not 1 <= data["port"] <= 65535):
                    raise ValueError("invalid Dequeue endpoint")
                if data["provider_environment"] not in (None, "Dev", "Retail"):
                    raise ValueError("invalid provider environment test value")
            elif route in POST_LOGIN_ROUTES and conf["handler"] == POST_LOGIN_ROUTES[route]:
                dc_ids = conf.get("datacenter_ids")
                if dc_ids is not None and (not isinstance(dc_ids, list) or
                        not dc_ids or len(dc_ids) > 16 or
                        any(not isinstance(i, str) or not i for i in dc_ids) or
                        len(set(dc_ids)) != len(dc_ids)):
                    raise ValueError("invalid datacenter_ids in experimental route")
                duration = conf.get("presence_available_seconds", 0)
                if not isinstance(duration, int) or isinstance(duration, bool) or not 0 <= duration <= 3600:
                    raise ValueError("invalid presence_available_seconds")
                if duration and conf["handler"] != "presence_connect":
                    raise ValueError("presence_available_seconds only applies to presence_connect")
                version_values = conf.get("heartbeat_version_values")
                if version_values is not None:
                    if conf["handler"] not in ("heartbeat_register", "heartbeat_update"):
                        raise ValueError("heartbeat_version_values only applies to heartbeat handlers")
                    if (not isinstance(version_values, list) or
                            not 1 <= len(version_values) <= 20 or
                            any(type(x) is not int or not 0 <= x < 2**63 for x in version_values)):
                        raise ValueError("heartbeat_version_values must be 1..20 nonnegative int64 values")
                data = {"post_login_handler": conf["handler"],
                        "datacenter_ids": dc_ids,
                        "presence_available_seconds": duration,
                        "heartbeat_version_values": version_values}
            else:
                raise ValueError("unsupported handler")
        elif "response_hex" in conf:
            data = bytes.fromhex(conf["response_hex"])
        else:
            data = (config_path.parent / conf["response_file"]).read_bytes()
        routes[route] = status, data
    # If an experimental fixture overrides heartbeat versions, both response
    # types must advertise the same list. Partial overrides hide logic errors.
    heartbeat_routes = [route for route, (_, config) in routes.items()
                        if isinstance(config, dict) and
                        config.get("post_login_handler") in ("heartbeat_register", "heartbeat_update")]
    specified = [routes[route][1].get("heartbeat_version_values") for route in heartbeat_routes]
    if any(values is not None for values in specified):
        if len(heartbeat_routes) != 2 or any(values != specified[0] for values in specified):
            raise ValueError("Heartbeat Register and Update must have identical version values")
    return routes


class App:
    def __init__(self, routes, capture_dir=None, max_body=2_000_000,
                 trace_clients=False):
        self.routes, self.capture_dir, self.max_body = routes, capture_dir, max_body
        self.trace_clients = trace_clients
        # Ephemeral random key: labels do not disclose client IPs or token
        # contents, and cannot be linked across server restarts.
        self._trace_key = secrets.token_bytes(32)
        self.queue = QueueState()
        self.auth_sessions = AuthSessions(self.queue)
        self.post_login = PostLogin(self.auth_sessions)
        if capture_dir is not None:
            capture_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
            try:
                os.chmod(capture_dir, 0o700)
            except OSError:
                pass


    def observation_label(self, ip, headers):
        if not self.trace_clients:
            return ""
        def tag(domain, value):
            data = (domain + "\\0" + value).encode("utf-8")
            return hmac.digest(self._trace_key, data, hashlib.sha256)[:6].hex()
        # These are connection-source labels, not verified player identities.
        # Users behind the same NAT may share an address label.
        label = " source_tag=" + tag("ip", ip)
        for name in ("Authorization", "X-Auth-Token", "X-Access-Token",
                     "X-Authorization", "Cookie"):
            secret = headers.get(name)
            if secret:
                # Never print the header value, only keyed ephemeral digest.
                label += " credential_tag=" + tag("credential", name + ":" + secret)
                label += " credential_header=" + name.lower()
                break
        return label


def make_handler(app):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):
            pass  # requests may contain tokens in query strings

        def handle(self):
            # The Switch often closes TLS keep-alive sockets when the game
            # exits. These are normal peer disconnects, not server crashes.
            # Do not conceal malformed protobuf, handler errors, etc.
            try:
                super().handle()
            except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError,
                    ssl.SSLEOFError):
                LOG.debug("Switch closed a keep-alive connection")

        def reply(self, status, data, content_type="application/protobuf"):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if normalize(self.path) == "/healthz":
                return self.reply(200, b'{"status":"experimental"}', "application/json")
            self.reply(404, b"Not found", "text/plain")

        def do_POST(self):
            path = normalize(self.path)
            if self.headers.get("Transfer-Encoding"):
                self.close_connection = True
                return self.reply(501, b"Chunked transfer unsupported", "text/plain")
            length_text = self.headers.get("Content-Length")
            if not length_text or not length_text.isascii() or not length_text.isdecimal():
                self.close_connection = True
                return self.reply(411, b"Content-Length required", "text/plain")
            length = int(length_text)
            if length > app.max_body:
                self.close_connection = True
                return self.reply(413, b"Request too large", "text/plain")
            raw = self.rfile.read(length)
            if len(raw) != length:
                self.close_connection = True
                return
            LOG.info("POST %s port=%s bytes=%s%s", path, self.server.server_port,
                     length, app.observation_label(self.client_address[0], self.headers))
            if path == ENVIRONMENT_ROUTE:
                try:
                    LOG.info("Environment discovery: %s", describe_environment_request(raw))
                except ValueError as exc:
                    LOG.warning("Malformed environment discovery: %s", exc)
            if app.capture_dir is not None:
                filename = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ") + "-" + uuid.uuid4().hex
                (app.capture_dir / (filename + ".bin")).write_bytes(raw)
                (app.capture_dir / (filename + ".json")).write_text(
                    json.dumps({"path": path, "length": length}), encoding="utf-8")
            if not GUID_ROUTE.fullmatch(path):
                # The newly observed RedLynx endpoint on 11701 is not a
                # GUID route. Log shape only; it has no verified response yet.
                if path == REDLYNX_ENVIRONMENT:
                    LOG.info("Unimplemented RedLynx environment request shape: %s",
                             unknown_request_summary(path, raw))
                return self.reply(404, b"Invalid RPC path", "text/plain")
            answer = app.routes.get(path)
            if answer is None:
                summary = unknown_request_summary(path, raw)
                if summary is not None:
                    LOG.info("Unimplemented RPC request shape: %s %s", path, summary)
                LOG.warning("Unmapped RPC: %s", path)
                return self.reply(404, b"Unknown RPC", "text/plain")
            if path == ENQUEUE_ROUTE and answer[1] is None:
                try:
                    metadata = inspect_enqueue(raw)
                    data = app.queue.issue(raw)
                except ValueError as exc:
                    LOG.warning("Enqueue payload rejected: %s", exc)
                    return self.reply(400, b"Invalid Enqueue payload", "text/plain")
                LOG.info("Experimental Enqueue reply: 200 state=ReadyToDequeue %s", metadata)
                return self.reply(answer[0], data)
            if path == DEQUEUE_ROUTE and isinstance(answer[1], dict):
                try:
                    data, info = app.auth_sessions.respond(raw, **answer[1])
                except ValueError as exc:
                    LOG.warning("Dequeue rejected: %s", exc)
                    return self.reply(400, b"Invalid queue token or Dequeue request", "text/plain")
                LOG.info("Experimental Dequeue/SignInResult reply: %s", info)
                return self.reply(answer[0], data)
            if path in POST_LOGIN_ROUTES and isinstance(answer[1], dict):
                try:
                    data, info = app.post_login.respond(
                        path, raw, datacenter_ids=answer[1].get("datacenter_ids"),
                        presence_available_seconds=answer[1].get("presence_available_seconds", 0),
                        heartbeat_version_values=answer[1].get("heartbeat_version_values"))
                except ValueError as exc:
                    LOG.warning("Experimental post-login request rejected on %s: %s", path, exc)
                    return self.reply(400, b"Invalid experimental RPC", "text/plain")
                LOG.info("Experimental post-login reply: %s", info)
                return self.reply(answer[0], data)
            self.reply(*answer)
    return Handler


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    def get_request(self):
        try:
            sock, addr = super().get_request()
        except OSError as exc:
            # SSLSocket.accept() performs the handshake before HTTP handling.
            # Log only local listener and error class: not client IP or tokens.
            LOG.warning("TCP/TLS accept failed port=%s error_type=%s",
                        self.server_port, type(exc).__name__)
            raise
        sock.settimeout(30)
        if isinstance(sock, ssl.SSLSocket):
            LOG.info("TLS handshake OK port=%s protocol=%s alpn=%s",
                     self.server_port, sock.version(), sock.selected_alpn_protocol())
        else:
            LOG.info("TCP accepted port=%s TLS=False", self.server_port)
        return sock, addr


def make_server(host, port, app, cert=None, key=None):
    server = Server((host, port), make_handler(app))
    if cert is not None and key is not None:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.set_alpn_protocols(["http/1.1"])
        ctx.load_cert_chain(str(cert), str(key))
        # SNI presence is useful when comparing main versus research, but
        # hostname strings could contain private or attacker-controlled data.
        def sni_seen(sock, requested_name, ssl_context):
            LOG.info("TLS SNI port=%s present=%s",
                     port, requested_name is not None)
        ctx.set_servername_callback(sni_seen)
        server.socket = ctx.wrap_socket(server.socket, server_side=True)
    return server


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--ports", default="11702,11704")
    ap.add_argument("--routes", type=Path, default=Path(__file__).with_name("routes.mvp.example.json"))
    ap.add_argument("--capture-dir", type=Path, help="stores raw requests, potentially sensitive")
    ap.add_argument("--trace-clients", action="store_true",
                    help="log ephemeral HMAC tags for source IP / known auth headers; never values")
    ap.add_argument("--cert", type=Path, default=Path(__file__).parent / "certs" / "server.crt")
    ap.add_argument("--key", type=Path, default=Path(__file__).parent / "certs" / "server.key")
    ap.add_argument("--max-body", type=int, default=2_000_000)
    ap.add_argument("--no-tls", action="store_true", help="local testing ONLY")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if args.max_body < 1:
        ap.error("--max-body must be positive")
    if not args.no_tls and not (args.cert.is_file() and args.key.is_file()):
        ap.error("Missing test TLS certificate/key; run gen_certs.ps1")
    ports = [int(v) for v in args.ports.split(",")]
    if not ports or len(set(ports)) != len(ports):
        ap.error("ports must be distinct")
    app = App(read_routes(args.routes), args.capture_dir, args.max_body,
              trace_clients=args.trace_clients)
    servers = []
    try:
        for port in ports:
            server = make_server(args.host, port, app, None if args.no_tls else args.cert,
                                 None if args.no_tls else args.key)
            servers.append(server)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            LOG.info("Listening %s:%s TLS=%s", args.host, port, not args.no_tls)
        threading.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        for server in servers:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    main()
