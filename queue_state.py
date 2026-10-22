"""Ephemeral authorization queue for the first observed WWZ Enqueue RPC.

The response is schema-valid but is NOT confirmed accepted by the Switch.
Credential/request bytes are never retained: an HMAC digest is used as the
short-lived request cache key. For test-console interoperability only.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time

from auth_queue_candidate import candidate
from wwz_wire import fields

ENQUEUE_ROUTE = "/0ae806e0260340fe86eb38ff8708252f.svc/3ad39ec0971940b98e522d40229704b9"


def inspect_enqueue(raw: bytes) -> dict:
    """Check captured 6-field wire signature without exposing sensitive values."""
    items = list(fields(raw))
    seen = {n: (wire, value) for n, wire, value in items}
    if set(seen) != set(range(1, 7)) or len(items) != 6:
        raise ValueError("expected six Enqueue fields (1..6)")
    if any(wire != 2 for wire, value in seen.values()):
        raise ValueError("Enqueue requires length-delimited fields")
    # Reject broken nested protobuf, but do not interpret login/password bytes.
    list(fields(seen[1][1]))
    list(fields(seen[5][1]))
    return {"fields": len(items), "field_sizes": [len(seen[n][1]) for n in range(1, 7)]}


class QueueState:
    """Single-process experiment, not official identity/authentication.

    Tokens repeat for identical requests until TTL expiration, preventing
    repeated retries from creating a new identity each time. Memory bounded.
    """
    def __init__(self, ttl=300, limit=256, clock=time.monotonic):
        if ttl <= 0 or limit <= 0:
            raise ValueError("ttl and limit must be positive")
        self.ttl = ttl
        self.limit = limit
        self.clock = clock
        self.key = secrets.token_bytes(32)
        self.entries = {}  # HMAC digest -> (token, expiration); never raw credentials
        self.lock = threading.Lock()

    def issue(self, raw: bytes) -> bytes:
        inspect_enqueue(raw)
        digest = hmac.digest(self.key, raw, hashlib.sha256)
        with self.lock:
            now = self.clock()
            for key, (_, expires) in list(self.entries.items()):
                if expires <= now:
                    del self.entries[key]
            existing = self.entries.get(digest)
            if existing is not None:
                token = existing[0]
            else:
                if len(self.entries) >= self.limit:
                    oldest = min(self.entries, key=lambda k: self.entries[k][1])
                    del self.entries[oldest]
                token = "wwz-lab-" + secrets.token_urlsafe(32)
            self.entries[digest] = token, now + self.ttl
            return candidate(token)

    def recognizes(self, token: str) -> bool:
        """Useful later for Dequeue, once its *real* method GUID is confirmed."""
        with self.lock:
            now = self.clock()
            return any(expires > now and secrets.compare_digest(token, existing)
                       for existing, expires in self.entries.values())
