#!/usr/bin/env python3
"""Inspect captured WWZ RPC protobuf fields without printing token or user values."""
import argparse
import json
from pathlib import Path
from wwz_wire import fields


def inspect(raw):
    return {"request_bytes": len(raw), "fields": [
        {"number": n, "wire_type": wire,
         "byte_length": len(value) if isinstance(value, bytes) else None}
        for n, wire, value in fields(raw)]}


def select(capture_dir, mapped_routes=None):
    if not capture_dir.is_dir():
        raise ValueError("captures directory not found")
    mapped = mapped_routes or set()
    captures = []
    for metadata in capture_dir.glob("*.json"):
        binary = metadata.with_suffix(".bin")
        if not binary.is_file():
            continue
        try:
            item = json.loads(metadata.read_text(encoding="utf-8"))
        except (ValueError, OSError, UnicodeError):
            continue
        path = str(item.get("path", "")).lower()
        if path.startswith("/") and ".svc/" in path and path not in mapped:
            captures.append((metadata.name, path, binary))
    if not captures:
        raise ValueError("no unmapped capture found; use --all or capture the next RPC")
    _, path, binary = max(captures)
    return path, binary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("captures", type=Path, nargs="?", default=Path("captures"))
    parser.add_argument("--routes", type=Path, default=Path(__file__).with_name("routes.mvp.example.json"))
    parser.add_argument("--all", action="store_true", help="also select known/mapped routes")
    args = parser.parse_args()
    mapped = set()
    if not args.all:
        routes = json.loads(args.routes.read_text(encoding="utf-8"))
        mapped = {"/" + str(name).lstrip("/").lower() for name in routes}
    path, binary = select(args.captures, mapped)
    print(json.dumps({"path": path, **inspect(binary.read_bytes()),
                      "warning": "Only field structure, not raw values, is displayed."}, indent=2))


if __name__ == "__main__":
    main()
