"""Experimental Hydra post-login wire responses, matching Switch protobuf descriptors.

Schemas/field numbers verified offline; values are UNVERIFIED on hardware.
"""
from wwz_wire import blob, scalar, string

HEARTBEAT_REGISTER = "/772eb3c6037845daa9ab86137203ccf2.svc/c5aca06ab450401d9c1b3a9c522ba3f0"
HEARTBEAT_UPDATE = "/772eb3c6037845daa9ab86137203ccf2.svc/e000e353458e4062b8bf7ebe912b225d"
HEARTBEAT_UNREGISTER = "/772eb3c6037845daa9ab86137203ccf2.svc/2b7cf45af675422d99bfc316ee316319"
DATACENTER_OCCUPATION = "/6c60c0f72c1343a385bd02b2b311f402.svc/096a2aba96f44f37802915dc1164746b"
PRESENCE_CONNECT = "/b89429154e224660837a4a307391b0b4.svc/dd280c97b0384ad9907571558151b40c"
REFRESH_TOKENS = "/fb383fc41afb42ce8c3f91bf828ce5a6.svc/c81bf7e6e43e4f39b1c7256651eb3576"
DIAGNOSTICS_WRITE = "/fc8ff9d3e52742f38746806b2ab946a4.svc/cd6d3021266746ffac6a0113e2e89e31"

RESULT_FIELDS = {
    "heartbeat_register": 438369230,
    "heartbeat_update": 417677176,
    "datacenter_occupation": 536714262,
    "presence_connect": 347012296,
    "refresh_tokens": 151915586,
}


def result(kind=None, contents=b""):
    """ServiceResult retCode=Success and optional descriptor-typed envelope."""
    payload = scalar(1, 0)
    if kind is not None:
        payload += blob(RESULT_FIELDS[kind], contents)
    return payload


def occupation(data_center="local"):
    return string(1, data_center) + scalar(2, 0) + scalar(3, 0)


def heartbeat_register_result(users_online=1, poll_ms=10000):
    # UserHeartbeatRegisterResult: Versions=1, PollingIntervals=2,
    # UsersOnline=3, DataCenterOccupation=4.
    inner = blob(1, b"")  # UserVersions unknown until client semantics traced
    for state in range(7):  # GameClientState Offline through Rematch
        inner += blob(2, scalar(1, state) + scalar(2, poll_ms))
    inner += scalar(3, users_online) + blob(4, occupation())
    return result("heartbeat_register", blob(1, inner))


def heartbeat_update_result(users_online=1, poll_ms=10000):
    inner = (blob(1, b"") + scalar(2, users_online) + blob(3, occupation()) +
             blob(4, scalar(1, poll_ms) + scalar(2, poll_ms)))
    return result("heartbeat_update", blob(1, inner))


def data_center_result():
    # ServiceResult_List_DataCenterOccupation.data is repeated field 1.
    return result("datacenter_occupation", blob(1, occupation()))


def presence_connect_result():
    # RegisterResult.ReturnAvailableSeconds=1; 0 = no forced backoff.
    return result("presence_connect", blob(1, scalar(1, 0)))


def refresh_tokens_result(tokens, provider_token, refresh_after=300):
    # ClientTokenList.Tokens=1; ProviderToken=2; RefreshAfter=3.
    inner = b""
    for token in tokens:
        # ClientToken: OldValue=1, ProlongedValue=2, NewValue=3,
        # UpdatePolicy=4(None=0). Keep locally-issued token unchanged.
        entry = (string(1, token) + string(2, token) +
                 string(3, token) + scalar(4, 0))
        inner += blob(1, entry)
    inner += string(2, provider_token) + scalar(3, refresh_after)
    return result("refresh_tokens", blob(1, inner))
