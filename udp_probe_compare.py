#!/usr/bin/env python3
"""WWZ Switch UDP:50000 probe comparison, local test network only.

PASSIVE by default. With --echo-38, reflect ONLY 38-byte datagrams from
192.168.137.0/24 or 127.0.0.0/8 to the same sender. Never echo to the
public Internet. It is an experiment, not a WWZ server or protocol decoder.

No payloads, source IPs, source ports, credentials, hashes, or arbitrary
content are printed or saved. Packet SHA256 digests are kept only in RAM
to count how many different datagrams arrived, never emitted.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import ipaddress
import json
import socket
import time

LAB_SUBNET = ipaddress.ip_network("192.168.137.0/24")
LOOPBACK = ipaddress.ip_network("127.0.0.0/8")
MAX_PACKET = 65535


def echo_eligible(payload: bytes, source_ip: str) -> bool:
    """Strictly local controlled test: avoid accidentally reflecting public UDP."""
    try:
        addr = ipaddress.ip_address(source_ip)
    except ValueError:
        return False
    return len(payload) == 38 and addr.version == 4 and (
        addr in LAB_SUBNET or addr in LOOPBACK
    )


def record_packet(state, payload: bytes, source):
    """Maintain aggregate-only stats. No bytes or peer addresses in output."""
    state["packets"] += 1
    state["sizes"][len(payload)] += 1
    state["digests"][hashlib.sha256(payload).digest()] += 1
    state["source_sockets"].add(source)
    return state


def printable_summary(state):
    """Return only aggregate statistics, without any private packet identifiers."""
    size_counts = state["sizes"]
    return {
        "packets_received": state["packets"],
        "unique_payloads": len(state["digests"]),
        "repeated_payload_groups": sorted(
            (count for count in state["digests"].values() if count > 1),
            reverse=True,
        )[:20],
        "size_counts": {str(size): count for size, count in sorted(size_counts.items())},
        "source_sockets": len(state["source_sockets"]),
        "reflected": state["reflected"],
        "reflection_failures": state["reflection_failures"],
        "reflection_skipped": state["reflection_skipped"],
        "first_to_last_packet_ms": (
            round(1000 * (state["last_at"] - state["first_at"]))
            if state["first_at"] is not None else None
        ),
        "note": (
            "38-byte packets and exact repetitions are observed facts only; "
            "no 14-endpoint mapping or handshake response is proven. "
            "Echo is a control experiment, not valid game protocol handling."
        ),
    }


def monitor(host="0.0.0.0", port=50000, echo_38=False, timeout=90,
            packet_limit=0, verbose=False, ready=None):
    if not 1 <= port <= 65535 or timeout < 0 or packet_limit < 0:
        raise ValueError("invalid listener options")
    state = {
        "packets": 0,
        "sizes": Counter(),
        "digests": Counter(),
        "source_sockets": set(),
        "reflected": 0,
        "reflection_failures": 0,
        "reflection_skipped": 0,
        "first_at": None,
        "last_at": None,
    }
    started = time.monotonic()
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind((host, port))
        sock.settimeout(.25)
        print("UDP listener port=%s mode=%s; no payloads or addresses logged" %
              (port, "echo-38-private-lab-only" if echo_38 else "passive"), flush=True)
        if ready is not None:
            ready.set()
        try:
            while True:
                if timeout and time.monotonic() - started >= timeout:
                    break
                if packet_limit and state["packets"] >= packet_limit:
                    break
                try:
                    payload, sender = sock.recvfrom(MAX_PACKET)
                except socket.timeout:
                    continue
                now = time.monotonic()
                if state["first_at"] is None:
                    state["first_at"] = now
                state["last_at"] = now
                record_packet(state, payload, sender)
                if echo_38:
                    if echo_eligible(payload, sender[0]):
                        try:
                            sock.sendto(payload, sender)
                            state["reflected"] += 1
                        except OSError:
                            state["reflection_failures"] += 1
                    else:
                        state["reflection_skipped"] += 1
                if verbose:
                    print("UDP packet count=%d bytes=%d" %
                          (state["packets"], len(payload)), flush=True)
        except KeyboardInterrupt:
            pass
    summary = printable_summary(state)
    print(json.dumps(summary, indent=2), flush=True)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=50000)
    parser.add_argument("--echo-38", action="store_true",
                        help="reflect exactly 38-byte packets, ONLY to local ICS/loopback senders")
    parser.add_argument("--timeout", type=int, default=90,
                        help="number of seconds before summary (0 until Ctrl+C)")
    parser.add_argument("--count", type=int, default=0,
                        help="max packets before summary (0 unlimited)")
    parser.add_argument("--verbose", action="store_true",
                        help="show each packet length (never packet data)")
    a = parser.parse_args()
    monitor(a.host, a.port, a.echo_38, a.timeout, a.count, a.verbose)


if __name__ == "__main__":
    main()
