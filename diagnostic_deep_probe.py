#!/usr/bin/env python3
"""Inspect local WWZ WriteADFPack uploads without exposing captured identities.

Uses descriptor-derived data=1, entries=2, header=3. Attempts bounded
zlib/gzip/ZIP decompression and emits only allowlisted error identifiers
and coarse header metadata. Never prints raw strings or diagnostic contents.
"""
from __future__ import annotations
from collections import Counter
import argparse
import io
import json
from pathlib import Path
import zipfile
import zlib

from wwz_wire import fields

DIAG_ROUTE = "/fc8ff9d3e52742f38746806b2ab946a4.svc/cd6d3021266746ffac6a0113e2e89e31"
MAX_CAPTURE = 1024 * 1024
MAX_DECODED = 4 * 1024 * 1024
MARKERS = (
    "CS_NoDefaultEnvironment", "CS_TooManyDefaultEnvironments",
    "CS_NoServiceEndpoint", "CS_RequiredComponentIsNotConnected",
    "CS_ParseError", "CS_InvalidProviderToken", "CS_InvalidACLToken",
    "CS_NotInitialized", "CS_NotReady", "CS_HTTPManager_UnexpectedStatusCode",
    "CS_HTTPManager_TimeOut", "CS_HTTPManager_CompressionError",
    "CS_HTTPManager_DecompressionError", "CS_TimeOut", "CS_UpdatePolicyReconnect",
    "CS_UnavaliableInThisConfiguration", "CS_HTTPManager_Error",
    "US_UserSignedOut", "Failed to establish connection with WWZ services",
    "autogen VersionDataType_Last does not corresponds with backend values",
)
SAFE_FORMATS = {"adf", "json", "jsonl", "protobuf", "binary", "csv",
                "gzip", "zlib", "text", "msgpack", "zip"}


def header_summary(data):
    """Never display SessionId, arbitrary Format strings or Context values."""
    result = {"present": True, "context_entries": 0}
    for number, wire, value in fields(data):
        if number == 2 and wire == 2:
            try:
                fmt = value.decode("ascii").strip().lower()
            except UnicodeDecodeError:
                fmt = ""
            result["format_class"] = fmt if fmt in SAFE_FORMATS else "other"
        elif number in (3, 4, 5, 6) and wire == 0:
            result[{3: "major_version", 4: "minor_version",
                    5: "pack_number", 6: "flags"}[number]] = value
        elif number == 8 and wire == 2:
            result["context_entries"] += 1
    return result


def compression_kind(data):
    if data.startswith(b"\x1f\x8b"):
        return "gzip"
    if len(data) > 1 and (data[0] & 15) == 8 and data[0] >> 4 <= 7 and (
            ((data[0] << 8) | data[1]) % 31 == 0):
        return "zlib_possible"
    if data.startswith(b"PK\x03\x04"):
        return "zip"
    if data.startswith(b"\x04\x22\x4d\x18"):
        return "lz4_frame"
    if data.startswith(b"\x28\xb5\x2f\xfd"):
        return "zstd_frame"
    return "unknown"


def bounded_decompress(data, wbits):
    """Avoid decompression bombs, incomplete streams, and unbounded output."""
    try:
        dec = zlib.decompressobj(wbits)
        output = dec.decompress(data, MAX_DECODED + 1)
        if len(output) > MAX_DECODED or not dec.eof:
            return None
        extra = dec.flush(MAX_DECODED + 1 - len(output))
        if len(output) + len(extra) > MAX_DECODED:
            return None
        return output + extra
    except (zlib.error, ValueError):
        return None


def inspect_part(payload):
    kind = compression_kind(payload)
    contents = [payload]
    verified = []
    if kind in ("gzip", "zlib_possible"):
        data = bounded_decompress(payload, 31 if kind == "gzip" else 15)
        if data is not None:
            contents.append(data)
            verified.append("gzip" if kind == "gzip" else "zlib")
    elif kind == "zip":
        try:
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                for member in archive.infolist()[:32]:
                    if member.is_dir() or member.file_size > MAX_DECODED:
                        continue
                    with archive.open(member) as stream:
                        data = stream.read(MAX_DECODED + 1)
                    if len(data) <= MAX_DECODED:
                        contents.append(data)
                verified.append("zip")
        except (OSError, ValueError, EOFError, RuntimeError, zipfile.BadZipFile,
                NotImplementedError):
            pass
    found = {name for body in contents for name in MARKERS
             if name.encode("ascii") in body}
    return {"hint": kind, "verified": verified, "markers": sorted(found)}


def inspect_pack(raw):
    if len(raw) > MAX_CAPTURE:
        raise ValueError("capture size exceeds cap")
    parts = {1: [], 2: [], 3: []}
    for n, wire, value in fields(raw):
        if n in parts and wire == 2:
            parts[n].append(value)
    headers = [header_summary(raw_header) for raw_header in parts[3]]
    results = [inspect_part(data) for data in parts[1] + parts[2]]
    return {"headers": headers, "parts": results}


def analyze(capture_dir):
    if not capture_dir.is_dir():
        raise ValueError("capture directory not found")
    scanned, skipped = [], 0
    for metadata in sorted(capture_dir.glob("*.json")):
        binary = metadata.with_suffix(".bin")
        if not binary.is_file():
            continue
        try:
            record = json.loads(metadata.read_text(encoding="utf-8"))
            if str(record.get("path", "")).lower() != DIAG_ROUTE:
                continue
            scanned.append(inspect_pack(binary.read_bytes()))
        except (OSError, ValueError, UnicodeError):
            skipped += 1
    if not scanned:
        raise ValueError("no matching readable diagnostic capture found")
    all_headers = [h for result in scanned for h in result["headers"]]
    all_parts = [p for result in scanned for p in result["parts"]]
    return {
        "diagnostic_packs": len(scanned),
        "skipped": skipped,
        "signature_hints": dict(sorted(Counter(p["hint"] for p in all_parts).items())),
        "verified_decompression": dict(sorted(
            Counter(v for p in all_parts for v in p["verified"]).items())),
        "format_classes": dict(sorted(Counter(
            h.get("format_class", "missing") for h in all_headers).items())),
        "header_version_pairs": [list(item) for item in sorted({
            (h.get("major_version"), h.get("minor_version")) for h in all_headers
        }, key=lambda v: ((v[0] or 0), (v[1] or 0)))],
        "known_error_markers": sorted({
            name for p in all_parts for name in p["markers"]
        }),
        "note": "No marker does not mean no error; ADF may be packed binary, encrypted, or use numeric error codes. Raw data remains private.",
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("captures", type=Path, nargs="?", default=Path("captures"))
    args = p.parse_args()
    print(json.dumps(analyze(args.captures), indent=2))


if __name__ == "__main__":
    main()
