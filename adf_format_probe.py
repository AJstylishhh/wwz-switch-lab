#!/usr/bin/env python3
"""Classify decompressed WWZ ADF packs WITHOUT printing any payload contents.

Diagnostic-only: no server changes, login capture, network access or external
dependencies. This is a coarse format probe, not a decoded WWZ error report.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path

from diagnostic_deep_probe import (
    DIAG_ROUTE, MAX_CAPTURE, bounded_decompress, compression_kind
)
from wwz_wire import fields

KEYWORDS = {
    "error": b"error",
    "exception": b"exception",
    "timeout": b"timeout",
    "offline": b"offline",
    "disconnect": b"disconnect",
    "failed": b"failed",
    "subscription": b"subscription",
    "not_connected": b"not connected",
    "invalid": b"invalid",
}
MAX_ITEMS = 40000


def decompressed_bytes(payload: bytes):
    kind = compression_kind(payload)
    if kind == "zlib_possible":
        return bounded_decompress(payload, 15), "zlib"
    if kind == "gzip":
        return bounded_decompress(payload, 31), "gzip"
    return None, kind


def characterize(data: bytes):
    """Only categorical output. No raw bytes, decoded text or literal values."""
    if not data:
        return {"format": "empty", "length": 0, "keyword_hits": []}
    fmt = "opaque_binary"
    try:
        decoded = data.decode("utf-8")
        control = sum(c in "\x00\x01\x02\x03\x04\x05\x06\x07\x08\x0b\x0c\x0e\x0f" for c in decoded)
        printable_fraction = 1 - control / max(len(decoded), 1)
        if printable_fraction > 0.97:
            fmt = "utf8_text"
            try:
                json.loads(decoded)
                fmt = "json"
            except (ValueError, RecursionError):
                pass
    except UnicodeDecodeError:
        pass
    if fmt == "opaque_binary":
        try:
            # Heuristic only: protobuf can parse arbitrary bytes as unknown fields.
            parsed = list(fields(data))
            if len(parsed) <= MAX_ITEMS and parsed:
                fmt = "protobuf_wire_candidate"
        except (ValueError, RecursionError):
            pass
    lower = data.lower()
    return {
        "format": fmt,
        "length": len(data),
        "keyword_hits": sorted(k for k, token in KEYWORDS.items() if token in lower),
    }


def analyze(capture_dir: Path):
    if not capture_dir.is_dir():
        raise ValueError("capture folder does not exist")
    counts = Counter()
    format_counts = Counter()
    len_ranges = {}
    keyword_counts = Counter()
    missing, discarded = 0, 0
    for metadata in sorted(capture_dir.glob("*.json")):
        try:
            meta = json.loads(metadata.read_text(encoding="utf-8"))
            if not isinstance(meta, dict) or str(meta.get("path", "")).lower() != DIAG_ROUTE:
                continue
            body_file = metadata.with_suffix(".bin")
            if not body_file.exists():
                missing += 1
                continue
            if body_file.stat().st_size > MAX_CAPTURE:
                discarded += 1
                continue
            for field, wire, payload in fields(body_file.read_bytes()):
                if wire != 2 or field not in (1, 2):
                    continue
                key = "data" if field == 1 else "entries"
                result, kind = decompressed_bytes(payload)
                counts[key + "_parts"] += 1
                if result is None:
                    counts[key + "_not_decompressed"] += 1
                    continue
                counts[key + "_decompressed"] += 1
                desc = characterize(result)
                format_counts[key + ":" + desc["format"]] += 1
                for keyword in desc["keyword_hits"]:
                    keyword_counts[keyword] += 1
                previous = len_ranges.get(key)
                size = desc["length"]
                len_ranges[key] = [size, size] if previous is None else [
                    min(previous[0], size), max(previous[1], size)]
        except (OSError, ValueError, UnicodeError, RecursionError):
            discarded += 1
    return {
        "part_counts": dict(sorted(counts.items())),
        "decoded_format_classes": dict(sorted(format_counts.items())),
        "decompressed_length_min_max": len_ranges,
        "keyword_presence_counts": dict(sorted(keyword_counts.items())),
        "skipped_or_invalid": discarded,
        "missing_payload_files": missing,
        "warning": ("No contents or identities are printed. A protobuf-wire match is "
                    "only a syntactic heuristic; missing keywords do not prove no error.")
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("captures", type=Path, nargs="?", default=Path("captures"))
    args = parser.parse_args()
    print(json.dumps(analyze(args.captures), indent=2))


if __name__ == "__main__":
    main()
