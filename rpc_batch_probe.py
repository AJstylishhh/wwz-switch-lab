#!/usr/bin/env python3
"""Batch summarize ALL new WWZ .svc requests without revealing field contents.

Reads the local, private mvp_server.py captures directory. Outputs ONLY routes,
top-level protobuf wire types/lengths, counts and cautious method candidates.
No authentication or player payload contents are printed or uploaded.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path

from wwz_wire import fields

# Derived from the Switch NSO's embedded backendPb FileDescriptorProto.
# Candidate signatures contain {field number: protobuf wire type}.
# This is intentionally a *focused* catalog, not a GUID-to-RPC mapping.
SHAPES = {
    "IUserHeartbeatService_RegisterVersioned": {1: 2, 2: 0, 3: 0},
    "IUserHeartbeatService_UpdateVersioned": {1: 2, 2: 0, 3: 2, 4: 0, 5: 2},
    "IUserHeartbeatService_UnRegister": {1: 0},
    "IDataCenterService_GetDataCentersOccupation": {1: 2},
    "IPingService_Ping": {1: 2},
    "IDiagnosticDataService_WriteADFPack": {1: 2, 2: 2, 3: 2},
    "IDiagnosticDataService_WriteDiagnosticsData": {1: 2, 2: 2, 3: 0},
    "IDiagnosticDataService_AppendReplayFile": {1: 2, 2: 2, 3: 0},
    "IDiagnosticDataService_SendUserReport": {1: 2},
    "IAccessManagementService_ReSignIn": {},
    "IAccessManagementService_SignOut": {},
    "IAccessManagementService_RefreshAclToken": {1: 2},
    "IAccessManagementService_RefreshTokens": {1: 2},
    "IGameConfigurationService_GetActiveFirstGameDefinition": {},
    "IGameConfigurationService_GetLayers": {1: 2},
    "IGameConfigurationService_GetLayersDataJson": {1: 2},
    "IGameConfigurationService_GetLayersToUpdate": {1: 2, 2: 2},
    "IUserService_GetUsersByNickname": {1: 0, 2: 2},
    "IUserService_GetUsersPublicDataByProviderUserId": {1: 2, 2: 2},
    "IPresenceService_PresenceConnect": {1: 2, 2: 0, 3: 2},
    "IPresenceService_GetStatusUser": {},
    "IPresenceService_GetStatusMatchmake": {1: 0},
    "IPresenceService_GetStatusSquad": {1: 0, 2: 0},
    "ISessionControlServiceCompact_ClientCreateSession": {1: 2, 2: 2, 3: 2, 4: 2},
    "ISessionControlServiceCompact_ClientGetSessionInfoCompact": {1: 2},
}


def shape(raw: bytes):
    """Top-level field metadata; never return bytes or scalar values."""
    return [{"number": n, "wire_type": w,
             "byte_length": len(v) if isinstance(v, bytes) else None}
            for n, w, v in fields(raw)]


def candidates(items: list[dict], limit: int = 8):
    observed = {item["number"]: item["wire_type"] for item in items}
    matches = []
    for method, signature in SHAPES.items():
        # Exclude unexpected fields and conflicting wire types.
        if any(signature.get(field) != wire for field, wire in observed.items()):
            continue
        # Fewer missing optional fields is a more useful lead, not proof.
        missing = len(set(signature) - set(observed))
        matches.append((missing, method))
    matches.sort(key=lambda item: (item[0], item[1]))
    return [name for _, name in matches[:limit]]


def analyze(capture_dir: Path, routes_file: Path | None = None, include_known=False):
    if not capture_dir.is_dir():
        raise ValueError("captures directory does not exist")
    known = set()
    if routes_file and routes_file.is_file() and not include_known:
        routes = json.loads(routes_file.read_text(encoding="utf-8"))
        known = {"/" + p.lower().lstrip("/") for p in routes}
    grouped = defaultdict(list)
    for metadata in sorted(capture_dir.glob("*.json")):
        binary = metadata.with_suffix(".bin")
        if not binary.is_file():
            continue
        try:
            record = json.loads(metadata.read_text(encoding="utf-8"))
            path = str(record.get("path", "")).lower()
            if not path.startswith("/") or ".svc/" not in path or path in known:
                continue
            data = binary.read_bytes()
            field_shape = shape(data)
        except (ValueError, OSError, UnicodeError):
            continue
        grouped[path].append((metadata.name, len(data), field_shape))
    result = []
    for path, events in sorted(grouped.items()):
        variants = {}
        for filename, length, items in events:
            signature = (length, tuple((f["number"], f["wire_type"], f["byte_length"]) for f in items))
            if signature not in variants:
                variants[signature] = {"request_bytes": length, "fields": items,
                                       "count": 0, "candidates": candidates(items)}
            variants[signature]["count"] += 1
        result.append({"path": path, "observations": len(events),
                       "variants": sorted(variants.values(), key=lambda item: item["request_bytes"])})
    return {"services": result, "note": (
        "Candidates are wire-shape suggestions only, not confirmed GUID mapping. "
        "No request values are disclosed."
    )}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("captures", type=Path, nargs="?", default=Path("captures"))
    parser.add_argument("--routes", type=Path,
                        default=Path(__file__).with_name("routes.mvp.example.json"))
    parser.add_argument("--include-known", action="store_true")
    args = parser.parse_args()
    print(json.dumps(analyze(args.captures, args.routes, args.include_known), indent=2))


if __name__ == "__main__":
    main()
