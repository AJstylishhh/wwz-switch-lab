"""Identifying two WWZ clients behind one NAT without losing their squads."""
import http.client
import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from uuid import UUID

from enable_lobby_rpc_probe import with_probe_routes
from enable_presence_menu_probe import add_probe_routes
from enable_presence_status_probe import modify_routes
from lobby_identity import ClientSessionIndex, UnresolvedClient
from lobby_registry import LobbyRegistry, HANDLERS
from mvp_server import App, Server, make_handler, read_routes
from wwz_wire import blob, scalar, string

ROOT = Path(__file__).resolve().parents[1]
START = next(k for k, v in HANDLERS.items() if v == "start")


def identity(n):
    return SimpleNamespace(
        user_guid=UUID(int=n), auth=f"lab-auth-only-{n}",
        access=f"lab-access-only-{n}", diagnostic=f"lab-diagnostic-{n}")


def match_request(playlist):
    return blob(1, scalar(1, 42)) + blob(2, scalar(1, 1)) + string(3, playlist)


class FakeClock:
    def __init__(self):
        self.now = 0
    def __call__(self):
        return self.now


class ClientSessionIdentityTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.idx = ClientSessionIndex(clock=self.clock, ttl_seconds=100)
        self.registry = LobbyRegistry()

    def test_two_devices_same_ip_remain_separate_when_valid_tokens_present(self):
        a, b = identity(17), identity(18)
        sid_a, meta_a = self.idx.attach("same-router", a)
        self.registry.attach(sid_a, a)
        self.registry.respond(sid_a, START, match_request("same-playlist"))
        sid_b, meta_b = self.idx.attach("same-router", b)
        self.registry.attach(sid_b, b)
        self.assertNotEqual(sid_a, sid_b)
        self.assertFalse(meta_a["another_session_on_source"])
        self.assertTrue(meta_b["another_session_on_source"])
        self.assertEqual(1, len(self.registry.groups))
        self.assertEqual(2, len(self.idx.sessions))
        for token, expected in ((a.auth, sid_a), (b.auth, sid_b)):
            source_id, via = self.idx.resolve(
                "same-router", {"Authorization": "Bearer " + token})
            self.assertEqual(expected, source_id)
            self.assertEqual("issued_token", via["identity_resolution"])
        sid, _ = self.idx.resolve("same-router", {"AuthorizationToken": b.auth})
        _, result = self.registry.respond(sid, START, match_request("same-playlist"))
        self.assertEqual("joined_existing_queue", result["decision"])
        self.assertEqual(2, result["members"])
        self.assertEqual(1, result["group_count"])

    def test_ambiguous_same_ip_without_token_fails_closed(self):
        a, b = identity(17), identity(18)
        self.idx.attach("same-router", a)
        self.idx.attach("same-router", b)
        with self.assertRaisesRegex(UnresolvedClient, "ambiguous shared-NAT"):
            self.idx.resolve("same-router", {})
        with self.assertRaisesRegex(UnresolvedClient, "unrecognized"):
            self.idx.resolve("same-router", {"Authorization": "Bearer bad-token"})
        with self.assertRaisesRegex(UnresolvedClient, "unrecognized"):
            self.idx.resolve("same-router", {"AuthorizationToken": a.diagnostic})
        # Distinct source with one login doesn't require a bearer.
        self.idx.attach("remote-network", identity(20))
        sid, via = self.idx.resolve("remote-network", {})
        self.assertEqual("unique_source", via["identity_resolution"])
        self.assertIsInstance(sid, str)

    def test_repeated_dequeue_same_user_does_not_create_new_session(self):
        a = identity(17)
        sid, info = self.idx.attach("same-router", a)
        same, again = self.idx.attach("same-router", a)
        self.assertEqual(sid, same)
        self.assertEqual(1, len(self.idx.sessions))
        self.assertFalse(info["another_session_on_source"])
        self.assertFalse(again["another_session_on_source"])
        self.assertEqual(1, again["same_network_source_sessions"])
        self.assertNotIn(a.auth, str(again))
        self.assertNotIn(str(a.user_guid), str(again))

    def test_valid_bearer_survives_network_change(self):
        a = identity(17)
        sid, _ = self.idx.attach("old-net", a)
        resolved, details = self.idx.resolve("new-net", {"X-Auth-Token": a.auth})
        self.assertEqual(sid, resolved)
        self.assertEqual("issued_token", details["identity_resolution"])
        self.assertEqual((sid, "unique_source"),
                         (lambda r: (r[0], r[1]["identity_resolution"]))(
                             self.idx.resolve("new-net", {})))

    def test_expired_sessions_and_invalid_config(self):
        a = identity(17)
        self.idx.attach("same-router", a)
        self.clock.now = 101
        with self.assertRaisesRegex(UnresolvedClient, "no signed-in"):
            self.idx.resolve("same-router", {})
        self.assertEqual(0, len(self.idx.sessions))
        for kwargs in ({"ttl_seconds": 0}, {"max_sessions": 0}):
            with self.assertRaises(ValueError):
                ClientSessionIndex(**kwargs)

    def test_real_http_handler_handles_issued_header_and_rejects_ambiguity(self):
        conf = json.loads((ROOT / "routes.heartbeat-versions9.example.json").read_text())
        conf = with_probe_routes(modify_routes(add_probe_routes(conf)))
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "routes.json"
            path.write_text(json.dumps(conf))
            routes = read_routes(path)
        app = App(routes, lobby_mvp=True, lobby_session_ids=True)
        a, b = identity(17), identity(18)
        network = app.source_key("127.0.0.1")
        for who in (a, b):
            sid, _ = app.lobby_sessions.attach(network, who)
            app.lobby_registry.attach(sid, who)
        server = Server(("127.0.0.1", 0), make_handler(app))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            def request(payload, token=None):
                conn = http.client.HTTPConnection("127.0.0.1", server.server_port,
                                                  timeout=3)
                try:
                    headers = {"Authorization": "Bearer " + token} if token else {}
                    conn.request("POST", START, body=payload, headers=headers)
                    response = conn.getresponse()
                    return response.status, response.read()
                finally:
                    conn.close()
            self.assertEqual((409, b"Ambiguous lab session"),
                             request(match_request("public")))
            self.assertEqual((200, bytes((8, 0))),
                             request(match_request("public"), a.auth))
            self.assertEqual((200, bytes((8, 0))),
                             request(match_request("public"), b.auth))
            self.assertEqual(1, len(app.lobby_registry.groups))
            group = next(iter(app.lobby_registry.groups.values()))
            self.assertEqual(2, len(group.members))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)


if __name__ == "__main__":
    unittest.main()
