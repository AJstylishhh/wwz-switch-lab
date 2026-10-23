#!/usr/bin/env python3
"""Inspect fixed-width structure of LOCAL World War Z ADF diagnostic uploads.

Read-only. Never prints decompressed content, record integer values, hashes,
filenames, account details, or arbitrary text. Tests the hypothesis that
the zlib-compressed 'entries' section contains 12-byte index records.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import struct

from diagnostic_deep_probe import (
    DIAG_ROUTE, MAX_CAPTURE, bounded_decompress, compression_kind,
)
from wwz_wire import fields

MAX_PACKS = 256
MAX_RECORDS = 100_000


def decompress(payload):
    kind = compression_kind(payload)
    if kind == "zlib_possible":
        return bounded_decompress(payload, 15)
    if kind == "gzip":
        return bounded_decompress(payload, 31)
    return None


def record_layout(entries: bytes, data_length: int):
    """Look at metadata only; byte order/layout remain hypotheses."""
    count = len(entries) // 12
    result = {"entry_bytes": len(entries),
              "multiple_of_12": len(entries) % 12 == 0,
              "entry_count_if_12_bytes": count if len(entries) % 12 == 0 else None,
              "candidate_offset_length_columns": []}
    if len(entries) % 12 or not count or count > MAX_RECORDS:
        return result
    columns = [[], [], []]
    for values in struct.iter_unpack("<III", entries):
        for i, number in enumerate(values):
            columns[i].append(number)
    result["column_shapes"] = []
    for i, values in enumerate(columns):
        result["column_shapes"].append({
            "column": i,
            "within_data_pct": round(100 * sum(v < data_length for v in values) / count, 1),
            "zero_pct": round(100 * sum(v == 0 for v in values) / count, 1),
            "unique_count": len(set(values)),
            "nondecreasing_pct": (
                round(100 * sum(a <= b for a, b in zip(values, values[1:]))
                      / (count - 1), 1) if count > 1 else None
            ),
        })
    for offset_col in range(3):
        for length_col in range(3):
            if offset_col == length_col:
                continue
            offsets, lengths = columns[offset_col], columns[length_col]
            valid = sum(0 < length <= data_length and off <= data_length - length
                        for off, length in zip(offsets, lengths))
            pct = round(100 * valid / count, 1)
            # Reject trivial all-zero / constant candidates.
            if pct >= 70 and len(set(offsets)) >= 3:
                result["candidate_offset_length_columns"].append({
                    "offset_column": offset_col,
                    "length_column": length_col,
                    "in_bounds_nonempty_pct": pct,
                })
    result["candidate_offset_length_columns"].sort(
        key=lambda entry: -entry["in_bounds_nonempty_pct"])
    return result


def summarize(folder: Path, details=False):
    if not folder.is_dir():
        raise ValueError("capture directory does not exist")
    reports = []
    fingerprints = Counter()
    skipped = 0
    for metadata in sorted(folder.glob("*.json")):
        if len(reports) >= MAX_PACKS:
            break
        try:
            meta = json.loads(metadata.read_text(encoding="utf-8"))
            if not isinstance(meta, dict) or str(meta.get("path", "")).lower() != DIAG_ROUTE:
                continue
            binary = metadata.with_suffix(".bin")
            if not binary.is_file() or binary.stat().st_size > MAX_CAPTURE:
                skipped += 1
                continue
            parts = {n: payload for n, wire, payload in fields(binary.read_bytes())
                     if n in (1, 2) and wire == 2}
            if 1 not in parts or 2 not in parts:
                skipped += 1
                continue
            data = decompress(parts[1])
            entries = decompress(parts[2])
            if data is None or entries is None:
                skipped += 1
                continue
            # Fingerprint comparison is local only: no digest is emitted.
            fingerprint = hashlib.sha256(
                len(data).to_bytes(8, "little") + data + entries).digest()
            fingerprints[fingerprint] += 1
            report = record_layout(entries, len(data))
            reports.append({"order": len(reports) + 1,
                            "data_bytes": len(data), **report})
        except (OSError, ValueError, UnicodeError, struct.error):
            skipped += 1
    if not reports:
        raise ValueError("no decodable ADF packs found")
    totals = Counter()
    for report in reports:
        totals["divisible_by_12"] += int(report["multiple_of_12"])
        totals["has_offset_length_candidate"] += int(
            bool(report["candidate_offset_length_columns"]))
    pair_counts = Counter(
        "offset=%s length=%s" % (pair["offset_column"], pair["length_column"])
        for report in reports for pair in report["candidate_offset_length_columns"])
    summary = {
        "packs_examined": len(reports),
        "skipped": skipped,
        "entries_multiple_of_12": totals["divisible_by_12"],
        "with_plausible_offset_length_columns": totals["has_offset_length_candidate"],
        "plausible_column_pairs": dict(sorted(pair_counts.items())),
        "exact_duplicate_payload_groups": sorted(
            (n for n in fingerprints.values() if n > 1), reverse=True),
        "entries_count_histogram": dict(sorted(Counter(
            str(r["entry_count_if_12_bytes"]) for r in reports).items(),
            key=lambda item: int(item[0]) if item[0].isdigit() else -1)),
        "warning": (
            "Three little-endian 32-bit integers per 12-byte record is only a "
            "hypothesis. In-bounds pairs can be coincidences; no semantic layout "
            "is proven. No raw values, contents, account data or hashes are printed."
        ),
    }
    if details:
        summary["per_pack"] = reports
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("captures", type=Path, nargs="?", default=Path("captures"))
    parser.add_argument("--details", action="store_true",
                        help="show per-pack aggregate column patterns (still no raw data)")
    args = parser.parse_args()
    print(json.dumps(summarize(args.captures, details=args.details), indent=2))


if __name__ == "__main__":
    main()
