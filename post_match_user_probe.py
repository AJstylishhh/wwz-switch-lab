"""Read-only correlation for the UNVERIFIED post-match user-lookup RPC.

Only accept the exact repeated backendPb.UserId -> bcl.Guid shape observed
in real Switch traffic. Return counts/classifications, never user IDs, token
values, request bytes or even unsalted hashes. No RPC response is generated.
"""
from __future__ import annotations

import hmac
from uuid import UUID

from wwz_wire import fields

MAX_LOOKUP_BYTES = 1024
MAX_LOOKUP_USERS = 16


def parse_lookup_user_ids(raw: bytes) -> tuple[UUID, ...]:
    """Decode repeated UserId records, strictly; reject unknown layouts."""
    if not 0 < len(raw) <= MAX_LOOKUP_BYTES:
        raise ValueError("invalid lookup length")
    records = list(fields(raw))
    if not 0 < len(records) <= MAX_LOOKUP_USERS:
        raise ValueError("invalid lookup record count")

    users = []
    for number, wire, user in records:
        if (number, wire) != (1, 2) or len(user) != 20:
            raise ValueError("unexpected lookup user field")
        nested = list(fields(user))
        if len(nested) != 1 or nested[0][:2] != (1, 2):
            raise ValueError("unexpected UserId shape")
        guid = nested[0][2]
        if len(guid) != 18:
            raise ValueError("unexpected GUID length")
        halves = list(fields(guid))
        if (len(halves) != 2 or [item[:2] for item in halves] !=
                [(1, 1), (2, 1)]):
            raise ValueError("unexpected bcl.Guid fields")
        users.append(UUID(bytes_le=halves[0][2] + halves[1][2]))
    return tuple(users)


def classify_lookup(raw: bytes, issued_identities, acl_token: str | None) -> dict:
    """Return only count-level evidence, including authenticated caller relation.

    The caller is verified only if acl-token matches exactly one locally
    issued authorization/access-role token. This is not Nintendo account auth.
    A failure to decode a candidate RPC never turns its HTTP 404 into a 200.
    """
    try:
        requested = parse_lookup_user_ids(raw)
    except (ValueError, TypeError, OverflowError):
        return {"format": "unrecognized"}

    identities = tuple(issued_identities)
    issued = {identity.user_guid for identity in identities}
    distinct = set(requested)

    requester = None
    if isinstance(acl_token, str) and 0 < len(acl_token) <= 512:
        matches = [
            identity.user_guid for identity in identities
            if any(hmac.compare_digest(acl_token, token)
                   for token in (identity.auth, identity.access))
        ]
        if len(set(matches)) == 1:
            requester = matches[0]

    result = {
        "format": "user_ids",
        "requested_records": len(requested),
        "distinct_requested_users": len(distinct),
        "issued_user_matches": len(distinct & issued),
        "unknown_user_ids": len(distinct - issued),
        "requester_verified": requester is not None,
    }
    if requester is not None:
        result["includes_requester"] = requester in distinct
        result["other_issued_users_requested"] = len(
            (distinct & issued) - {requester})
    return result
