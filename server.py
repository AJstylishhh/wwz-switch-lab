#!/usr/bin/env python3
"""
WWZ Switch lab — TLS terminator + byte/HTTP logger on TCP 11702 / 11704.
Not a game server. Completes TLS with a lab cert so we can see decrypted data.
"""

from __future__ import annotations

import argparse
import socket
import ssl
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LOG_DIR = ROOT / "logs"
CERT_FILE = ROOT / "certs" / "server.crt"
KEY_FILE = ROOT / "certs" / "server.key"


def ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def hexdump(data: bytes, width: int = 16, limit: int = 1024) -> str:
    data = data[:limit]
    lines = []
    for i in range(0, len(data), width):
        chunk = data[i : i + width]
        hexpart = " ".join(f"{b:02x}" for b in chunk)
        asciipart = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        lines.append(f"  {i:04x}  {hexpart:<{width * 3}}  {asciipart}")
    return "\n".join(lines)


def make_ssl_context() -> ssl.SSLContext:
    if not CERT_FILE.is_file() or not KEY_FILE.is_file():
        print("[WWZ Lab] ERROR: missing certs/server.crt or certs/server.key")
        print("[WWZ Lab] Run once:  .\\gen_certs.ps1")
        sys.exit(1)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    # Lab only — accept a wide range of client TLS versions
    try:
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    except Exception:
        pass
    ctx.load_cert_chain(str(CERT_FILE), str(KEY_FILE))
    # Client offered http/1.1 and h2; only claim http/1.1 so we can read plain requests
    try:
        ctx.set_alpn_protocols(["http/1.1"])
    except Exception:
        pass
    return ctx


def handle_client(conn: socket.socket, addr, port: int, ssl_ctx: ssl.SSLContext) -> None:
    peer = addr[0]
    conn_id = f"{port}_{int(time.time())}_{peer.replace('.', '_')}"
    print(f"\n[{ts()}] [{port}] TCP CONNECT from {peer}:{addr[1]} id={conn_id}")
    sys.stdout.flush()

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"{conn_id}.log"
    bin_path = LOG_DIR / f"{conn_id}.bin"

    ssock = None
    try:
        conn.settimeout(30.0)
        ssock = ssl_ctx.wrap_socket(conn, server_side=True)
        alpn = None
        try:
            alpn = ssock.selected_alpn_protocol()
        except Exception:
            pass
        print(f"[{ts()}] [{port}] TLS OK peer={peer} alpn={alpn!r} version={ssock.version()}")
        sys.stdout.flush()

        total = 0
        with log_path.open("a", encoding="utf-8") as logf, bin_path.open("ab") as binf:
            logf.write(f"# peer={peer} port={port} alpn={alpn} tls={ssock.version()} start={ts()}\n")
            while True:
                try:
                    data = ssock.recv(65535)
                except socket.timeout:
                    print(f"[{ts()}] [{port}] recv timeout (total={total})")
                    break
                except ssl.SSLError as e:
                    print(f"[{ts()}] [{port}] SSL error after handshake: {e}")
                    break
                if not data:
                    print(f"[{ts()}] [{port}] peer closed (total={total} bytes)")
                    break

                total += len(data)
                binf.write(data)
                binf.flush()

                # Try show as text if it looks like HTTP
                text_hint = ""
                try:
                    if data.startswith((b"GET ", b"POST ", b"PUT ", b"HEAD ", b"OPTIONS", b"HTTP/")):
                        text_hint = data.decode("utf-8", errors="replace").split("\r\n\r\n", 1)[0]
                except Exception:
                    pass

                header = f"[{ts()}] [{port}] +{len(data)} bytes decrypted (total={total})"
                print(header)
                if text_hint:
                    print("--- HTTP head ---")
                    print(text_hint[:2000])
                    print("-----------------")
                print(hexdump(data))
                sys.stdout.flush()

                logf.write(header + "\n")
                if text_hint:
                    logf.write(text_hint + "\n")
                logf.write(hexdump(data, limit=65535) + "\n")
                logf.flush()

                # Lab: no real API responses yet (empty reply keeps session for logging only)

        print(f"[{ts()}] [{port}] done {peer} total={total} -> {log_path.name}")
    except ssl.SSLError as e:
        print(f"[{ts()}] [{port}] TLS handshake FAILED from {peer}: {e}")
        print("[WWZ Lab] If this keeps failing, the Switch may pin the real Saber certificate.")
        sys.stdout.flush()
        with (LOG_DIR / f"{conn_id}_tls_fail.txt").open("a", encoding="utf-8") as f:
            f.write(f"{ts()} {peer} {e}\n")
    except OSError as e:
        print(f"[{ts()}] [{port}] socket error {peer}: {e}")
        sys.stdout.flush()
    finally:
        try:
            if ssock is not None:
                ssock.close()
            else:
                conn.close()
        except Exception:
            pass
        sys.stdout.flush()


def serve_port(host: str, port: int, ssl_ctx: ssl.SSLContext) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, port))
    sock.listen(50)
    print(f"[WWZ Lab] TLS listening {host}:{port}")
    sys.stdout.flush()
    while True:
        conn, addr = sock.accept()
        t = threading.Thread(
            target=handle_client, args=(conn, addr, port, ssl_ctx), daemon=True
        )
        t.start()


def main() -> None:
    ap = argparse.ArgumentParser(description="WWZ Switch TLS lab logger")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--ports", default="11702,11704")
    args = ap.parse_args()
    ports = [int(p.strip()) for p in args.ports.split(",") if p.strip()]

    print("[WWZ Lab] World War Z Switch — TLS terminator + logger")
    print(f"[WWZ Lab] cert={CERT_FILE}")
    print(f"[WWZ Lab] logs -> {LOG_DIR}")
    ssl_ctx = make_ssl_context()
    print("[WWZ Lab] waiting for Switch…")
    sys.stdout.flush()

    for port in ports:
        t = threading.Thread(target=serve_port, args=(args.host, port, ssl_ctx), daemon=True)
        t.start()

    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        print("\n[WWZ Lab] stopped")


if __name__ == "__main__":
    main()
