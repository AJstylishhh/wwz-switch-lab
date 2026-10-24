"""Opt-in typed user-public-data experiment; all tests use synthetic users."""
import http.client
import threading
import unittest
from types import SimpleNamespace
from uuid import UUID

from lobby_registry import HANDLERS, user_id
from mvp_server import App, Server, make_handler
from post_match_user_probe import parse_lookup_user_ids
from public_user_data import USER_BASE_DATA_RESULT_FIELD, public_user_data_reply
from request_shape import POST_MATCH_USER_LOOKUP_CANDIDATE as RPC
from wwz_wire import blob, scalar, fields, string

START = next(path for path, method in HANDLERS.items() if method == "start")


def identity(i):
    return SimpleNamespace(
        user_guid=UUID(int=i), auth="synthetic-auth-" + str(i),
        access="synthetic-access-" + str(i))


def request(*uids):
    return b"".join(blob(1, user_id(uid)) for uid in uids)


def start(playlist):
    return blob(1, scalar(1, 10)) + blob(2, scalar(1, 1)) + string(3, playlist)


def select(raw, field):
    return [data for n, _, data in fields(raw) if n == field]


class PublicUserDataTests(unittest.TestCase):
    def test_typed_envelope_contains_correct_user_and_synthetic_nickname(self):
        a, b = identity(1), identity(2)
        response, meta = public_user_data_reply(
            request(a.user_guid, b.user_guid), {a.user_guid: a, b.user_guid: b})
        self.assertEqual([0], select(response, 1))
        typed = select(response, USER_BASE_DATA_RESULT_FIELD)
        self.assertEqual(1, len(typed))
        records = select(typed[0], 1)
        self.assertEqual(2, len(records))
        for record, ident in zip(records, (a, b)):
            self.assertEqual([user_id(ident.user_guid)], select(record, 1))
            self.assertEqual(["WWZ Lab " + ident.user_guid.hex[:8]],
                             [text.decode("utf8") for text in select(record, 2)])
        self.assertEqual(2, meta["result_records"])
        self.assertNotIn(a.auth, str(meta))

    def test_nonmember_id_fails_closed(self):
        a = identity(3)
        with self.assertRaises(ValueError):
            public_user_data_reply(request(a.user_guid, UUID(int=99)),
                                   {a.user_guid: a})

    def test_flag_requires_session_safe_mode(self):
        for options in ({}, {"lobby_mvp": True}, {"lobby_session_ids": True}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                App({}, experimental_public_user_data=True, **options)
        self.assertTrue(App({}, lobby_mvp=True, lobby_session_ids=True,
                            experimental_public_user_data=True).experimental_public_user_data)

    def test_http_authenticated_same_lobby_gets_typed_response(self):
        app = App({}, lobby_mvp=True, lobby_session_ids=True,
                  experimental_public_user_data=True)
        a, b, c = identity(101), identity(102), identity(103)
        for n, ident in enumerate((a, b, c)):
            sid, _ = app.lobby_sessions.attach("address-" + str(n), ident)
            app.lobby_registry.attach(sid, ident)
            if n == 0:
                alice_sid = sid
            elif n == 1:
                bob_sid = sid
        app.lobby_registry.respond(alice_sid, START, start("one-mode"))
        app.lobby_registry.respond(bob_sid, START, start("one-mode"))
        server = Server(("127.0.0.1", 0), make_handler(app))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            def send(body, token=None):
                conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
                try:
                    conn.request("POST", RPC, body=body, headers=(
                        {"acl-token": token} if token else {}))
                    response = conn.getresponse()
                    return response.status, response.read()
                finally:
                    conn.close()
            status, data = send(request(b.user_guid), a.access)
            self.assertEqual(200, status)
            self.assertEqual([0], select(data, 1))
            self.assertEqual(1, len(select(select(data, USER_BASE_DATA_RESULT_FIELD)[0], 1)))
            for body, token in (
                    (request(b.user_guid), "invalid-token"),
                    (request(c.user_guid), a.access),
                    (request(b.user_guid), None),
                    (b"\x0a\x20\xff", a.access)):
                self.assertEqual(404, send(body, token)[0])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

    def test_no_flag_keeps_unknown_404(self):
        app = App({}, lobby_mvp=True, lobby_session_ids=True)
        server = Server(("127.0.0.1", 0), make_handler(app))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            c = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
            try:
                c.request("POST", RPC, body=request(identity(1).user_guid))
                self.assertEqual(404, c.getresponse().status)
            finally:
                c.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)


if __name__ == "__main__":
    unittest.main()
