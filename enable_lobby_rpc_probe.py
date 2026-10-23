#!/usr/bin/env python3
"""Opt-in lobby RPC A/B: bare success on exact observed presence methods.

This is deliberately a test of HTTP 404 versus syntactically valid
ServiceResult(Success), NOT a working lobby, squad or matchmaking service.
It does not change heartbeat, authentication, public IPs or typed status RPCs.
No game packets, user data or tokens are logged or saved.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import tempfile

PRESENCE_SERVICE = "b89429154e224660837a4a307391b0b4"
BARE = {"response_hex": "0800"}
# Each is present in the two-console Oct 23 remote trace, with HTTP 404.
# "candidate" names are inferred from descriptor shape, not verified GUID xrefs.
TARGETS = {
    "b2a1ab68eb464d7796c4e9f49247d3c8": "set_property_candidate",
    "5df1122df8884a408c2b804153dc90f1": "squad_settings_candidate",
    "44a718e4c7514684b5259e0879e98c63": "squad_game_data_candidate",
    "dfd72da619924665a51e16f74e813f13": "squad_invites_state_candidate",
    "67cdaf75ca604bd993ad9f1db0c3f812": "matchmake_start_high_confidence",
    "f9dcd75c457145e7a8b4d5e619171fc1": "matchmake_stop_candidate",
    "b2ba5509c32e43f09b39cb0a828059df": "state_toggle_candidate",
}
ROUTES = tuple(f"{PRESENCE_SERVICE}.svc/{method}" for method in TARGETS)


def with_probe_routes(config: dict, undo: bool = False) -> dict:
    if not isinstance(config, dict):
        raise ValueError("routes must be JSON object")
    result = {}
    for name, value in config.items():
        if not isinstance(name, str) or not isinstance(value, dict):
            raise ValueError("malformed route entry")
        result[name] = dict(value)
    for route in ROUTES:
        if undo:
            if route not in result:
                continue
            if result[route] != BARE:
                raise ValueError("will not remove a customized route: " + route)
            del result[route]
        else:
            if route in result and result[route] != BARE:
                raise ValueError("will not replace a customized route: " + route)
            result[route] = dict(BARE)
    return result


def update_file(path: Path, undo: bool = False) -> int:
    raw = path.read_text(encoding="utf-8")
    original = json.loads(raw)
    changed = with_probe_routes(original, undo=undo)
    modifications = sum(original.get(p) != changed.get(p) for p in ROUTES)
    # Atomic write and preserve existing file permissions. Keep private
    # endpoint values local and never echo the contents to the console.
    fd, name = tempfile.mkstemp(prefix=".wwz-lobby-", dir=path.parent)
    try:
        os.fchmod(fd, path.stat().st_mode & 0o777)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(changed, stream, indent=2)
            stream.write("\n")
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)
    return modifications


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("routes", type=Path)
    ap.add_argument("--undo", action="store_true")
    args = ap.parse_args()
    n = update_file(args.routes, args.undo)
    print(f"Lobby A/B {'disabled' if args.undo else 'enabled'} ({n} routes changed, {len(ROUTES)} in test).")
    print("This does not implement lobby state or identify users; only replaces HTTP 404 with 0800.")


if __name__ == "__main__":
    main()
