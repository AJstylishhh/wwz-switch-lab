#!/usr/bin/env python3
"""
WWZ Switch lab listener — TCP 11702 / 11704 byte logger.
Not a game server. Accepts connections and logs raw traffic for protocol research.
"""

from __future__ import annotations

import argparse
import socket
import socketserver
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent / "logs"


def ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def hexdump(data: bytes, width: int = 16) -> str:
    lines = []
    for i in range(0, len(data), width):
        chunk = data[i : i + width]
        hexpart = " ".join(f"{b:02x}" for b in chunk)
        asciipart = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        lines.append(f"  {i:04x}  {hexpart:<{width * 3}}  {asciipart}")
    return "\n".join(lines)


def classify_first_bytes(data: bytes) -> str:
    if not data:
        return "empty"
    if data[0] == 0x16 and len(data) > 1 and data[1] == 0x03:
        return "likely TLS record (handshake/app data)"
    if data[:3] == b"\x16\x03\x01" or data[:3] == b"\x16\x03\x03":
        return "likely TLS ClientHello/record"
    if data[:4] == b"HTTP" or data.startswith(b"GET ") or data.startswith(b"POST "):
        return "HTTP plaintext"
    if data[0] in (0x00, 0x01, 0x02) and len(data) >= 4:
        return "possible length-prefixed binary"
    return "unknown binary"


class LabHandler(socketserver.BaseRequestHandler):
    port: int = 0

    def handle(self) -> None:
        peer = self.client_address[0]
        port = self.server.server_address[1]
        conn_id = f"{port}_{int(time.time())}_{peer.replace('.', '_')}"
        print(f"\n[{ts()}] [{port}] CONNECT from {peer}:{self.client_address[1]} id={conn_id}")
        sys.stdout.flush()

        LOG_DIR.mkdir(parents=True, exist_ok=True)
        log_path = LOG_DIR / f"{conn_id}.log"
        bin_path = LOG_DIR / f"{conn_id}.bin"

        self.request.settimeout(120.0)
        total = 0
        first = True

        with log_path.open("a", encoding="utf-8") as logf, bin_path.open("ab") as binf:
            logf.write(f"# peer={peer} server_port={port} start={ts()}\n")
            try:
                while True:
                    try:
                        data = self.request.recv(65535)
                    except socket.timeout:
                        print(f"[{ts()}] [{port}] timeout waiting data from {peer} (total={total} bytes)")
                        break
                    if not data:
                        print(f"[{ts()}] [{port}] peer closed {peer} (total={total} bytes)")
                        break

                    total += len(data)
                    binf.write(data)
                    binf.flush()

                    kind = classify_first_bytes(data) if first else ""
                    header = f"[{ts()}] [{port}] +{len(data)} bytes from {peer} (total={total})"
                    if first:
                        header += f"  guess={kind}"
                        first = False
                    print(header)
                    print(hexdump(data[:512]))
                    if len(data) > 512:
                        print(f"  … ({len(data) - 512} more bytes not shown)")
                    sys.stdout.flush()

                    logf.write(header + "\n")
                    logf.write(hexdump(data) + "\n")
                    logf.flush()

                    # Lab only: do not pretend to be a real server.
                    # Optional tiny ACK probe disabled by default.
            except ConnectionResetError:
                print(f"[{ts()}] [{port}] reset by {peer} (total={total} bytes)")
            except OSError as e:
                print(f"[{ts()}] [{port}] error {peer}: {e}")

        print(f"[{ts()}] [{port}] done {peer} total={total} -> {log_path.name}")
        sys.stdout.flush()


class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


def serve_port(host: str, port: int) -> None:
    with ThreadedTCPServer((host, port), LabHandler) as srv:
        print(f"[WWZ Lab] listening TCP {host}:{port}")
        sys.stdout.flush()
        srv.serve_forever()


def main() -> None:
    ap = argparse.ArgumentParser(description="WWZ Switch lab TCP logger (11702/11704)")
    ap.add_argument("--host", default="0.0.0.0", help="bind address (default 0.0.0.0)")
    ap.add_argument(
        "--ports",
        default="11702,11704",
        help="comma-separated TCP ports (default 11702,11704)",
    )
    args = ap.parse_args()
    ports = [int(p.strip()) for p in args.ports.split(",") if p.strip()]

    print("[WWZ Lab] World War Z Switch — byte logger (not a game server)")
    print(f"[WWZ Lab] logs -> {LOG_DIR}")
    print("[WWZ Lab] waiting for Switch…")
    sys.stdout.flush()

    threads = []
    for port in ports:
        t = threading.Thread(target=serve_port, args=(args.host, port), daemon=True)
        t.start()
        threads.append(t)

    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        print("\n[WWZ Lab] stopped")


if __name__ == "__main__":
    main()
