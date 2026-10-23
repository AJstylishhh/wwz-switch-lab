#!/usr/bin/env python3
"""WWZ Switch UDP:50000 observation-only probe.

No packet contents, source addresses, device IDs or credentials are printed.
No packets are relayed or echoed. Does not implement a gameplay server.
Run in another PowerShell window beside experimental TLS mvp_server.py.
"""
from __future__ import annotations

import argparse
import logging
import socket
import time

LOG = logging.getLogger("wwz.udp-probe")


def monitor(host="0.0.0.0", port=50000, packet_limit=0, timeout=0):
    if not 1 <= port <= 65535 or packet_limit < 0 or timeout < 0:
        raise ValueError("invalid listener options")
    source_sockets = {}
    count = 0
    start = time.monotonic()
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as listener:
        listener.bind((host, port))
        listener.settimeout(1.0)
        LOG.info("Listening for WWZ UDP datagrams port=%s (no payloads, no replies)", port)
        while not packet_limit or count < packet_limit:
            if timeout and time.monotonic() - start >= timeout:
                break
            try:
                payload, addr = listener.recvfrom(65535)
            except socket.timeout:
                continue
            if addr not in source_sockets:
                source_sockets[addr] = len(source_sockets) + 1
            count += 1
            LOG.info("UDP datagram source_socket=%s bytes=%s total=%s",
                     source_sockets[addr], len(payload), count)
    LOG.info("UDP probe complete packets=%s distinct_source_sockets=%s",
             count, len(source_sockets))
    return count, len(source_sockets)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=50000)
    p.add_argument("--count", type=int, default=0, help="stop after this many packets (0: unlimited)")
    p.add_argument("--timeout", type=int, default=0, help="stop after N seconds (0: unlimited)")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        monitor(args.host, args.port, args.count, args.timeout)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
