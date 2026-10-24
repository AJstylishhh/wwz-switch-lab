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
# Only observed after a two-player match; service and method names remain
# unverified. 44 bytes may encode multiple user IDs. Log shapes, never IDs.
POST_MATCH_USER_LOOKUP_CANDIDATE = (
    "/8aa8a8fb77a6450cb44b11e823a7c959.svc/"
    "4be808a1e9a842e581ee6eb47e8cd5eb"
)
MAX_INPUT = 2048
MAX_FIELDS = 24
GUID = re.compile(r"^[a-f0-9]{32}$")


def eligible(path: str) -> bool:
    """Only log bounded unknown presence calls and the observed RedLynx endpoint."""
    if path in (REDLYNX_ENVIRONMENT, POST_MATCH_USER_LOOKUP_CANDIDATE):
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


def nested_shape(raw: bytes, depth: int = 3) -> dict:
    """Bounded, redacted protobuf tree for ONE known post-match RPC.

    We do not emit numeric/scalar values, bytes, string contents, tokens,
    hashes, bcl.Guid payloads, addresses or header data. A raw length-delimited
    field may represent bytes/string, not a nested message. Only recurse when
    the full byte string parses as protobuf without exceeding size limits.
    """
    result = shape(raw)
    if result.get("format") != "protobuf" or depth <= 1:
        return result

    def walk(data, level):
        if level >= depth or len(data) > 256:
            return None
        try:
            entries = list(fields(data))
        except (ValueError, TypeError, OverflowError):
            return None
        if not entries or len(entries) > MAX_FIELDS:
            return None
        children = []
        for n, wire, value in entries:
            item = {"field": n, "wire": wire}
            if isinstance(value, bytes):
                item["size"] = len(value)
                if wire == 2 and value:
                    sub = walk(value, level + 1)
                    if sub is not None:
                        item["children"] = sub
            children.append(item)
        return children

    for item, (_, wire, value) in zip(result["fields"], fields(raw)):
        if wire == 2 and value:
            child = walk(value, 1)
            if child is not None:
                item["children"] = child
    return result


def unknown_request_summary(path: str, raw: bytes) -> dict | None:
    if not eligible(path):
        return None
    if path == POST_MATCH_USER_LOOKUP_CANDIDATE:
        return nested_shape(raw)
    return shape(raw)
