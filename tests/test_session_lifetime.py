"""Queue-ticket and authenticated-session lifetime regression tests.

Uses only synthetic tokens and clock; no Switch traffic or real credentials.
"""
import unittest

from auth_dequeue import AuthSessions
from post_login import PostLogin
import post_login_wire as wire
from wwz_wire import blob, fields, string


class Clock:
    def __init__(self):
        self.now = 0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class FakeQueue:
    def __init__(self, clock):
        self.clock = clock

    def recognizes(self, token):
        return token in ("queue-A", "queue-B") and self.clock.now < 300


def dequeue(token):
    return string(1, token) + blob(2, string(1, "PresenceService"))


def refresh_tokens(ident):
    return string(1, ident.auth) + string(1, ident.diagnostic)


class SessionLifetimeTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.queue = FakeQueue(self.clock)
        self.auth = AuthSessions(self.queue, clock=self.clock, session_ttl=3600, limit=3)
        self.post = PostLogin(self.auth)

    def sign_in(self, token):
        reply, info = self.auth.respond(
            dequeue(token), address="127.0.0.1", port=11704,
            name="PresenceService")
        self.assertEqual((1, 0, 0), next(fields(reply)))
        self.assertEqual(1, info["service_versions"])
        return self.auth.identities[token]

    def test_refresh_after_original_queue_ticket_expires(self):
        ident = self.sign_in("queue-A")
        self.clock.advance(301)
        self.assertFalse(self.queue.recognizes("queue-A"))
        reply, info = self.post.respond(wire.REFRESH_TOKENS, refresh_tokens(ident))
        self.assertEqual("refresh_tokens", info["stage"])
        self.assertEqual(2, info["tokens"])
        self.assertEqual((1, 0, 0), next(fields(reply)))
        # Refresh extends the authenticated idle lifetime.
        self.clock.advance(3500)
        self.assertIs(ident, self.auth.resolve_refresh_tokens([ident.auth]))

    def test_two_clients_are_isolated_even_after_queue_expiration(self):
        a = self.sign_in("queue-A")
        b = self.sign_in("queue-B")
        self.assertNotEqual(a.user_guid, b.user_guid)
        self.clock.advance(305)
        self.assertIs(a, self.auth.resolve_refresh_tokens([a.auth, a.diagnostic]))
        self.assertIs(b, self.auth.resolve_refresh_tokens([b.auth, b.diagnostic]))
        with self.assertRaisesRegex(ValueError, "Unrecognized refresh tokens"):
            self.auth.resolve_refresh_tokens([a.auth, b.diagnostic])
        self.assertEqual(2, len(self.auth.identities))

    def test_unrefreshed_session_expires_independently(self):
        ident = self.sign_in("queue-A")
        self.clock.advance(3601)
        with self.assertRaisesRegex(ValueError, "Unrecognized refresh tokens"):
            self.auth.resolve_refresh_tokens([ident.auth])
        self.assertFalse(self.auth.identities)
        self.assertFalse(self.auth.expirations)

    def test_queue_still_blocks_late_initial_dequeue(self):
        self.clock.advance(301)
        with self.assertRaisesRegex(ValueError, "expired queue"):
            self.sign_in("queue-A")
        self.assertFalse(self.auth.identities)

    def test_unknown_tokens_rejected_and_parameters_validated(self):
        ident = self.sign_in("queue-A")
        for tokens in ([], ["wrong"], [ident.auth, "wrong"], [ident.auth] * 4):
            with self.subTest(tokens=len(tokens)):
                with self.assertRaisesRegex(ValueError, "Unrecognized refresh tokens"):
                    self.auth.resolve_refresh_tokens(tokens)
        with self.assertRaises(ValueError):
            AuthSessions(self.queue, session_ttl=0)
        with self.assertRaises(ValueError):
            AuthSessions(self.queue, limit=0)


if __name__ == "__main__":
    unittest.main()
