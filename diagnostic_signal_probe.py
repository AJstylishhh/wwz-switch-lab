#!/usr/bin/env python3
"""Safely inspect LOCAL captured WWZ diagnostics for known errors.

Prints only allowlisted error identifiers, protobuf field sizes and
compression-format hints. Never outputs upload contents, identities or tokens.
Works without Git metadata. Python standard library only.
"""
from __future__ import annotations
from collections import Counter
import argparse
import json
from pathlib import Path
import zlib

from wwz_wire import fields

DIAG_ROUTE = "/fc8ff9d3e52742f38746806b2ab946a4.svc/cd6d3021266746ffac6a0113e2e89e31"
MARKERS = (
    "CS_NoDefaultEnvironment", "CS_TooManyDefaultEnvironments",
    "CS_NoServiceEndpoint", "CS_RequiredComponentIsNotConnected",
    "CS_ParseError", "CS_InvalidProviderToken", "CS_InvalidACLToken",
    "CS_NotInitialized", "CS_NotReady", "CS_HTTPManager_UnexpectedStatusCode",
    "CS_HTTPManager_TimeOut", "CS_TimeOut", "CS_UpdatePolicyReconnect",
    "CS_UnavaliableInThisConfiguration", "CS_UnavailableInThisConfiguration",
    "US_UserSignedOut", "Failed to establish connection with WWZ services",
)


def compression_hint(payload: bytes) -> str | None:
    if payload.startswith(b"\x1f\x8b"):
        return "gzip"
    if payload[:4] == b"\x04\x22\x4d\x18":
        return "lz4_frame"
    if len(payload) >= 2 and (payload[0] & 0x0f) == 8 and (
            (payload[0] << 8 | payload[1]) % 31 == 0):
        return "zlib_possible"
    return None


def safe_summary(raw: bytes) -> dict:
    top = list(fields(raw))
    result = {
        "request_bytes": len(raw),
        "fields": [
            {"number": n, "wire_type": w,
             "byte_length": len(v) if isinstance(v, bytes) else None,
             "compression_hint": compression_hint(v) if isinstance(v, bytes) else None}
            for n,w,v in top
        ],
        "known_error_markers": [],
    }
    hits = set()
    for n,w,payload in top:
        if w != 2:
            continue
        for marker in MARKERS:
            if marker.encode("ascii") in payload:
                hits.add(marker)
    result["known_error_markers"] = sorted(hits)
    # Do not recursively inspect arbitrary binary bytes as protobuf.
    return result


def analyze(directory: Path):
    if not directory.is_dir():
        raise ValueError("Capture directory not found")
    matches = []
    for meta in directory.glob("*.json"):
        try:
            record = json.loads(meta.read_text(encoding="utf-8"))
            path = record.get("path", "").lower()
            binary = meta.with_suffix(".bin")
            if path == DIAG_ROUTE and binary.is_file():
                matches.append(binary)
        except (ValueError, OSError, TypeError):
            pass
    if not matches:
        raise ValueError("No matching diagnostic captures found")
    summaries = []
    all_markers = set()
    for file in sorted(matches):
        item = safe_summary(file.read_bytes())
        summaries.append(item)
        all_markers.update(item["known_error_markers"])
    return {
        "captures": len(matches),
        "variants": [
            {"request_bytes": size, "count": count}
            for size,count in sorted(Counter(i["request_bytes"] for i in summaries).items())
        ],
        "known_error_markers": sorted(all_markers),
        "possible_compression": sorted({f["compression_hint"] for s in summaries
                                        for f in s["fields"] if f["compression_hint"]}),
        "note": "No hits does not mean there was no error. Packs may be compressed, binary-encoded or encrypted. Raw values are deliberately omitted.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("captures", nargs="?", type=Path, default=Path("captures"))
    args = parser.parse_args()
    print(json.dumps(analyze(args.captures), indent=2))


if __name__ == "__main__":
    main()
