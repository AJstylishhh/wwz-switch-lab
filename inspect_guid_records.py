#!/usr/bin/env python3
"""Find GUID pointer records in a decompressed WWZ Switch NSO .rodata section.

Input is locally extracted from the game executable; no executable bytes,
certificates, or raw private network captures belong in the public repository.
Usage:
  python inspect_guid_records.py path/to/main.rodata.bin
  python inspect_guid_records.py path/to/main.rodata.bin --guid c928398a5e4b4debb4099f62383eb196
"""
import argparse
import json
import re
from pathlib import Path
from struct import unpack_from

RODATA_VA = 0x2131000
GUID = re.compile(rb"[a-f0-9]{32}\x00")


def records(rodata: bytes, rodata_va: int = RODATA_VA):
    """Yield candidate entries (string pointer, sidecar pointer, 0x403 marker).

    Structure was found empirically, NOT identified as an actual RPC dispatch
    table or a proof of any service-to-method pairing.
    """
    for offset in range(0, len(rodata) - 24 + 1, 8):
        string_va, sidecar_va, marker = unpack_from("<QQQ", rodata, offset)
        if marker != 0x403:
            continue
        string_offset = string_va - rodata_va
        if not (0 <= string_offset <= len(rodata) - 33):
            continue
        match = GUID.match(rodata, string_offset)
        if match:
            yield {
                "record_va": f"0x{rodata_va + offset:x}",
                "string_va": f"0x{string_va:x}",
                "sidecar_va": f"0x{sidecar_va:x}",
                "guid": match.group(0)[:-1].decode("ascii"),
            }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rodata", type=Path, help="locally decompressed main.rodata.bin")
    parser.add_argument("--rodata-va", type=lambda value: int(value, 0), default=RODATA_VA)
    parser.add_argument("--guid", help="only show records for this exact GUID")
    args = parser.parse_args()

    found = list(records(args.rodata.read_bytes(), args.rodata_va))
    if args.guid:
        found = [item for item in found if item["guid"] == args.guid.lower()]
    print(json.dumps({"record_count": len(found), "records": found}, indent=2))


if __name__ == "__main__":
    main()
