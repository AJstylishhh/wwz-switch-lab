"""Bounded, opt-in heartbeat version pulse for *observed lab roster changes*.

The NSO build checked here expects precisely nine UserVersions integers.
That fact comes from an ARM64 length comparison, not from the protobuf
descriptor (which only declares a repeated int64). The *meaning* of each
slot is not verified, so this is a deliberately reversible experiment.

Potentially observed consumer slots: 0, 1, 2, 4, 6 (zero-based), from
the nine-value application loop. Slots 3, 5, 7, 8 are left unchanged.
"""
from __future__ import annotations

from wwz_wire import fields


def client_reported_versions(raw):
    """Parse only field-5 UserVersions in a Heartbeat.Update request.

    No headers, properties or user-identifying payloads are retained or
    logged. A malformed / omitted list returns None for diagnostics.
    This helper never controls authorization or the wire response.
    """
    try:
        root = list(fields(raw))
        versions = [v for n, w, v in root if (n, w) == (5, 2)]
        if len(versions) != 1:
            return None
        entries = list(fields(versions[0]))
        if len(entries) > 20 or any((n, w) != (1, 0) for n, w, _ in entries):
            return None
        return tuple(value for _, _, value in entries)
    except (ValueError, IndexError, TypeError):
        return None

VERSION_COUNT = 9
EXPERIMENTAL_SLOTS = (0, 1, 2, 4, 6)
MAX_REVISION = 1024
MAX_I64 = (1 << 63) - 1


def pulse_versions(configured, roster_revision):
    """Return fresh immutable values; never mutate the routes config.

    Zero means no change. Only actual shared-lobby membership transitions
    increase roster_revision, not frequent GameData writes or heartbeats.
    """
    if not isinstance(configured, (list, tuple)) or len(configured) != VERSION_COUNT:
        raise ValueError("lobby version pulse requires exactly nine baseline entries")
    if any(type(v) is not int or not 0 <= v <= MAX_I64 for v in configured):
        raise ValueError("invalid heartbeat version integer")
    if type(roster_revision) is not int or roster_revision < 0:
        raise ValueError("invalid roster revision")
    if roster_revision == 0:
        return tuple(configured)
    bump = min(roster_revision, MAX_REVISION)
    versions = list(configured)
    for slot in EXPERIMENTAL_SLOTS:
        if versions[slot] > MAX_I64 - bump:
            raise ValueError("heartbeat version would overflow")
        versions[slot] += bump
    return tuple(versions)
