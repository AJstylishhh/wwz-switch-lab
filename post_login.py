"""Experimental stateful WWZ post-login RPC dispatch.

Single-process test lab; correlation of heartbeat/presence to individual
users is not yet supported. Do not expose to untrusted networks.
"""
import hmac
import threading
from wwz_wire import fields
import post_login_wire as wire

ROUTES = {
    wire.HEARTBEAT_REGISTER: "heartbeat_register",
    wire.HEARTBEAT_UPDATE: "heartbeat_update",
    wire.HEARTBEAT_UNREGISTER: "heartbeat_unregister",
    wire.DATACENTER_OCCUPATION: "datacenter_occupation",
    wire.PRESENCE_CONNECT: "presence_connect",
    wire.REFRESH_TOKENS: "refresh_tokens",
    wire.DIAGNOSTICS_WRITE: "diagnostics_ack",
}
EXPECTED = {
    "heartbeat_register": {1: 2, 2: 0, 3: 0},
    "heartbeat_update": {1: 2, 2: 0, 3: 2, 4: 0, 5: 2},
    "heartbeat_unregister": {1: 0},
    "datacenter_occupation": {1: 2},
    "presence_connect": {1: 2, 2: 0, 3: 2},
    "refresh_tokens": {1: 2},
    "diagnostics_ack": {1: 2, 2: 2, 3: 2},
}


def inspect_request(kind, raw):
    items = list(fields(raw))
    schema = EXPECTED[kind]
    if any(n not in schema or schema[n] != w for n, w, _ in items):
        raise ValueError("Unexpected protobuf field layout")
    if kind in ("heartbeat_register", "presence_connect", "diagnostics_ack"):
        if {n for n, _, _ in items} != {1, 2, 3}:
            raise ValueError("Missing required experimental request fields")
    if kind == "refresh_tokens" and not items:
        raise ValueError("Missing tokens")
    if kind == "diagnostics_ack":
        # Nested header must be valid protobuf; never log contents.
        list(fields(next(v for n, _, v in items if n == 3)))
    return items


class PostLogin:
    def __init__(self, auth_sessions):
        self.auth_sessions = auth_sessions
        self.lock = threading.RLock()
        self.heartbeat_generation = None
        self.heartbeat_state = None
        self.presence_connected = False
        self.diagnostic_packs = 0

    def _identity_for_tokens(self, tokens):
        # All supplied tokens must belong to the same locally-issued session.
        with self.auth_sessions.lock:
            for queue_token, identity in self.auth_sessions.identities.items():
                if not self.auth_sessions.queue.recognizes(queue_token):
                    continue
                allowed = (identity.auth, identity.diagnostic, identity.access)
                if all(any(hmac.compare_digest(t, known) for known in allowed)
                       for t in tokens):
                    return identity
        raise ValueError("Unrecognized refresh tokens")

    def respond(self, path, raw):
        kind = ROUTES.get(path)
        if kind is None:
            raise ValueError("Unmapped service")
        items = inspect_request(kind, raw)
        with self.lock:
            if kind == "heartbeat_register":
                if not next(v for n, _, v in items if n == 1):
                    raise ValueError("Missing game version")
                self.heartbeat_generation = next(v for n, _, v in items if n == 2)
                self.heartbeat_state = next(v for n, _, v in items if n == 3)
                return wire.heartbeat_register_result(), {"stage": kind, "poll_ms": 10000}
            if kind == "heartbeat_update":
                self.heartbeat_generation = next((v for n, _, v in items if n == 2), None)
                self.heartbeat_state = next((v for n, _, v in items if n == 4), None)
                return wire.heartbeat_update_result(), {"stage": kind}
            if kind == "heartbeat_unregister":
                self.heartbeat_generation = None
                self.heartbeat_state = None
                return wire.result(), {"stage": kind}
            if kind == "datacenter_occupation":
                if len(items) != 1 or not items[0][2]:
                    raise ValueError("Missing version")
                return wire.data_center_result(), {"stage": kind, "centers": 1}
            if kind == "presence_connect":
                self.presence_connected = True
                return wire.presence_connect_result(), {"stage": kind}
            if kind == "refresh_tokens":
                try:
                    tokens = [v.decode("ascii") for n, _, v in items]
                except UnicodeDecodeError as e:
                    raise ValueError("Malformed token encoding") from e
                identity = self._identity_for_tokens(tokens)
                return (wire.refresh_tokens_result(tokens, identity.provider),
                        {"stage": kind, "tokens": len(tokens)})
            if kind == "diagnostics_ack":
                self.diagnostic_packs += 1
                # Explicit experiment: discard telemetry, return only success.
                return wire.result(), {"stage": kind, "discarded_packs": self.diagnostic_packs}
        raise AssertionError("Unreachable")
