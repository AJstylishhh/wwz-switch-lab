#!/usr/bin/env python3
import base64
from pathlib import Path
parts = []
for i in range(6):
    parts.append(Path(__file__).with_name(f"lobby_b64_{i}.txt").read_text().strip())
raw = base64.b64decode("".join(parts))
Path(__file__).with_name("lobby_registry.py").write_bytes(raw)
print("Restored lobby_registry.py", len(raw), "bytes")
assert b"joined_soft_playlist_mismatch" in raw
