#!/usr/bin/env python3
"""Opt-in success-only responder for the five observed presence RPC paths.

This experiment changes only responses for paths seen in the nine-entry
heartbeat remote test. It does NOT claim to implement their real methods.
The experimental response is bare ServiceResult(retCode=Success), hex 0800.
No packet bodies or credentials are stored.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

PRESENCE_SERVICE = "b89429154e224660837a4a307391b0b4"
# Four paths new in Oct 23 remote log, plus the pre-existing empty-body path.
OBSERVED_METHODS = (
    "44106e2a072d4667999b814b3207e195",  # 4-byte requests
    "feda55b07bcf4b94b2e065a7f380d5be",  # 2-byte requests
    "2896c4aa256e4e7290454ef6df3f1ce9",  # 2-byte requests
    "b96449cd66864ace861786c011fdaf48",  # empty requests
    "2299e0e7d40548838e89bba0268ed3b2",  # empty requests, known earlier
)
RESPONSE = {"response_hex": "0800"}
EXPECTED_ROUTE_NAMES = tuple(f"{PRESENCE_SERVICE}.svc/{method}" for method in OBSERVED_METHODS)


def add_probe_routes(config: dict) -> dict:
    if not isinstance(config, dict):
        raise ValueError("route file must contain an object")
    result = {}
    for key, value in config.items():
        if not isinstance(key, str) or not isinstance(value, dict):
            raise ValueError("route entries must be JSON objects")
        result[key] = dict(value)
    for route in EXPECTED_ROUTE_NAMES:
        existing = result.get(route)
        if existing is None:
            result[route] = dict(RESPONSE)
        elif existing != RESPONSE:
            raise ValueError("refusing to overwrite existing route: " + route)
    return result


def update_local_route(path: Path) -> int:
    if not path.is_file():
        raise FileNotFoundError(path)
    original = json.loads(path.read_text(encoding="utf-8"))
    updated = add_probe_routes(original)
    new_count = len(updated) - len(original)
    # Validation complete before any write. Preserve the local endpoint IPs.
    path.write_text(json.dumps(updated, indent=2) + "\n", encoding="utf-8")
    return new_count


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("routes", type=Path, help="existing local route configuration")
    args = ap.parse_args()
    count = update_local_route(args.routes)
    print(f"Presence 200-success experiment ready ({count} new routes; 5 observed paths total).")
    print("Unrelated routes, heartbeat version counts and advertised IPs preserved.")
    print("This is NOT a complete presence implementation; no typed response data.")


if __name__ == "__main__":
    main()
