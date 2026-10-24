"""Opt-in WWZ lobby registry tests with synthetic identities and loopback HTTP."""
import http.client
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID
import tempfile
import threading
import unittest

from enable_lobby_rpc_probe import with_probe_routes
from enable_presence_menu_probe import add_probe_routes
from enable_presence_status_probe import modify_routes, TYPE_FIELD, SERVICE
from lobby_registry import HANDLERS, LobbyRegistry, matchmake_playlist, presence_reply
from mvp_server import App, Server, make_handler, read_routes
from wwz_wire import blob, fields, scalar, string

ROOT = Path(__file__).resolve().parents[1]
SQUAD = "/" + SERVICE + ".svc/44106e2a072d4667999b814b3207e195"
MATCH = "/" + SERVICE + ".svc/2896c4aa256e4e7290454ef6df3f1ce9"
START = "/" + SERVICE + ".svc/67cdaf75ca604bd993ad9f1db0c3f812"
STOP = "/" + SERVICE + ".svc/f9dcd75c457145e7a8b4d5e619171fc1"
SETTINGS = "/" + SERVICE + ".svc/5df1122df8884a408c2b804153dc90f1"
GAMEDATA = "/" + SERVICE + ".svc/44a718e4c7514684b5259e0879e98c63"
INVITES = "/" + SERVICE + ".svc/dfd72da619924665a51e16f74e813f13"


def node(data, n):
    return [value for f, wire, value in fields(data) if f == n]


def presence_part(response, type_number):
    assert node(response, 1) == [0]
    payload = node(response, TYPE_FIELD)[0]
    return node(node(payload, 1)[0], type_number)[0]


def playlist(name):
    return (blob(1, scalar(1, 14) + scalar(2, 30)) +
            blob(2, scalar(1, 1) + scalar(2, 1)) +
            string(3, name) +
            blob(4, blob(1, string(1, "variant"))))


class Clock:
    def __init__(self):
        self.now = 1000

    def __call__(self):
        return self.now

    def advance(self, sec):
        self.now += sec


class LobbyRegistryTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.reg = LobbyRegistry(clock=self.clock, idle_seconds=100)
        self.alice = SimpleNamespace(user_guid=UUID(int=1))
        self.bob = SimpleNamespace(user_guid=UUID(int=2))
        self.chris = SimpleNamespace(user_guid=UUID(int=3))
        for source, ident in (("source-A", self.alice), ("source-B", self.bob),
                              ("source-C", self.chris)):
            self.reg.attach(source, ident)

    def test_two_matchmaking_clients_share_one_group_and_typed_members(self):
        _, info = self.reg.respond("source-A", SETTINGS, blob(1, scalar(1, 4)))
        self.assertEqual(1, info["members"])
        self.reg.respond("source-A", GAMEDATA, string(1, '{"mode":"public"}'))
        self.reg.respond("source-A", INVITES, scalar(1, 0))
        self.reg.respond("source-A", START, playlist("WWZ-public"))
        _, info = self.reg.respond("source-B", START, playlist("WWZ-public"))
        self.assertEqual({"members": 2, "group_count": 1},
                         {k: info[k] for k in ("members", "group_count")})
        self.assertEqual(self.reg.member_group["source-A"],
                         self.reg.member_group["source-B"])
        squad, meta = self.reg.respond("source-A", SQUAD, scalar(1, 0) + scalar(2, 0))
        self.assertEqual(2, meta["members"])
        squad_status = node(presence_part(squad, 2), 2)[0]
        member_records = node(squad_status, 2)
        self.assertEqual(2, len(member_records))
        self.assertEqual([1, 0], [node(m, 2)[0] for m in member_records])
        self.assertEqual([b'{"mode":"public"}'], node(squad_status, 1))
        queue_response, state = self.reg.respond("source-B", MATCH, scalar(1, 0))
        mm_status = node(presence_part(queue_response, 3), 4)[0]
        self.assertEqual([1], node(mm_status, 1))  # msQueue, not fabricated msGame
        queue = node(mm_status, 5)[0]
        self.assertEqual(2, len(node(queue, 2)))
        self.assertEqual([b"WWZ-public"], node(mm_status, 7))
        self.assertTrue(state["queued"])

    def test_different_playlists_never_merge(self):
        self.reg.respond("source-A", START, playlist("campaign"))
        self.reg.respond("source-B", START, playlist("horde"))
        self.assertEqual(2, len(self.reg.groups))
        self.reg.respond("source-C", START, playlist("campaign"))
        self.assertEqual(self.reg.member_group["source-A"],
                         self.reg.member_group["source-C"])
        self.assertNotEqual(self.reg.member_group["source-A"],
                            self.reg.member_group["source-B"])

    def test_stop_no_auto_publish_and_ttl(self):
        self.reg.respond("source-A", SETTINGS, blob(1, scalar(1, 4)))
        self.assertEqual(1, len(self.reg.groups))
        # B has no queued lobby to join; a local squad is not globally public.
        self.reg.respond("source-B", START, playlist("open"))
        self.assertEqual(2, len(self.reg.groups))
        self.reg.respond("source-B", STOP, b"")
        response, info = self.reg.respond("source-B", MATCH, scalar(1, 0))
        mm_status = node(presence_part(response, 3), 4)[0]
        self.assertEqual([0], node(mm_status, 1))  # msMenu after Stop
        self.assertFalse(info["queued"])
        self.clock.advance(101)
        response, info = self.reg.respond("source-B", SQUAD, b"")
        self.assertEqual(0, info["group_count"])
        self.assertFalse(info["lobby_present"])

    def test_malformed_and_unauthenticated_calls_fail_without_creating_lobbies(self):
        with self.assertRaisesRegex(ValueError, "Dequeue"):
            self.reg.respond("unknown", START, playlist("public"))
        for path, raw in ((SETTINGS, b"\x08\x03"),
                          (INVITES, string(1, "wrong")),
                          (START, b"\x08\x01"),
                          (MATCH, b"\x12\x00"),
                          (STOP, scalar(1, 1)),
                          (GAMEDATA, b"\x12\x02hi")):
            with self.subTest(path=path):
                with self.assertRaises(ValueError):
                    self.reg.respond("source-A", path, raw)
        self.assertFalse(self.reg.groups)

    def test_relogin_changes_identity_and_prevents_old_membership(self):
        self.reg.respond("source-A", START, playlist("public"))
        old_group = self.reg.member_group["source-A"]
        self.reg.attach("source-A", SimpleNamespace(user_guid=UUID(int=99)))
        self.assertNotIn(old_group, self.reg.groups)
        self.assertNotIn("source-A", self.reg.member_group)

    def test_no_flags_preserves_original_probe_responses(self):
        with tempfile.TemporaryDirectory() as tmp:
            route = Path(tmp) / "routes.json"
            config = json.loads((ROOT/"routes.heartbeat-versions9.example.json").read_text())
            config = with_probe_routes(modify_routes(add_probe_routes(config)))
            route.write_text(json.dumps(config))
            decoded = read_routes(route)
        app = App(decoded)
        server = Server(("127.0.0.1", 0), make_handler(app))
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
            try:
                conn.request("POST", START, body=playlist("public"))
                response = conn.getresponse()
                self.assertEqual(200, response.status)
                self.assertEqual(b"\x08\x00", response.read())
            finally:
                conn.close()
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=3)

    def test_opt_in_http_writes_and_dynamic_reads(self):
        with tempfile.TemporaryDirectory() as tmp:
            route = Path(tmp) / "routes.json"
            config = json.loads((ROOT/"routes.heartbeat-versions9.example.json").read_text())
            config = with_probe_routes(modify_routes(add_probe_routes(config)))
            route.write_text(json.dumps(config))
            decoded = read_routes(route)
        app = App(decoded, lobby_mvp=True)
        app.lobby_registry.attach(app.source_key("127.0.0.1"), self.alice)
        server = Server(("127.0.0.1", 0), make_handler(app))
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            for path, payload in ((SETTINGS, blob(1, scalar(1, 4))),
                                  (START, playlist("public"))):
                conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
                try:
                    conn.request("POST", path, body=payload)
                    reply = conn.getresponse()
                    self.assertEqual(200, reply.status)
                    self.assertEqual(b"\x08\x00", reply.read())
                finally:
                    conn.close()
            conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
            try:
                conn.request("POST", MATCH, body=scalar(1, 0))
                resp = conn.getresponse()
                self.assertEqual(200, resp.status)
                data = resp.read()
                self.assertIn(TYPE_FIELD, [n for n, w, v in fields(data)])
                self.assertEqual([1], node(node(presence_part(data, 3), 4)[0], 1))
            finally:
                conn.close()
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=3)


if __name__ == "__main__":
    unittest.main()
