#!/usr/bin/env python3
"""Experimental WWZ TLS/protobuf responder. NOT a playable game server.

Python 3.10+ standard library. The original server.py capture logger is unchanged.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import os
from pathlib import Path
import re
import ssl
import threading
import uuid
from urllib.parse import urlsplit

from wwz_wire import ENVIRONMENT_ROUTE, environment_result, describe_environment_request

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
            if route != ENVIRONMENT_ROUTE or conf["handler"] != "environment_list":
                raise ValueError("unsupported handler")
            data = environment_result(conf["address"], conf["port"], conf["name"],
                                      conf["environment_id"], conf["region"])
        elif "response_hex" in conf:
            data = bytes.fromhex(conf["response_hex"])
        else:
            data = (config_path.parent / conf["response_file"]).read_bytes()
        routes[route] = status, data
    return routes


class App:
    def __init__(self, routes, capture_dir=None, max_body=2_000_000):
        self.routes, self.capture_dir, self.max_body = routes, capture_dir, max_body
        if capture_dir is not None:
            capture_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
            try:
                os.chmod(capture_dir, 0o700)
            except OSError:
                pass


def make_handler(app):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):
            pass  # requests may contain tokens in query strings

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
            LOG.info("POST %s port=%s bytes=%s", path, self.server.server_port, length)
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
                return self.reply(404, b"Invalid RPC path", "text/plain")
            answer = app.routes.get(path)
            if answer is None:
                LOG.warning("Unmapped RPC: %s", path)
                return self.reply(404, b"Unknown RPC", "text/plain")
            self.reply(*answer)
    return Handler


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    def get_request(self):
        sock, addr = super().get_request()
        sock.settimeout(30)
        return sock, addr


def make_server(host, port, app, cert=None, key=None):
    server = Server((host, port), make_handler(app))
    if cert is not None and key is not None:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.set_alpn_protocols(["http/1.1"])
        ctx.load_cert_chain(str(cert), str(key))
        server.socket = ctx.wrap_socket(server.socket, server_side=True)
    return server


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--ports", default="11702,11704")
    ap.add_argument("--routes", type=Path, default=Path(__file__).with_name("routes.mvp.example.json"))
    ap.add_argument("--capture-dir", type=Path, help="stores raw requests, potentially sensitive")
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
    app = App(read_routes(args.routes), args.capture_dir, args.max_body)
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
