"""Opt-in experimental UserBaseData reply for a *verified shared lab lobby*.

Based on the exact protobuf descriptor; hashed RPC-to-method mapping and
actual Switch UI acceptance remain hypotheses. No public matchmaking,
Nintendo auth, real gamer identities or gameplay transport are implemented.
"""
from __future__ import annotations

from lobby_registry import user_id
from post_match_user_probe import parse_lookup_user_ids
from wwz_wire import blob, scalar, string

USER_BASE_DATA_RESULT_FIELD = 194158588


def public_user_data_reply(raw: bytes, lobby_member_identities: dict) -> tuple[bytes, dict]:
    """Return a typed list only if ALL requested IDs are shared lobby members.

    An unknown / nonmember user must be rejected before encoding any reply.
    Avoid using random provider tokens as nicknames or revealing stable profiles.
    Names are intentionally synthetic and session-scoped.
    """
    requested = parse_lookup_user_ids(raw)
    if any(uid not in lobby_member_identities for uid in requested):
        raise ValueError("public user lookup contains a nonmember")
    data = b""
    for uid in requested:
        nickname = "WWZ Lab " + uid.hex[:8]
        user_base = blob(1, user_id(uid)) + string(2, nickname)
        data += blob(1, user_base)
    return scalar(1, 0) + blob(USER_BASE_DATA_RESULT_FIELD, data), {
        "stage": "public_user_data_candidate",
        "requested_records": len(requested),
        "known_lobby_members": len(lobby_member_identities),
        "result_records": len(requested),
        "nickname_source": "synthetic",
    }
