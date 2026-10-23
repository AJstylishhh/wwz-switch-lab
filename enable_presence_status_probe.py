#!/usr/bin/env python3
"""Opt-in typed PresenceStatusResponse A/B test after the nine-version breakthrough.

Three recurrent RPC methods are *candidate* GetStatusSquad, GetStatusMatchmake,
and GetStatusUser, inferred ONLY from request sizes + protobuf field counts:
4, 2 and 0 bytes. The GUID-to-name mapping is NOT independently proven.
This test changes no authentication, heartbeat, token, or network code.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from wwz_wire import blob, scalar

SERVICE = "b89429154e224660837a4a307391b0b4"
TYPE_FIELD = 334914069  # ServiceResult_PresenceStatusResponse
BARE_SUCCESS = "0800"
# Only three regularly polled method GUIDs, all already observed on Switch.
METHOD_CANDIDATES = {
    "44106e2a072d4667999b814b3207e195": "squad",      # 4 bytes, two sequence IDs?
    "2896c4aa256e4e7290454ef6df3f1ce9": "matchmake", # 2 bytes, one sequence ID?
    "b96449cd66864ace861786c011fdaf48": "user",       # 0 bytes, no request fields?
}


def presence_status_reply(kind: str) -> bytes:
    """Descriptor-grounded protobuf shape; values are an experimental guess.

    ServiceResult [retCode=Success, typed extension]
      ServiceResult_PresenceStatusResponse.data
        PresenceStatusResponse.{User|Squad|Matchmake}
    """
    if kind == "user":
        # UserStatusResponse.Version=0, Status=UserStatus(empty ratings).
        status = blob(1, scalar(1, 0) + blob(2, b""))
    elif kind == "squad":
        # SquadStatusResponse.Version=0, absent squad (no membership claimed).
        status = blob(2, scalar(1, 0))
    elif kind == "matchmake":
        # MatchmakeStatusResponse.Version=0, Status.State=msMenu(0).
        status = blob(3, scalar(1, 0) + blob(4, scalar(1, 0)))
    else:
        raise ValueError("unknown presence status kind")
    return scalar(1, 0) + blob(TYPE_FIELD, blob(1, status))


def modify_routes(config: dict, undo: bool = False) -> dict:
    if not isinstance(config, dict):
        raise ValueError("route config must be JSON object")
    result = {}
    for key, value in config.items():
        if not isinstance(key, str) or not isinstance(value, dict):
            raise ValueError("invalid route config")
        result[key] = dict(value)
    for method, kind in METHOD_CANDIDATES.items():
        route = f"{SERVICE}.svc/{method}"
        expected = {"response_hex": presence_status_reply(kind).hex()}
        before = {"response_hex": BARE_SUCCESS}
        required = expected if undo else before
        new = before if undo else expected
        if route not in result:
            raise ValueError("missing presence success route; run enable_presence_menu_probe.py first")
        if result[route] not in (required, new):
            raise ValueError("refusing to overwrite customized route: " + route)
        result[route] = new
    return result


def update_local_routes(path: Path, undo: bool = False) -> None:
    original = json.loads(path.read_text(encoding="utf-8"))
    updated = modify_routes(original, undo=undo)
    # Atomic replace avoids half-written configs on Linux; no private address logged.
    import os
    import tempfile
    mode = path.stat().st_mode & 0o777
    fd, temp = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        os.chmod(temp, mode)
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            json.dump(updated, output, indent=2)
            output.write("\n")
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("routes", type=Path)
    ap.add_argument("--undo", action="store_true",
                    help="restore only the three polled methods to bare 0800 success")
    args = ap.parse_args()
    update_local_routes(args.routes, args.undo)
    print("Presence typed status probe " + ("disabled" if args.undo else "enabled"))
    print("Exactly three polled presence routes affected. All IPs and nine heartbeat entries preserved.")
    print("GUID-to-method assignment and status values are hypotheses, not verified protocol.")


if __name__ == "__main__":
    main()
