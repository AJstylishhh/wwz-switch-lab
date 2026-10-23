#!/usr/bin/env python3
"""Test whether WWZ ADF 'entries' are coherent 12-byte offset/length records.

Only uses local encrypted-in-transit captures already decrypted by the user's
test server. Output is AGGREGATE STRUCTURAL METADATA: never exposes entry
values, diagnostic text, filenames, hashes, authentication or player data.

Tests all six offset/length column permutations under both endiannesses.
In-bounds values alone are weak evidence; contiguous coverage, adjacency,
low overlap and reaching the end of 'data' are considerably stronger.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import statistics
import struct

from adf_entry_layout_probe import decompress
from diagnostic_deep_probe import DIAG_ROUTE, MAX_CAPTURE
from wwz_wire import fields

MAX_PACKS = 256
MAX_RECORDS = 100_000
MIN_RECORDS = 3


def candidate(entries: bytes, data_size: int, order: str, offset_col: int, length_col: int):
    if not entries or len(entries) % 12:
        return None
    n = len(entries) // 12
    if n < MIN_RECORDS or n > MAX_RECORDS or data_size < 1:
        return None
    intervals = []
    unique = set()
    for values in struct.iter_unpack(("<" if order == "little" else ">") + "III", entries):
        start, length = values[offset_col], values[length_col]
        if length and start < data_size and length <= data_size - start:
            intervals.append((start, start + length))
            unique.add(start)
    if not intervals:
        return None
    intervals.sort()
    distinct = len(unique) / n
    in_bounds = len(intervals) / n
    merged_covered = 0
    current_start, current_end = intervals[0]
    for start, end in intervals[1:]:
        if start > current_end:
            merged_covered += current_end - current_start
            current_start, current_end = start, end
        else:
            current_end = max(current_end, end)
    merged_covered += current_end - current_start
    exact_next = sum(intervals[i][1] == intervals[i + 1][0]
                     for i in range(len(intervals) - 1))
    no_overlap = sum(intervals[i][1] <= intervals[i + 1][0]
                     for i in range(len(intervals) - 1))
    pair_count = max(1, len(intervals) - 1)
    adj = exact_next / pair_count if len(intervals) > 1 else 0.0
    nonoverlap = no_overlap / pair_count if len(intervals) > 1 else 0.0
    coverage = merged_covered / data_size
    starts_near_zero = intervals[0][0] <= min(32, data_size // 100)
    ends_near_end = max(end for _, end in intervals) >= .95 * data_size
    strong = (in_bounds >= .95 and distinct >= .9 and
              adj >= .75 and nonoverlap >= .95 and coverage >= .7 and
              starts_near_zero and ends_near_end)
    return {
        "order": order, "offset_col": offset_col, "length_col": length_col,
        "in_bounds_pct": round(100 * in_bounds, 1),
        "distinct_offsets_pct": round(100 * distinct, 1),
        "adjacent_pct": round(100 * adj, 1),
        "nonoverlap_pct": round(100 * nonoverlap, 1),
        "covered_data_pct": round(100 * coverage, 1),
        "starts_near_zero": starts_near_zero,
        "reaches_last_5_pct": ends_near_end,
        "strong_sequential_candidate": strong,
    }


def inspect(data: bytes, entries: bytes):
    result = []
    for endian in ("little", "big"):
        for offset in range(3):
            for length in range(3):
                if offset != length:
                    test = candidate(entries, len(data), endian, offset, length)
                    if test is not None:
                        result.append(test)
    return result


def summarize(folder: Path, details=False):
    if not folder.is_dir():
        raise ValueError("capture directory not found")
    packs = []
    exact = Counter()
    skipped = 0
    for meta_path in sorted(folder.glob("*.json")):
        if len(packs) >= MAX_PACKS:
            break
        try:
            metadata = json.loads(meta_path.read_text(encoding="utf-8"))
            if not isinstance(metadata, dict) or str(metadata.get("path", "")).lower() != DIAG_ROUTE:
                continue
            body_path = meta_path.with_suffix(".bin")
            if not body_path.is_file() or body_path.stat().st_size > MAX_CAPTURE:
                skipped += 1
                continue
            parts = {k: v for k, wire, v in fields(body_path.read_bytes())
                     if k in (1, 2) and wire == 2}
            if 1 not in parts or 2 not in parts:
                skipped += 1
                continue
            data, entries = decompress(parts[1]), decompress(parts[2])
            if data is None or entries is None:
                skipped += 1
                continue
            layout = inspect(data, entries)
            packs.append(layout)
            exact[hashlib.sha256(data + b"\x00" + entries).digest()] += 1
        except (OSError, ValueError, UnicodeError, struct.error):
            skipped += 1
    if not packs:
        raise ValueError("no decodable diagnostic packs found")
    by_layout = defaultdict(list)
    for pack in packs:
        for result in pack:
            key = (result["order"], result["offset_col"], result["length_col"])
            by_layout[key].append(result)
    output = []
    for (order, offset, length), rows in sorted(by_layout.items()):
        strong_count = sum(row["strong_sequential_candidate"] for row in rows)
        output.append({
            "byte_order": order, "offset_col": offset, "length_col": length,
            "strong_sequential_packs": strong_count,
            "median_in_bounds_pct": statistics.median(r["in_bounds_pct"] for r in rows),
            "median_distinct_offsets_pct": statistics.median(r["distinct_offsets_pct"] for r in rows),
            "median_adjacent_pct": statistics.median(r["adjacent_pct"] for r in rows),
            "median_nonoverlap_pct": statistics.median(r["nonoverlap_pct"] for r in rows),
            "median_covered_data_pct": statistics.median(r["covered_data_pct"] for r in rows),
            "packs_reaching_last_5_pct": sum(r["reaches_last_5_pct"] for r in rows),
        })
    output.sort(key=lambda row: (
        -row["strong_sequential_packs"], -row["median_adjacent_pct"],
        -row["median_covered_data_pct"], row["byte_order"],
        row["offset_col"], row["length_col"]))
    summary = {
        "packs_examined": len(packs),
        "skipped": skipped,
        "unique_exact_payloads": len(exact),
        "layout_hypotheses": output[:12],
        "note": ("In-bounds columns alone prove very little. A strong sequential layout "
                 "should cover much of the data in adjacent, minimally overlapping chunks "
                 "with offsets from near zero to near the end. These are heuristic "
                 "requirements, not a definition of WWZ ADF. No private content is output."),
    }
    if details:
        summary["per_pack_strong_layouts"] = [
            {"order": idx + 1, "layouts": [
                "byte_order=%s offset=%s length=%s" %
                (r["order"], r["offset_col"], r["length_col"])
                for r in rows if r["strong_sequential_candidate"]]}
            for idx, rows in enumerate(packs)]
    return summary


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("captures", nargs="?", type=Path, default=Path("captures"))
    p.add_argument("--details", action="store_true",
                   help="include strong-layout hypotheses per capture (no raw bytes)")
    args = p.parse_args()
    print(json.dumps(summarize(args.captures, details=args.details), indent=2))


if __name__ == "__main__":
    main()
