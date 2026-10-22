#!/usr/bin/env python3
"""Derive candidate .svc service/method GUID pairs from WWZ Switch main.rodata.

The records are empirically identified as 24-byte entries containing a pointer
to a GUID string, sidecar pointer and marker 0x403. A unique method GUID
immediately precedes a repeated service GUID in the observed layout.
This grouping is a STATIC HEURISTIC until cross-references prove dispatch.
No game binaries are checked into Git.
"""
import argparse
from collections import Counter
import json
from pathlib import Path

from inspect_guid_records import RODATA_VA, records


def infer_pairs(rows):
    guids = [row["guid"] for row in rows]
    counts = Counter(guids)
    found = []
    for i in range(len(rows) - 1):
        method, service = guids[i:i+2]
        if counts[method] != 1 or counts[service] < 2:
            continue
        found.append({
            "service_guid": service,
            "method_guid": method,
            "route": f"/{service}.svc/{method}",
            "method_record_va": rows[i]["record_va"],
            "service_record_va": rows[i+1]["record_va"],
        })
    return found


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rodata", type=Path, help="locally decompressed main.rodata.bin")
    parser.add_argument("--rodata-va", type=lambda n: int(n, 0), default=RODATA_VA)
    parser.add_argument("--guid", help="filter to service or method GUID")
    args = parser.parse_args()
    rows = list(records(args.rodata.read_bytes(), args.rodata_va))
    pairs = infer_pairs(rows)
    if args.guid:
        pairs = [p for p in pairs if args.guid.lower() in
                 (p["service_guid"], p["method_guid"])]
    print(json.dumps({
        "candidate_pair_count": len(pairs),
        "unique_service_guids": len({p["service_guid"] for p in pairs}),
        "pairs": pairs,
        "warning": "These are structural candidates, not proven RPC method names."
    }, indent=2))


if __name__ == "__main__":
    main()
