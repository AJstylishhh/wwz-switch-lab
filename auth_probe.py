#!/usr/bin/env python3
"""Privacy-preserving protobuf structural classifier for the second WWZ RPC.

Never prints string values, tokens, fingerprints, login credentials, or raw bytes.
Method candidates are schema-compatible guesses, NOT verified GUID mappings.
Supports one .bin file or a capture directory written by mvp_server.py.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from wwz_wire import fields

AUTH_ROUTE = "/0ae806e0260340fe86eb38ff8708252f.svc/3ad39ec0971940b98e522d40229704b9"

# Extracted from the client's IAuthorizationService_* protobuf definitions.
# Mapping field number -> protobuf wire type; 2=length-delimited.
METHODS = {
    "CheckBan": {1: 2},
    "CreateSlaveServerDiagnosticSession": {1: 2, 2: 2, 3: 2},
    "Dequeue": {1: 2, 2: 2},
    "Enqueue": {1: 2, 2: 2, 3: 2, 4: 2, 5: 2, 6: 2},
    "GetDiagnosticsToken": {1: 2, 2: 2, 3: 2, 4: 2, 5: 2},
    "ReEnqueue": {1: 2, 2: 2, 3: 2, 4: 2},
    "SignIn": {1: 2, 2: 2},
    "Upqueue": {1: 2},
}


def summarize(raw: bytes) -> dict:
    observed = list(fields(raw))
    unique_numbers = {num for num, wire, value in observed}
    ranked = []
    for name, spec in METHODS.items():
        matched = sum(num in spec and spec[num] == wire for num, wire, _ in observed)
        mismatched = sum(num in spec and spec[num] != wire for num, wire, _ in observed)
        unknown = sum(num not in spec for num, wire, _ in observed)
        priority = (matched, -mismatched, -unknown, -abs(len(spec) - len(unique_numbers)))
        ranked.append((priority, name))
    ranked.sort(reverse=True)
    return {
        "length": len(raw),
        "fields": [{"number": n, "wire_type": w,
                    "byte_length": len(v) if isinstance(v, bytes) else None}
                   for n, w, v in observed],
        "candidates": [{"method": method, "matched": score[0],
                        "mismatched": -score[1], "unknown": -score[2]}
                       for score, method in ranked],
        "warning": "Wire compatibility does not prove method identity. Keep raw captures private."
    }


def select_capture(path: Path):
    if path.is_file() and path.suffix.lower() == ".bin":
        return path
    if not path.is_dir():
        raise ValueError("Supply one private .bin file or the captures directory")
    matches = []
    for metadata in path.glob("*.json"):
        try:
            info = json.loads(metadata.read_text(encoding="utf-8"))
            candidate = metadata.with_suffix(".bin")
            if info.get("path", "").lower() == AUTH_ROUTE and candidate.is_file():
                matches.append(candidate)
        except (OSError, ValueError, TypeError):
            pass
    if not matches:
        raise ValueError("No matching 11704 authorization capture found in directory")
    return sorted(matches)[-1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path, help="file.bin or captures/ directory")
    args = parser.parse_args()
    selected = select_capture(args.capture)
    print(json.dumps(summarize(selected.read_bytes()), indent=2))


if __name__ == "__main__":
    main()
