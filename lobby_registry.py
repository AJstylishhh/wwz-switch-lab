"""Opt-in, in-memory WWZ squad and matchmaking lab.

Wire shapes are based on the embedded Switch proto2 descriptor. Hashed RPC
GUID assignments are still hypotheses, and this is not gameplay networking.
Never retain login tokens, raw IPs, or actual traffic on disk.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import hmac
import secrets
import threading
import time
from uuid import UUID, uuid4

from enable_presence_status_probe import METHOD_CANDIDATES, SERVICE, TYPE_FIELD, presence_status_reply
from enable_lobby_rpc_probe import TARGETS
from wwz_wire import blob, fields, scalar, string

PREFIX = "/" + SERVICE + ".svc/"
HANDLERS = {
    PREFIX + "5df1122df8884a408c2b804153dc90f1": "settings",
    PREFIX + "44a718e4c7514684b5259e0879e98c63": "game_data",
    PREFIX + "dfd72da619924665a51e16f74e813f13": "invites",
    PREFIX + "67cdaf75ca604bd993ad9f1db0c3f812": "start",
    PREFIX + "f9dcd75c457145e7a8b4d5e619171fc1": "stop",
    PREFIX + "44106e2a072d4667999b814b3207e195": "squad_status",
    PREFIX + "2896c4aa256e4e7290454ef6df3f1ce9": "match_status",
    # Observed 47x during matchmaking. Method name is NOT proven.
    PREFIX + "b2ba5509c32e43f09b39cb0a828059df": "observed_scalar",
}
SUCCESS = scalar(1, 0)
MAX_PLAYERS = 4
MAX_GROUPS = 128
MAX_SOURCES = 256
MAX_BODY = 8192
IDLE_SECONDS = 1800


def bcl_guid(value: UUID) -> bytes:
    data = value.bytes_le
    # bcl.Guid fields fixed64=1 / fixed64=2. Match the issued UserId.
    return b"\x09" + data[:8] + b"\x11" + data[8:]


def user_id(uid: UUID) -> bytes:
    return blob(1, bcl_guid(uid))


def presence_reply(kind: str, response: bytes) -> bytes:
    # ServiceResult -> ServiceResult_PresenceStatusResponse.data
    # -> PresenceStatusResponse.{Squad=2, Matchmake=3}
    field_number = {"squad": 2, "matchmake": 3}[kind]
    return SUCCESS + blob(TYPE_FIELD, blob(1, blob(field_number, response)))


def single_field(raw: bytes, expected_field: int, wire: int):
    entries = list(fields(raw))
    if len(entries) != 1 or entries[0][:2] != (expected_field, wire):
        raise ValueError("unexpected lobby request fields")
    return entries[0][2]


def matchmake_playlist(raw: bytes) -> str:
    """Extract only the playlist needed for lab grouping; no player secrets."""
    if len(raw) > MAX_BODY:
        raise ValueError("oversized matchmake request")
    entries = list(fields(raw))
    if len(entries) > 32:
        raise ValueError("too many matchmake fields")
    if any(n not in (1, 2, 3, 4) or wire != 2 for n, wire, _ in entries):
        raise ValueError("invalid MatchmakeStart signature")
    playlist = next((v for n, _, v in entries if n == 3), b"")
    if len(playlist) > 256:
        raise ValueError("oversized playlist")
    # Verify known nested shapes without interpreting private game metadata.
    for n, _, data in entries:
        if n in (1, 2, 4):
            list(fields(data))
    return playlist.decode("utf-8")


@dataclass
class Lobby:
    lid: UUID
    owner: str
    members: list[str]
    created: float
    updated: float
    playlist: str = ""
    settings: bytes = b""
    game_data: str = ""
    invites_state: int = 0
    queued: bool = False
    version: int = 1


class LobbyRegistry:
    """Guarded ephemeral registry, keyed by process-private source HMAC tags.

    Source tags identify remote network addresses, not Nintendo users.
    Clients sharing one public IP are deliberately not supported by this MVP.
    """
    def __init__(self, *, clock=time.monotonic, idle_seconds=IDLE_SECONDS):
        if idle_seconds <= 0:
            raise ValueError("invalid idle ttl")
        self.clock = clock
        self.idle_seconds = idle_seconds
        self.lock = threading.RLock()
        self.identities = {}    # pseudonymous source -> synthetic SignIn Identity
        self.groups = {}        # random UUID -> Lobby
        self.member_group = {}  # source -> lobby UUID
        # Random, process-scoped key prevents offline guessing of short playlist
        # strings from their diagnostic tags. Never log the key or raw playlist.
        self._diagnostic_key = secrets.token_bytes(32)
        self._scalar_observations = {}  # source -> (last numeric value, count)

    def _playlist_tag(self, playlist):
        return hmac.digest(self._diagnostic_key, playlist.encode("utf-8"),
                           hashlib.sha256)[:6].hex()

    def _expire(self):
        now = self.clock()
        for lid, group in list(self.groups.items()):
            if now - group.updated > self.idle_seconds:
                self.groups.pop(lid, None)
                for source in group.members:
                    if self.member_group.get(source) == lid:
                        self.member_group.pop(source, None)

    def attach(self, source: str, identity):
        with self.lock:
            if not isinstance(source, str) or not source:
                raise ValueError("missing source")
            previous = self.identities.get(source)
            if previous is not None and previous.user_guid != identity.user_guid:
                self._leave(source)
                self._scalar_observations.pop(source, None)
            if source not in self.identities and len(self.identities) >= MAX_SOURCES:
                raise ValueError("too many client sources")
            self.identities[source] = identity

    def _require(self, source):
        if source not in self.identities:
            raise ValueError("client has not completed Dequeue")
        return self.identities[source]

    def _group(self, source, *, create=False):
        lid = self.member_group.get(source)
        group = self.groups.get(lid)
        if group is not None:
            return group
        if not create:
            return None
        if len(self.groups) >= MAX_GROUPS:
            raise ValueError("lab lobby capacity reached")
        now = self.clock()
        group = Lobby(uuid4(), source, [source], now, now)
        self.groups[group.lid] = group
        self.member_group[source] = group.lid
        return group

    def _touch(self, group):
        group.version += 1
        group.updated = self.clock()

    def _leave(self, source):
        group = self._group(source)
        if group is None:
            return
        group.members.remove(source)
        self.member_group.pop(source, None)
        if not group.members:
            self.groups.pop(group.lid, None)
        else:
            if group.owner == source:
                group.owner = group.members[0]
            self._touch(group)

    def _size(self, group):
        if not group.settings:
            return MAX_PLAYERS
        count = next((v for n, w, v in fields(group.settings)
                      if (n, w) == (1, 0)), MAX_PLAYERS)
        return min(MAX_PLAYERS, max(1, count or MAX_PLAYERS))

    def _join_queue(self, source, group):
        current = self._group(source)
        if current is not None and current.lid != group.lid:
            self._leave(source)
        if source not in group.members:
            group.members.append(source)
            self.member_group[source] = group.lid
            self._touch(group)

    def _squad(self, source, group) -> bytes:
        payload = b""
        if group.game_data:
            payload += string(1, group.game_data)
        for member in group.members:
            identity = self.identities[member]
            data = (blob(1, user_id(identity.user_guid)) +
                    scalar(2, int(member == group.owner)) +
                    scalar(4, 1))  # GameClientState.StateMenu (conservative)
            payload += blob(2, data)
        if group.settings:
            payload += blob(3, group.settings)
        else:
            payload += blob(3, scalar(1, MAX_PLAYERS))
        squad_id = blob(227625060, blob(1, bcl_guid(group.lid)))
        payload += blob(4, squad_id) + scalar(5, group.invites_state)
        return scalar(1, group.version) + blob(2, payload)

    def _matchmake(self, source, group) -> bytes:
        state = 1 if group is not None and group.queued else 0  # msQueue / msMenu
        status = scalar(1, state)
        if group is not None and group.queued:
            party_id = blob(425731978, blob(1, bcl_guid(group.lid)))
            queue = blob(1, party_id)
            for member in group.members:
                identity = self.identities[member]
                queue += blob(2, blob(1, user_id(identity.user_guid)) +
                              scalar(2, int(member == group.owner)))
            queue += scalar(3, 0) + string(7, group.playlist)
            status += blob(5, queue) + string(7, group.playlist)
            status += scalar(10, self._size(group))
        return scalar(1, group.version if group else 0) + blob(4, status)

    def respond(self, source: str, path: str, raw: bytes):
        kind = HANDLERS.get(path)
        if kind is None:
            raise ValueError("unknown lobby handler")
        if len(raw) > MAX_BODY:
            raise ValueError("oversized lobby request")
        with self.lock:
            self._expire()
            self._require(source)
            group = self._group(source)
            details = {}
            if kind == "settings":
                value = single_field(raw, 1, 2)
                if len(value) > 128:
                    raise ValueError("settings too large")
                list(fields(value))
                group = group or self._group(source, create=True)
                group.settings = value
                self._touch(group)
                details["max_count"] = self._size(group)
            elif kind == "game_data":
                value = single_field(raw, 1, 2)
                if len(value) > 2048:
                    raise ValueError("game_data too large")
                group = group or self._group(source, create=True)
                group.game_data = value.decode("utf-8")
                self._touch(group)
            elif kind == "invites":
                value = single_field(raw, 1, 0)
                if value not in (0, 1, 2):
                    raise ValueError("unknown invites setting")
                group = group or self._group(source, create=True)
                group.invites_state = value
                self._touch(group)
            elif kind == "start":
                playlist = matchmake_playlist(raw)
                # Join only a *queued* lobby with the same playlist. A squad
                # left in the local UI is not automatically public.
                others = [g for g in self.groups.values()
                          if g.queued and source not in g.members]
                compatible = [g for g in others if g.playlist == playlist]
                available = [g for g in compatible if len(g.members) < self._size(g)]
                candidate = min(available, key=lambda g: (g.created, g.lid.int),
                                default=None)
                details = {
                    "playlist_tag": self._playlist_tag(playlist),
                    "playlist_bytes": len(playlist.encode("utf-8")),
                    "other_queued_groups": len(others),
                    "same_playlist_groups": len(compatible),
                    "same_playlist_open_seats": len(available),
                }
                if candidate:
                    self._join_queue(source, candidate)
                    group = candidate
                    details["decision"] = "joined_existing_queue"
                else:
                    group = group or self._group(source, create=True)
                    group.playlist = playlist
                    group.queued = True
                    self._touch(group)
                    details["decision"] = ("no_other_queue" if not others else
                                           "playlist_differs" if not compatible else
                                           "matching_queue_full")
                details["max_count"] = self._size(group)
            elif kind == "stop":
                if raw:
                    raise ValueError("MatchmakeStop should have no fields")
                if group is not None:
                    group.queued = False
                    self._touch(group)
            elif kind == "observed_scalar":
                # A two-byte repeating scalar method was seen during matchmaking.
                # Track shape only; never claim it is a known SDK method.
                value = single_field(raw, 1, 0)
                previous, count = self._scalar_observations.get(source, (None, 0))
                count += 1
                self._scalar_observations[source] = value, count
                if previous != value or count % 20 == 0:
                    details = {"observed_value": value, "observation_count": count,
                               "changed": previous is not None and previous != value}
                else:
                    return SUCCESS, None
            elif kind == "squad_status":
                if any(n not in (1, 2) or w != 0 for n, w, _ in fields(raw)):
                    raise ValueError("invalid GetStatusSquad request")
                result = (presence_reply("squad", self._squad(source, group))
                          if group is not None else presence_status_reply("squad"))
                return result, self._summary(kind, group)
            elif kind == "match_status":
                if any(n != 1 or w != 0 for n, w, _ in fields(raw)):
                    raise ValueError("invalid GetStatusMatchmake request")
                return presence_reply("matchmake", self._matchmake(source, group)), self._summary(kind, group)
            return SUCCESS, {**self._summary(kind, group), **details}

    def _summary(self, kind, group):
        return {"stage": "lobby_mvp_" + kind,
                "lobby_present": group is not None,
                "members": len(group.members) if group else 0,
                "queued": bool(group and group.queued),
                "group_count": len(self.groups)}
