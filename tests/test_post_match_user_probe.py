"""The post-match probe never emits IDs, credentials or fabricated replies."""
import http.client
import logging
import threading
import unittest
from types import SimpleNamespace
from uuid import UUID

from auth_dequeue import Identity
from lobby_registry import user_id
from mvp_server import App, Server, make_handler
from post_match_user_probe import classify_lookup, parse_lookup_user_ids
from request_shape import POST_MATCH_USER_LOOKUP_CANDIDATE
from wwz_wire import blob


def make_request(*uids):
    return b"".join(blob(1, user_id(uid)) for uid in uids)


def make_identity(number):
    return SimpleNamespace(
        user_guid=UUID(int=number),
        auth=f"lab-authorization-{number}",
        access=f"lab-access-role-{number}")


class PostMatchUserProbeTests(unittest.TestCase):
    def test_one_user_id_is_22_bytes_and_roundtrips(self):
        a, b = UUID(int=17), UUID(int=18)
        self.assertEqual(22, len(make_request(a)))
        self.assertEqual(44, len(make_request(a, b)))
        self.assertEqual((a, b), parse_lookup_user_ids(make_request(a, b)))

    def test_verified_requester_looks_up_other_issued_user(self):
        a, b = make_identity(17), make_identity(18)
        result = classify_lookup(make_request(b.user_guid), (a, b), a.access)
        self.assertEqual({
            "format": "user_ids", "requested_records": 1,
            "distinct_requested_users": 1, "issued_user_matches": 1,
            "unknown_user_ids": 0, "requester_verified": True,
            "includes_requester": False, "other_issued_users_requested": 1,
        }, result)
        self.assertNotIn(a.auth, str(result))
        self.assertNotIn(a.access, str(result))
        self.assertNotIn(str(b.user_guid), str(result))

    def test_own_unknown_and_duplicate_requests_are_distinguished(self):
        a, b = make_identity(17), make_identity(18)
        own = classify_lookup(make_request(a.user_guid), (a, b), a.auth)
        self.assertTrue(own["includes_requester"])
        self.assertEqual(0, own["other_issued_users_requested"])
        unknown = classify_lookup(make_request(UUID(int=99)), (a, b), a.auth)
        self.assertEqual(1, unknown["unknown_user_ids"])
        self.assertFalse(unknown["includes_requester"])
        repeated = classify_lookup(make_request(b.user_guid, b.user_guid),
                                   (a, b), a.access)
        self.assertEqual(2, repeated["requested_records"])
        self.assertEqual(1, repeated["distinct_requested_users"])

    def test_only_issued_tokens_resolve_caller(self):
        a, b = make_identity(17), make_identity(18)
        for token in (None, "arbitrary-third-party-token", a.auth + "x"):
            result = classify_lookup(make_request(b.user_guid), (a, b), token)
            self.assertFalse(result["requester_verified"])
            self.assertNotIn("includes_requester", result)

    def test_nonmatching_shapes_never_create_inferred_profile(self):
        valid = make_request(UUID(int=1))
        malformed = (
            b"", b"\x0a\x20\xff", valid + b"\x10\x01",
            blob(2, user_id(UUID(int=1))), valid * 17,
        )
        for payload in malformed:
            with self.subTest(length=len(payload)):
                self.assertEqual({"format": "unrecognized"},
                                 classify_lookup(payload, (), None))
        # Unrecognized is not proof this is the real IUserService method.

    def test_http_probe_keeps_404_and_logs_only_counts(self):
        app = App({}, trace_post_match_users=True)
        a = make_identity(17)
        ident = Identity(a.auth, "unused-diagnostic", a.access,
                         "unused-provider", a.user_guid, "lab-test")
        with app.auth_sessions.lock:
            app.auth_sessions.identities["synthetic-queue"] = ident
            app.auth_sessions.expirations["synthetic-queue"] = (
                app.auth_sessions.clock() + 3600)
        server = Server(("127.0.0.1", 0), make_handler(app))
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            with self.assertLogs("wwz.mvp", level="INFO") as captured:
                conn = http.client.HTTPConnection("127.0.0.1", server.server_port,
                                                  timeout=3)
                try:
                    conn.request(
                        "POST", POST_MATCH_USER_LOOKUP_CANDIDATE,
                        body=make_request(a.user_guid),
                        headers={"acl-token": a.access})
                    response = conn.getresponse()
                    self.assertEqual(404, response.status)
                    self.assertEqual(b"Unknown RPC", response.read())
                finally:
                    conn.close()
            events = "\n".join(captured.output)
            self.assertIn("Post-match user lookup correlation:", events)
            self.assertIn("'includes_requester': True", events)
            self.assertIn("'issued_user_matches': 1", events)
            self.assertNotIn(a.auth, events)
            self.assertNotIn(a.access, events)
            self.assertNotIn(str(a.user_guid), events)
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=3)


if __name__ == "__main__":
    unittest.main()
