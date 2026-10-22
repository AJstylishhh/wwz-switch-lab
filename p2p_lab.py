#!/usr/bin/env python3
"""Two-peer P2P directory and opaque UDP relay laboratory.

NOT World War Z-native: peers must explicitly send our registration packet.
A stock WWZ Switch cannot connect through this until matchmaking gives it
a usable endpoint and the client's connection setup is understood.
Do not expose the cleartext HTTP control interface to the Internet.
"""
from __future__ import annotations
import argparse
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import secrets
import socketserver
import threading

REGISTER = b"WWZ-LAB-REGISTER "
ACK = b"WWZ-LAB-OK"


@dataclass
class Room:
    code: str
    host_token: str
    guest_token: str | None = None
    host_addr: tuple[str, int] | None = None
    guest_addr: tuple[str, int] | None = None


class Directory:
    def __init__(self):
        self.rooms: dict[str, Room] = {}
        self.lock = threading.RLock()

    def create(self):
        with self.lock:
            code = secrets.token_hex(5).upper()
            while code in self.rooms:
                code = secrets.token_hex(5).upper()
            room = Room(code, secrets.token_urlsafe(24))
            self.rooms[code] = room
            return {"room": code, "role": "host", "token": room.host_token}

    def join(self, code: str):
        with self.lock:
            room = self.rooms.get(code.upper())
            if not room:
                raise KeyError("room not found")
            if room.guest_token:
                raise ValueError("room full")
            room.guest_token = secrets.token_urlsafe(24)
            return {"room": room.code, "role": "guest", "token": room.guest_token}

    def _find(self, token):
        for room in self.rooms.values():
            if secrets.compare_digest(token, room.host_token):
                return room, "host"
            if room.guest_token and secrets.compare_digest(token, room.guest_token):
                return room, "guest"
        return None, None

    def status(self, token: str):
        with self.lock:
            room, role = self._find(token)
            if room is None:
                raise KeyError("unknown token")
            return {"room": room.code, "role": role, "has_guest": bool(room.guest_token),
                    "host_ready": room.host_addr is not None,
                    "guest_ready": room.guest_addr is not None}

    def packet(self, data: bytes, source: tuple[str, int]):
        """Return (unchanged bytes, target) or None.

        Our explicit registration format is invented for the lab and
        must NOT be mistaken for WWZ's real UDP connection handshake.
        """
        with self.lock:
            if data.startswith(REGISTER):
                try:
                    token = data[len(REGISTER):].decode("ascii")
                except UnicodeDecodeError:
                    return None
                room, role = self._find(token)
                if not room:
                    return None
                if role == "host":
                    room.host_addr = source
                else:
                    room.guest_addr = source
                return ACK, source
            for room in self.rooms.values():
                if source == room.host_addr and room.guest_addr:
                    return data, room.guest_addr
                if source == room.guest_addr and room.host_addr:
                    return data, room.host_addr
            return None


class UDPServer(socketserver.UDPServer):
    allow_reuse_address = True

    def __init__(self, address, directory):
        self.directory = directory
        super().__init__(address, UDPHandler)


class UDPHandler(socketserver.BaseRequestHandler):
    def handle(self):
        data, sock = self.request
        result = self.server.directory.packet(data, self.client_address)
        if result is not None:
            packet, destination = result
            sock.sendto(packet, destination)


class ControlServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, directory):
        self.directory = directory
        super().__init__(address, HTTPHandler)


class HTTPHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass  # never log room access tokens

    def send_json(self, code, body):
        data = json.dumps(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/healthz":
            return self.send_json(200, {"status": "lab", "native_wwz": False})
        self.send_json(404, {"error": "not found"})

    def do_POST(self):
        if self.path not in ("/lab/create", "/lab/join", "/lab/status"):
            return self.send_json(404, {"error": "not found"})
        size_text = self.headers.get("Content-Length", "")
        if not size_text.isascii() or not size_text.isdecimal():
            self.close_connection = True
            return self.send_json(411, {"error": "Content-Length required"})
        size = int(size_text)
        if size > 4096:
            self.close_connection = True
            return self.send_json(413, {"error": "body too large"})
        try:
            body = json.loads(self.rfile.read(size) or b"{}")
            if not isinstance(body, dict):
                raise ValueError("JSON object required")
            directory = self.server.directory
            if self.path == "/lab/create":
                output = directory.create()
            elif self.path == "/lab/join":
                output = directory.join(str(body["room"]))
            else:
                output = directory.status(str(body["token"]))
            return self.send_json(200, output)
        except KeyError:
            return self.send_json(404, {"error": "not found or invalid token"})
        except (ValueError, TypeError, UnicodeDecodeError):
            return self.send_json(400, {"error": "invalid request or room full"})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--control-port", type=int, default=11705)
    parser.add_argument("--udp-port", type=int, default=50001)
    args = parser.parse_args()
    directory = Directory()
    control = ControlServer((args.host, args.control_port), directory)
    udp = UDPServer((args.host, args.udp_port), directory)
    threads = []
    try:
        for service in (control, udp):
            t = threading.Thread(target=service.serve_forever, daemon=True)
            t.start()
            threads.append(t)
        print(f"P2P lab: HTTP {control.server_address}, UDP {udp.server_address}; NOT game-native")
        threading.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        for service in (control, udp):
            service.shutdown()
            service.server_close()
        for t in threads:
            t.join(timeout=3)


if __name__ == "__main__":
    main()
