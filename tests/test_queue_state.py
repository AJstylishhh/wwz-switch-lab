"""Queue state and schema tests (no real credentials or Switch required)."""
import unittest
from queue_state import QueueState, inspect_enqueue
from wwz_wire import blob, string, fields


def request(password=b"secret-sensitive-data"):
    return (blob(1, string(1, "Retail")) + blob(2, b"a"*16) +
            blob(3, password) + blob(4, b"provider") +
            blob(5, blob(1, b"signature")) + blob(6, b"2026"))


def token_from_response(raw):
    wrapper = next(v for n,w,v in fields(raw) if n == 262225376)
    position = next(v for n,w,v in fields(wrapper) if n == 1)
    queue = next(v for n,w,v in fields(position) if n == 1)
    return next(v for n,w,v in fields(queue) if n == 1).decode()


class QueueTests(unittest.TestCase):
    def test_shape_and_secret_redaction(self):
        info=inspect_enqueue(request())
        self.assertEqual([8,16,21,8,11,4],info["field_sizes"])
        self.assertNotIn("secret",repr(info))

    def test_repeats_same_token_and_changes_by_request(self):
        s=QueueState()
        first=s.issue(request())
        second=s.issue(request())
        self.assertEqual(first,second)
        self.assertNotEqual(first,s.issue(request(b"different")))
        self.assertTrue(s.recognizes(token_from_response(first)))

    def test_expiry_and_eviction(self):
        now=[10]
        s=QueueState(ttl=5,limit=1,clock=lambda:now[0])
        token=token_from_response(s.issue(request()))
        now[0]=16
        self.assertFalse(s.recognizes(token))
        self.assertNotEqual(token,token_from_response(s.issue(request())))
        second=token_from_response(s.issue(request()))
        s.issue(request(b"another"))
        self.assertFalse(s.recognizes(second))

    def test_bad_wire_data_rejected(self):
        s=QueueState()
        with self.assertRaises(ValueError):s.issue(b"\x08\x00")
        with self.assertRaises(ValueError):s.issue(request()[:-1])


if __name__=="__main__":
    unittest.main()
