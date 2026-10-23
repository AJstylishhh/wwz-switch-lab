"""On-receipt WWZ diagnostic pack summary for the experimental HTTPS lab.

Bounded, allowlisted and non-persistent. Presence of a text marker in a pack
is NOT proof it is a client-raised error: ADF can contain string dictionaries.
No URLs, token values, authentication bodies or private captured bytes printed.
"""
from collections import Counter

from diagnostic_deep_probe import inspect_pack


def safe_live_summary(raw: bytes) -> dict:
    """Summarize one WriteADFPack request, without exposing captured content."""
    parsed = inspect_pack(raw)  # Bounded decompression and known-marker matching.
    parts = parsed["parts"]
    headers = parsed["headers"]
    hints = Counter(part["hint"] for part in parts)
    decoded = Counter(kind for part in parts for kind in part["verified"])
    markers = sorted({marker for part in parts for marker in part["markers"]})
    classes = Counter(header.get("format_class", "missing") for header in headers)
    return {
        "packed_fields": len(parts),
        "header_count": len(headers),
        "format_classes": dict(sorted(classes.items())),
        "compression_hints": dict(sorted(hints.items())),
        "verified_decompression": dict(sorted(decoded.items())),
        "known_marker_strings": markers,
        "warning": "markers are present strings, not confirmed runtime errors",
    }
