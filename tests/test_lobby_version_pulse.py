"""Synthetic, loopback-only test of roster-driven heartbeat version pulses."""
import http.client
from pathlib import Path
from types import SimpleNamespace
import threading
import unittest
from uuid import UUID

from lobby_registry import HANDLERS
from lobby_version_pulse import EXPERIMENTAL_SLOTS, pulse_versions, client_reported_versions
from mvp_server import App, Server, make_handler, read_routes
from post_login_wire import HEARTBEAT_UPDATE
from wwz_wire import blob, fields, scalar, string

ROOT = Path(__file__).resolve().parents[1]
START = next(path for path, kind in HANDLERS.items() if kind == "start")
STOP = next(path for path, kind in HANDLERS.items() if kind == "stop")
GAMEDATA = next(path for path, kind in HANDLERS.items() if kind == "game_data")
BASE = [8802288] * 9


def user(n):
    return SimpleNamespace(
        user_guid=UUID(int=n), auth=f"test-auth-{n}",
        access=f"test-access-{n}")


def playlist(name):
    return blob(1, scalar(1, 20)) + blob(2, scalar(1, 1)) + string(3, name)


def values(reply):
    def part(raw, number):
        return next(data for n, wire, data in fields(raw)
                    if (n, wire) == (number, 2))
    envelope = part(reply, 417677176)
    result = part(envelope, 1)
    version_message = part(result, 1)
    return [v for n, wire, v in fields(version_message) if (n, wire) == (1, 0)]


class LobbyVersionPulseTests(unittest.TestCase):
    def setup_app(self, enable=True):
        routes = read_routes(ROOT / "routes.heartbeat-versions9.example.json")
        app = App(routes, lobby_mvp=True, lobby_session_ids=True,
                  lobby_version_pulse=enable)
        a, b, c = user(11), user(12), user(13)
        ids = {}
        for who in (a, b, c):
            sid, _ = app.lobby_sessions.attach(app.source_key("127.0.0.1"), who)
            app.lobby_registry.attach(sid, who)
            ids[who.user_guid] = sid
        return app, (a, b, c), ids

    def test_client_heartbeat_version_vector_is_parsed_without_other_data(self):
        raw = (string(1, "fake-build") + scalar(2, 1) +
               blob(5, b"".join(scalar(1, v) for v in BASE)))
        self.assertEqual(tuple(BASE), client_reported_versions(raw))
        self.assertIsNone(client_reported_versions(string(1, "fake-build")))
        self.assertIsNone(client_reported_versions(blob(5, string(3, "bad"))))

    def test_pulse_ack_transition_logged_once_per_session(self):
        app, (a, b, _), ids = self.setup_app()
        app.lobby_registry.respond(ids[a.user_guid], START, playlist("campaign"))
        app.lobby_registry.respond(ids[b.user_guid], START, playlist("campaign"))
        before = blob(5, b"".join(scalar(1, v) for v in BASE))
        after = blob(5, b"".join(scalar(1, v) for v in pulse_versions(BASE, 1)))
        with self.assertLogs("wwz.mvp", level="INFO") as captured:
            app.heartbeat_versions_for("127.0.0.1", {"Acl-Token": a.access}, BASE, before)
            app.heartbeat_versions_for("127.0.0.1", {"Acl-Token": a.access}, BASE, before)
            app.heartbeat_versions_for("127.0.0.1", {"Acl-Token": a.access}, BASE, after)
            app.heartbeat_versions_for("127.0.0.1", {"Acl-Token": a.access}, BASE, after)
        self.assertEqual(2, len(captured.output))
        self.assertIn("'client_reports_baseline': True", captured.output[0])
        self.assertIn("'client_reports_pulsed': True", captured.output[1])

    def test_nine_entry_shape_and_no_mutation(self):
        self.assertEqual(tuple(BASE), pulse_versions(BASE, 0))
        observed = pulse_versions(BASE, 3)
        self.assertEqual(9, len(observed))
        self.assertEqual([8802288] * 9, BASE)
        for idx in range(9):
            self.assertEqual(8802288 + (3 if idx in EXPERIMENTAL_SLOTS else 0),
                             observed[idx])
        with self.assertRaisesRegex(ValueError, "nine baseline"):
            pulse_versions([1, 2, 3], 1)
        with self.assertRaises(ValueError):
            pulse_versions(BASE, -1)
        with self.assertRaises(ValueError):
            pulse_versions([2**63 - 1] * 9, 1)

    def test_requires_session_safe_opt_in(self):
        with self.assertRaises(ValueError):
            App({}, lobby_version_pulse=True)
        with self.assertRaises(ValueError):
            App({}, lobby_mvp=True, lobby_version_pulse=True)
        self.assertTrue(App({}, lobby_mvp=True, lobby_session_ids=True,
                            lobby_version_pulse=True).lobby_version_pulse)

    def test_only_verified_member_after_merge_receives_revision(self):
        app, (a, b, c), ids = self.setup_app()
        lookup = lambda who: app.heartbeat_versions_for(
            "127.0.0.1", {"Acl-Token": who.access}, BASE)
        self.assertEqual(tuple(BASE), lookup(a))
        self.assertEqual(tuple(BASE), lookup(b))
        app.lobby_registry.respond(ids[a.user_guid], START, playlist("story"))
        self.assertEqual(tuple(BASE), lookup(a))
        app.lobby_registry.respond(ids[b.user_guid], START, playlist("story"))
        expected = pulse_versions(BASE, 1)
        self.assertEqual(expected, lookup(a))
        self.assertEqual(expected, lookup(b))
        self.assertEqual(tuple(BASE), lookup(c))
        self.assertEqual(BASE, app.heartbeat_versions_for(
            "127.0.0.1", {"Acl-Token": "bad"}, BASE))
        self.assertEqual(BASE, app.heartbeat_versions_for(
            "127.0.0.1", {}, BASE))  # same public IP must NOT suffice
        app.lobby_registry.respond(ids[a.user_guid], GAMEDATA, string(1, "new metadata"))
        self.assertEqual(expected, lookup(a))
        self.assertEqual(expected, lookup(b))
        # Stopping one member does not stop the other; remaining member
        # gets one more roster-change pulse, and stopper returns to baseline.
        app.lobby_registry.respond(ids[b.user_guid], STOP, b"")
        self.assertEqual(pulse_versions(BASE, 2), lookup(a))
        self.assertEqual(tuple(BASE), lookup(b))

    def test_actual_http_heartbeat_reply_changes_only_after_merge(self):
        app, (a, b, _) , ids = self.setup_app()
        server = Server(("127.0.0.1", 0), make_handler(app))
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        raw = (string(1, "0.1.DEV.8802288/PREBUILD") +
               scalar(2, 1) + scalar(4, 1) + blob(5, b""))
        def request(token):
            conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
            try:
                conn.request("POST", HEARTBEAT_UPDATE, body=raw,
                             headers={"Acl-Token": token})
                res = conn.getresponse()
                return res.status, values(res.read())
            finally:
                conn.close()
        try:
            self.assertEqual((200, BASE), request(a.access))
            app.lobby_registry.respond(ids[a.user_guid], START, playlist("public"))
            app.lobby_registry.respond(ids[b.user_guid], START, playlist("public"))
            self.assertEqual((200, list(pulse_versions(BASE, 1))), request(a.access))
            self.assertEqual((200, list(pulse_versions(BASE, 1))), request(b.access))
            self.assertEqual((200, BASE), request("invalid-token"))
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=3)

    def test_disabled_flag_returns_original_versions(self):
        app, (a, b, _), ids = self.setup_app(enable=False)
        app.lobby_registry.respond(ids[a.user_guid], START, playlist("story"))
        app.lobby_registry.respond(ids[b.user_guid], START, playlist("story"))
        self.assertEqual(BASE, app.heartbeat_versions_for(
            "127.0.0.1", {"Acl-Token": a.access}, BASE))


if __name__ == "__main__":
    unittest.main()
