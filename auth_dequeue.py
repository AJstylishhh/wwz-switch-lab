"""Experimental WWZ authorization Dequeue -> SignInResult; not Switch-verified.

No Nintendo auth is performed. Only locally issued queue tokens are accepted.
"""
from dataclasses import dataclass
import secrets
import threading
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


def encode_signin(identity, services, *, address, port, name, provider_environment=None):
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
    if provider_environment is not None:
        environment_enum = {"Dev": 1, "Retail": 2}
        if provider_environment not in environment_enum:
            raise ValueError("unknown test provider environment")
        # SignInResult.ProviderInfo=10 -> ProviderOptionalInfo.Environment=2.
        # Deliberately do NOT synthesize HasSubscription=1.
        data += blob(10, scalar(2, environment_enum[provider_environment]))
    return scalar(1, 0) + blob(SIGNIN_RESULT_FIELD, blob(1, data))


class AuthSessions:
    """Process-local identities linked to bounded, expiring QueueState."""
    def __init__(self, queue, limit=256):
        self.queue = queue
        self.limit = limit
        self.identities = {}
        self.lock = threading.RLock()

    def respond(self, raw, *, address, port, name, provider_environment=None):
        token, services = parse_dequeue(raw)
        if not self.queue.recognizes(token):
            raise ValueError("unknown or expired queue token")
        with self.lock:
            for key in list(self.identities):
                if not self.queue.recognizes(key):
                    del self.identities[key]
            ident = self.identities.get(token)
            if ident is None:
                if len(self.identities) >= self.limit:
                    del self.identities[next(iter(self.identities))]
                ident = Identity(
                    "lab-auth-" + secrets.token_urlsafe(32),
                    "lab-diagnostic-" + secrets.token_urlsafe(32),
                    "lab-access-" + secrets.token_urlsafe(32),
                    "lab-provider-" + secrets.token_urlsafe(32),
                    uuid4(), "lab-" + secrets.token_urlsafe(12))
                self.identities[token] = ident
            response = encode_signin(
                ident, services, address=address, port=port, name=name,
                provider_environment=provider_environment)
            return response, {"service_versions": len(services),
                              "endpoints": len(set((name, *services)))}
