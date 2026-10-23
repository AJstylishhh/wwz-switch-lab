"""Bounded, content-free request shapes for unknown WWZ presence RPCs.

Use only with known lab RPCs; print field numbers, wire types and byte lengths.
No text, tokens, binary contents, packet hashes, peer addresses or headers
are emitted. This is instrumentation, NOT a decoder of semantic method names.
"""
from __future__ import annotations

import re

from wwz_wire import fields

PRESENCE_PREFIX = "/b89429154e224660837a4a307391b0b4.svc/"
REDLYNX_ENVIRONMENT = (
    "/redlynx.api.endpointdispatcher.endpointdispatcherapi/getenvironmentinfo"
)
MAX_INPUT = 2048
MAX_FIELDS = 24
GUID = re.compile(r"^[a-f0-9]{32}$")


def eligible(path: str) -> bool:
    """Only log bounded unknown presence calls and the observed RedLynx endpoint."""
    if path == REDLYNX_ENVIRONMENT:
        return True
    if not path.startswith(PRESENCE_PREFIX):
        return False
    return GUID.fullmatch(path[len(PRESENCE_PREFIX):]) is not None


def shape(raw: bytes) -> dict:
    """Non-sensitive protobuf layout summary; never render wire values."""
    result = {"bytes": len(raw)}
    if len(raw) > MAX_INPUT:
        return {**result, "format": "over_limit"}
    try:
        entries = list(fields(raw))
        if len(entries) > MAX_FIELDS:
            return {**result, "format": "too_many_fields"}
        public = []
        for n, wire, v in entries:
            # Bounded field number, wire kind and lengths only.
            item = {"field": n, "wire": wire}
            if isinstance(v, bytes):
                item["size"] = len(v)
            public.append(item)
        return {**result, "format": "protobuf", "fields": public}
    except (ValueError, TypeError, OverflowError):
        return {**result, "format": "unknown"}


def unknown_request_summary(path: str, raw: bytes) -> dict | None:
    if not eligible(path):
        return None
    return shape(raw)
