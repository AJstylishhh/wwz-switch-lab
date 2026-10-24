"""Opt-in WWZ lab session correlation: local issued identity, not source IP.

A Dequeue establishes an identity and tokens returned in SignInResult.
Later authenticated RPCs are resolved via a validated issued token if present.
With no token, source-IP affinity is allowed ONLY when exactly one session
is associated with that IP. Two sessions behind NAT are never silently merged.

This is NOT device identification. One device can create many sessions, and the
source protocol must actually present a usable token on later RPCs.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time

CREDENTIAL_HEADERS = (
    "Authorization",
    "AuthorizationToken",
    "X-Auth-Token",
    "X-Access-Token",
    "X-Authorization",
)
MAX_SESSIONS = 256


class UnresolvedClient(ValueError):
    """Zero or several candidate sessions, or unrecognized bearer token."""


def _candidate_credentials(headers):
    """Yield only known client credential header values, no logs."""
    for name in CREDENTIAL_HEADERS:
        value = headers.get(name)
        if not value:
            continue
        value = value.strip()
        if not value:
            continue
        if name.lower() == "authorization" and value.lower().startswith("bearer "):
            value = value[7:].strip()
        if value and len(value) <= 512:
            yield value


class ClientSessionIndex:
    """Small in-memory correlation of verified local sessions to network sources."""

    def __init__(self, *, ttl_seconds=3600, clock=time.monotonic,
                 max_sessions=MAX_SESSIONS):
        if ttl_seconds <= 0 or max_sessions < 1:
            raise ValueError("invalid session index limits")
        self.clock = clock
        self.ttl_seconds = ttl_seconds
        self.max_sessions = max_sessions
        self.lock = threading.RLock()
        self._key = secrets.token_bytes(32)
        self.sessions = {}  # session-key -> (synthetic Identity, expires_at)
        self.sources = {}   # process-keyed IP source -> set(session-key)

    def _key_for_identity(self, identity):
        # Sessions use our *issued* SignInResult identity, never a claimed
        # ID in an unauthenticated client request.
        return hmac.digest(self._key, identity.user_guid.bytes, hashlib.sha256)[:16].hex()

    def _label(self, session_key):
        return session_key[:12]

    def _prune(self):
        now = self.clock()
        for sid, (_, expiry) in tuple(self.sessions.items()):
            if expiry <= now:
                del self.sessions[sid]
        for source, members in tuple(self.sources.items()):
            members.intersection_update(self.sessions)
            if not members:
                del self.sources[source]

    def attach(self, source_key, identity):
        """Register a successful Dequeue without deleting another NAT user."""
        if not source_key or not hasattr(identity, "user_guid"):
            raise ValueError("Dequeue must provide source and issued identity")
        with self.lock:
            self._prune()
            sid = self._key_for_identity(identity)
            if sid not in self.sessions and len(self.sessions) >= self.max_sessions:
                raise UnresolvedClient("session registry capacity reached")
            prior = len(self.sources.get(source_key, ()))
            self.sessions[sid] = identity, self.clock() + self.ttl_seconds
            self.sources.setdefault(source_key, set()).add(sid)
            return sid, {
                "stage": "lobby_session_attach",
                "session_tag": self._label(sid),
                "same_network_source_sessions": len(self.sources[source_key]),
                "another_session_on_source": len(self.sources[source_key]) > 1,
            }

    def resolve(self, source_key, headers):
        """Resolve known issued bearer or unambiguous source affinity.

        No API exposes auth token text. A supplied unrecognized credential
        is not silently overridden by IP affinity.
        """
        with self.lock:
            self._prune()
            credentials = tuple(_candidate_credentials(headers))
            if credentials:
                matches = []
                for sid, (ident, _) in self.sessions.items():
                    issued = (ident.auth, ident.access)
                    if any(any(hmac.compare_digest(value, t) for t in issued)
                           for value in credentials):
                        matches.append(sid)
                if len(matches) != 1:
                    raise UnresolvedClient("unrecognized or ambiguous issued credential")
                sid = matches[0]
                self.sources.setdefault(source_key, set()).add(sid)
                method = "issued_token"
            else:
                members = self.sources.get(source_key, set())
                if len(members) != 1:
                    raise UnresolvedClient(
                        "ambiguous shared-NAT sessions" if members
                        else "no signed-in session for network source")
                sid = next(iter(members))
                method = "unique_source"
            ident, _ = self.sessions[sid]
            self.sessions[sid] = ident, self.clock() + self.ttl_seconds
            return sid, {
                "session_tag": self._label(sid),
                "identity_resolution": method,
                "same_network_source_sessions": len(self.sources[source_key]),
            }
