"""Protocol-shaped public lobby discovery candidate, synthetic sessions only."""
import http.client
from pathlib import Path
import threading
import unittest
from types import SimpleNamespace
from uuid import UUID

from enable_lobby_rpc_probe import with_probe_routes
from enable_presence_menu_probe import add_probe_routes
from enable_presence_status_probe import TYPE_FIELD, modify_routes
from lobby_registry import HANDLERS, LobbyRegistry, public_lobby_presence_reply
from mvp_server import App, Server, make_handler, read_routes
from wwz_wire import blob, fields, scalar, string
import json
import tempfile

ROOT = Path(__file__).resolve().parents[1]
START = next(k for k, v in HANDLERS.items() if v == "start")
STOP = next(k for k, v in HANDLERS.items() if v == "stop")
SETTINGS = next(k for k, v in HANDLERS.items() if v == "settings")
GAMEDATA = next(k for k, v in HANDLERS.items() if v == "game_data")
MATCH = next(k for k, v in HANDLERS.items() if v == "match_status")
SUCCESS = scalar(1, 0)


def identity(i):
    return SimpleNamespace(user_guid=UUID(int=i),
                           auth=f"fake-auth-{i}", access=f"fake-access-{i}")


def start_req(name):
    return blob(1, scalar(1, 20)) + blob(2, scalar(1, 1)) + string(3, name)


def node(payload, number):
    return [data for n, wire, data in fields(payload) if n == number]


def unpack_presence(reply):
    assert node(reply, 1) == [0], "Expected ServiceResult.Success"
    wrappers = node(reply, TYPE_FIELD)
    assert len(wrappers) == 1
    responses = node(wrappers[0], 1)
    assert len(responses) == 1
    return responses[0]


class PublicLobbyDiscoveryTests(unittest.TestCase):
    def setup_registry(self):
        reg = LobbyRegistry()
        for i, name in enumerate(("citron", "switch", "third"), 1):
            reg.attach(name, identity(i))
        return reg

    def test_typed_start_exposes_host_squad_and_search_state(self):
        reg = self.setup_registry()
        reg.respond("citron", SETTINGS, blob(1, scalar(1, 4)))
        payload, info = reg.respond("citron", START, start_req("story-pve"),
                                    public_discovery=True)
        self.assertEqual("squad_and_matchmake", info["typed_status_response"])
        self.assertEqual("matching_queue_only", info["lobby_visibility"])
        presence = unpack_presence(payload)
        squad_response = node(presence, 2)[0]
        match_response = node(presence, 3)[0]
        self.assertEqual(1, len(node(node(squad_response, 2)[0], 2)))
        match_state = node(match_response, 4)[0]
        self.assertEqual([1], node(match_state, 1))  # msQueue
        self.assertEqual([b"story-pve"], node(match_state, 7))
        self.assertEqual(1, len(node(node(match_state, 5)[0], 2)))

    def test_typed_join_exposes_both_users_and_enables_future_status(self):
        reg = self.setup_registry()
        reg.respond("citron", START, start_req("story-pve"))
        reply, info = reg.respond("switch", START, start_req("story-pve"),
                                  public_discovery=True)
        self.assertEqual("joined_existing_queue", info["decision"])
        self.assertEqual(2, info["members"])
        presence = unpack_presence(reply)
        squad_members = node(node(node(presence, 2)[0], 2)[0], 2)
        queue = node(node(node(presence, 3)[0], 4)[0], 5)[0]
        self.assertEqual(2, len(squad_members))
        self.assertEqual(2, len(node(queue, 2)))
        self.assertEqual(1, reg._group("citron").roster_revision)
        self.assertEqual(1, reg._group("switch").roster_revision)

    def test_stop_and_property_mutation_have_safely_typed_snapshots(self):
        reg = self.setup_registry()
        data, info = reg.respond("citron", SETTINGS, blob(1, scalar(1, 4)),
                                 public_discovery=True)
        self.assertEqual([2], [n for n, w, v in fields(unpack_presence(data))])
        data, _ = reg.respond("citron", GAMEDATA, string(1, "{}"),
                              public_discovery=True)
        self.assertEqual([2], [n for n, w, v in fields(unpack_presence(data))])
        reg.respond("citron", START, start_req("story-pve"))
        data, info = reg.respond("citron", STOP, b"", public_discovery=True)
        match = node(node(unpack_presence(data), 3)[0], 4)[0]
        self.assertEqual([0], node(match, 1))  # msMenu
        self.assertEqual("not_queued", info["lobby_visibility"])

    def test_different_playlists_not_falsely_reported_as_visible(self):
        reg = self.setup_registry()
        reg.respond("citron", START, start_req("story-pve"),
                    public_discovery=True)
        result, info = reg.respond("switch", START, start_req("horde-pve"),
                                   public_discovery=True)
        self.assertEqual("playlist_differs", info["decision"])
        self.assertEqual(1, info["members"])
        self.assertEqual(2, info["group_count"])
        p = unpack_presence(result)
        self.assertEqual([b"horde-pve"], node(node(node(p, 3)[0], 4)[0], 7))
        self.assertEqual(1, len(reg._group("citron").members))

    def test_flag_off_keeps_success_only_wire_bytes(self):
        reg = self.setup_registry()
        data, _ = reg.respond("citron", START, start_req("story-pve"))
        self.assertEqual(SUCCESS, data)
        data, _ = reg.respond("citron", SETTINGS, blob(1, scalar(1, 4)))
        self.assertEqual(SUCCESS, data)

    def test_requires_session_safe_mode(self):
        for settings in ({}, {"lobby_mvp": True}, {"lobby_session_ids": True}):
            with self.subTest(settings=settings), self.assertRaises(ValueError):
                App({}, public_lobby_discovery=True, **settings)

    def test_real_http_typed_response_authenticates_two_clients(self):
        cfg = json.loads((ROOT / "routes.heartbeat-versions9.example.json").read_text())
        cfg = with_probe_routes(modify_routes(add_probe_routes(cfg)))
        with tempfile.TemporaryDirectory() as td:
            route_path = Path(td) / "routes.json"
            route_path.write_text(json.dumps(cfg))
            app = App(read_routes(route_path), lobby_mvp=True,
                      lobby_session_ids=True, public_lobby_discovery=True)
        alice, bob = identity(10), identity(11)
        source = app.source_key("127.0.0.1")
        for ident in (alice, bob):
            sid, _ = app.lobby_sessions.attach(source, ident)
            app.lobby_registry.attach(sid, ident)
        server = Server(("127.0.0.1", 0), make_handler(app))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            def post(ident, route, payload):
                client = http.client.HTTPConnection("127.0.0.1", server.server_port,
                                                     timeout=3)
                try:
                    client.request("POST", route, body=payload,
                                   headers={"Acl-Token": ident.access})
                    resp = client.getresponse()
                    return resp.status, resp.read()
                finally:
                    client.close()
            for ident in (alice, bob):
                status, body = post(ident, START, start_req("story-pve"))
                self.assertEqual(200, status)
                presence = unpack_presence(body)
                queue = node(node(node(presence, 3)[0], 4)[0], 5)[0]
                self.assertEqual(1 if ident is alice else 2, len(node(queue, 2)))
            self.assertEqual(1, len(app.lobby_registry.groups))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)


if __name__ == "__main__":
    unittest.main()
