"""Experimental WWZ authorization Dequeue -> SignInResult; not Switch-verified.

No Nintendo auth is performed. Only locally issued queue tokens are accepted.
"""
from dataclasses import dataclass
import hmac
import secrets
import threading
import time
from uuid import uuid4

from wwz_wire import fields, blob, scalar, string

DEQUEUE_ROUTE = "/0ae806e0260340fe86eb38ff8708252f.svc/c4504538d0ca4b2fb2a9e87f0091f97e"
SIGNIN_RESULT_FIELD = 323326796


def parse_dequeue(raw):
    """Extract queue token and public service names without logging values."""
    token = None
    names = []
    for field, wire, data in fields(raw):
        if field == 1 and wire == 2 and token is None:
            try:
                token = data.decode("ascii")
            except UnicodeDecodeError as e:
                raise ValueError("invalid token encoding") from e
        elif field == 2 and wire == 2:
            name = None
            for number, kind, value in fields(data):
                if number == 1 and kind == 2:
                    try:
                        name = value.decode("ascii")
                    except UnicodeDecodeError as e:
                        raise ValueError("invalid service name") from e
                elif number in (2, 3) and kind != 0:
                    raise ValueError("bad service version type")
            if name is not None:
                names.append(name)
        else:
            raise ValueError("unexpected Dequeue field")
    if not token or not names or len(names) > 100:
        raise ValueError("missing token or versions")
    return token, tuple(names)


@dataclass(frozen=True)
class Identity:
    auth: str
    diagnostic: str
    access: str
    provider: str
    user_guid: object
    provider_user: str


def encode_signin(identity, services, *, address, port, name, provider_environment=None,
                  provider_has_subscription=None):
    """SignInResult in ServiceResult_SignInResult (field 323326796)."""
    if not (isinstance(address, str) and address and isinstance(name, str) and
            name and 1 <= int(port) <= 65535):
        raise ValueError("invalid backend endpoint")
    data = (string(1, identity.auth) + string(2, identity.diagnostic) +
            string(3, identity.access) + string(4, identity.provider))
    endpoints = tuple(dict.fromkeys((name, *services)))
    for entry in endpoints:
        ep = (string(1, entry) + string(2, address) + scalar(3, int(port)) +
              scalar(4, 1) + scalar(5, int(entry == name)))
        data += blob(5, ep)
    binary = identity.user_guid.bytes_le
    guid = b"\x09" + binary[:8] + b"\x11" + binary[8:]
    data += blob(8, blob(1, guid))  # SignInResult.User.Uid (bcl.Guid)
    data += string(9, identity.provider_user)
    if provider_has_subscription is not None and type(provider_has_subscription) is not bool:
        raise ValueError("provider_has_subscription must be a boolean or null")
    if provider_environment is not None or provider_has_subscription is not None:
        environment_enum = {"Dev": 1, "Retail": 2}
        if provider_environment not in (None, *environment_enum):
            raise ValueError("unknown test provider environment")
        # SignInResult.ProviderInfo=10, ProviderOptionalInfo.HasSubscription=1.
        # Disabled by default. Opt-in simulation is not proof of a Nintendo
        # subscription and cannot replace the console's system-side checks.
        optional_info = b""
        if provider_has_subscription is not None:
            optional_info += scalar(1, int(provider_has_subscription))
        if provider_environment is not None:
            optional_info += scalar(2, environment_enum[provider_environment])
        data += blob(10, optional_info)
    return scalar(1, 0) + blob(SIGNIN_RESULT_FIELD, blob(1, data))


class AuthSessions:
    """Bounded local identities with independent login and session lifetimes.

    Queue tokens authorize the initial Dequeue only (default five minutes).
    A successfully issued SignInResult creates an independent, expiring
    authenticated session. Refreshing its locally-issued tokens extends that
    session's idle lifetime; it does not require the old queue ticket.
    This is experimental identity emulation, not Nintendo authentication.
    """

    def __init__(self, queue, limit=256, session_ttl=3600, clock=time.monotonic):
        if limit <= 0 or session_ttl <= 0:
            raise ValueError("limit and session_ttl must be positive")
        self.queue = queue
        self.limit = limit
        self.session_ttl = session_ttl
        self.clock = clock
        self.identities = {}
        self.expirations = {}
        self.lock = threading.RLock()

    def _prune_locked(self, now):
        for key, expiration in tuple(self.expirations.items()):
            if expiration <= now:
                self.expirations.pop(key, None)
                self.identities.pop(key, None)

    def resolve_refresh_tokens(self, tokens):
        """Validate all supplied credentials against one active local session."""
        if not tokens or len(tokens) > 3 or any(not isinstance(t, str) or not t for t in tokens):
            raise ValueError("Unrecognized refresh tokens")
        with self.lock:
            now = self.clock()
            self._prune_locked(now)
            for queue_token, identity in self.identities.items():
                allowed = (identity.auth, identity.diagnostic, identity.access)
                if all(any(hmac.compare_digest(t, known) for known in allowed) for t in tokens):
                    self.expirations[queue_token] = now + self.session_ttl
                    return identity
        raise ValueError("Unrecognized refresh tokens")

    def respond(self, raw, *, address, port, name, provider_environment=None,
                provider_has_subscription=None):
        token, services = parse_dequeue(raw)
        # Queue ticket is checked *only* for the initial Dequeue.
        if not self.queue.recognizes(token):
            raise ValueError("unknown or expired queue token")
        with self.lock:
            now = self.clock()
            self._prune_locked(now)
            ident = self.identities.get(token)
            if ident is None:
                if len(self.identities) >= self.limit:
                    oldest = min(self.expirations, key=self.expirations.get)
                    self.expirations.pop(oldest, None)
                    self.identities.pop(oldest, None)
                ident = Identity(
                    "lab-auth-" + secrets.token_urlsafe(32),
                    "lab-diagnostic-" + secrets.token_urlsafe(32),
                    "lab-access-" + secrets.token_urlsafe(32),
                    "lab-provider-" + secrets.token_urlsafe(32),
                    uuid4(), "lab-" + secrets.token_urlsafe(12))
                self.identities[token] = ident
            self.expirations[token] = now + self.session_ttl
            response = encode_signin(
                ident, services, address=address, port=port, name=name,
                provider_environment=provider_environment,
                provider_has_subscription=provider_has_subscription)
            return response, {"service_versions": len(services),
                              "endpoints": len(set((name, *services)))}
