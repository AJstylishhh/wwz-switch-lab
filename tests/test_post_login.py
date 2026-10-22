"""Offline post-login wire and state tests, no Switch credentials required."""
import unittest
import threading
from wwz_wire import blob, scalar, string, fields
import post_login_wire as wire
from post_login import PostLogin, inspect_request


class FakeQueue:
    def recognizes(self, token):
        return token == "queue-test"


class Identity:
    auth = "lab-auth-" + "a" * 43
    diagnostic = "lab-diagnostic-" + "b" * 43
    access = "lab-access-" + "c" * 43
    provider = "lab-provider-" + "d" * 43


class Sessions:
    lock = threading.RLock()
    identities = {"queue-test": Identity()}
    queue = FakeQueue()


class PostLoginTests(unittest.TestCase):
    def test_wire_results(self):
        for method, payload, field in (
            (wire.heartbeat_register_result(), 438369230, "register"),
            (wire.heartbeat_update_result(), 417677176, "update"),
            (wire.data_center_result(), 536714262, "center"),
            (wire.presence_connect_result(), 347012296, "presence"),
            (wire.refresh_tokens_result([Identity.auth], Identity.provider), 151915586, "refresh"),
        ):
            self.assertEqual([(1, 0), (payload, 2)],
                             [(n, w) for n, w, v in fields(method)], field)

    def test_post_login_sequence(self):
        handler = PostLogin(Sessions())
        version = string(1, "0.1.DEV.8802288/PREBUILD")
        items = [
            (wire.HEARTBEAT_REGISTER, version + scalar(2, 1) + scalar(3, 1), 438369230),
            (wire.HEARTBEAT_UPDATE, version + scalar(2, 1) + blob(3, b"\x0a\x00")
             + scalar(4, 1) + blob(5, b""), 417677176),
            (wire.DATACENTER_OCCUPATION, version, 536714262),
            (wire.PRESENCE_CONNECT, version + scalar(2, 1) + string(3, "static"), 347012296),
            (wire.REFRESH_TOKENS, string(1, Identity.auth) +
             string(1, Identity.diagnostic), 151915586),
            (wire.DIAGNOSTICS_WRITE, blob(1, b"sample") + blob(2, b"entries") +
             blob(3, string(2, "header")), None),
            (wire.HEARTBEAT_UNREGISTER, scalar(1, 1), None),
        ]
        for path, request, field in items:
            data, safe_info = handler.respond(path, request)
            expected = [(1, 0)] if field is None else [(1, 0), (field, 2)]
            self.assertEqual(expected, [(n, w) for n, w, v in fields(data)])
            self.assertNotIn(Identity.auth, str(safe_info))
        self.assertEqual(1, handler.diagnostic_packs)
        self.assertTrue(handler.presence_connected)

    def test_reject_unrecognized_refresh(self):
        handler = PostLogin(Sessions())
        with self.assertRaises(ValueError):
            handler.respond(wire.REFRESH_TOKENS, string(1, "not-issued"))
        with self.assertRaises(ValueError):
            handler.respond(wire.HEARTBEAT_REGISTER, b"\x08\x00")


if __name__ == "__main__":
    unittest.main()
