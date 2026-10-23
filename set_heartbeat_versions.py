#!/usr/bin/env python3
"""Edit ONLY the heartbeat UserVersions test count in an existing local JSON.

Never alters endpoint addresses, TLS, provider fields or presence settings.
Works with private routes.remote.local.json (not checked into Git).
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path


HEARTBEATS = ("heartbeat_register", "heartbeat_update")
VERSION = 8802288


def set_version_count(config: dict, count: int) -> dict:
    if type(count) is not int or not 1 <= count <= 20:
        raise ValueError("version count must be 1..20")
    if not isinstance(config, dict):
        raise ValueError("configuration must be a JSON object")
    seen = {name: 0 for name in HEARTBEATS}
    result = {}
    for route, original in config.items():
        if not isinstance(original, dict):
            raise ValueError("route configurations must be objects")
        new = dict(original)
        kind = new.get("handler")
        if kind in seen:
            seen[kind] += 1
            new["heartbeat_version_values"] = [VERSION] * count
        result[route] = new
    if any(times != 1 for times in seen.values()):
        raise ValueError("expected exactly one heartbeat_register and one heartbeat_update route")
    return result


def update_local_route(path: Path, count: int) -> None:
    if not path.is_file():
        raise ValueError("route file not found")
    previous = path.read_text(encoding="utf-8")
    updated = set_version_count(json.loads(previous), count)
    # Only write once all validation succeeds; do not print private endpoint IPs.
    path.write_text(json.dumps(updated, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("routes", type=Path, help="existing local route file")
    parser.add_argument("count", type=int, choices=range(1, 21),
                        metavar="COUNT", help="1..20 UserVersions entries")
    args = parser.parse_args()
    update_local_route(args.routes, args.count)
    print(f"Updated both heartbeat responses: {args.count} version entries each.")
    print("All addresses, ports, provider and presence settings preserved.")


if __name__ == "__main__":
    main()
