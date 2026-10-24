"""Privacy-limited matchmaking decision diagnostics and unknown scalar cadence."""
from types import SimpleNamespace
from uuid import UUID
import unittest

from lobby_registry import LobbyRegistry, MAX_PLAYERS, HANDLERS
from wwz_wire import blob, scalar, string

START = next(p for p, v in HANDLERS.items() if v == "start")
SETTINGS = next(p for p, v in HANDLERS.items() if v == "settings")
OBSERVED = next(p for p, v in HANDLERS.items() if v == "observed_scalar")


def match_request(playlist):
    return blob(1, scalar(1, 11)) + blob(2, scalar(1, 1)) + string(3, playlist)


class LobbyMatchingDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.reg = LobbyRegistry()
        for name, n in (("A", 1), ("B", 2), ("C", 3)):
            self.reg.attach(name, SimpleNamespace(user_guid=UUID(int=n)))

    def test_observed_mismatched_playlists_are_distinguishable_without_contents(self):
        _, a = self.reg.respond("A", START, match_request("different-secret-alpha"))
        _, b = self.reg.respond("B", START, match_request("different-secret-beta"))
        self.assertEqual("no_other_queue", a["decision"])
        self.assertEqual("playlist_differs", b["decision"])
        self.assertEqual(1, b["other_queued_groups"])
        self.assertEqual(0, b["same_playlist_groups"])
        self.assertNotEqual(a["playlist_tag"], b["playlist_tag"])
        self.assertNotIn("different-secret-alpha", str(a))
        self.assertNotIn("different-secret-beta", str(b))
        self.assertEqual(2, b["group_count"])

    def test_matching_playlist_joins_even_when_request_wrapper_differs(self):
        self.reg.respond("A", START, match_request("same-playlist"))
        second = (blob(1, scalar(1, 123) + scalar(2, 456)) +
                  blob(2, scalar(1, 0)) + string(3, "same-playlist") +
                  blob(4, string(1, "extra-variant")))
        _, b = self.reg.respond("B", START, second)
        self.assertEqual("joined_existing_queue", b["decision"])
        self.assertEqual(1, b["same_playlist_groups"])
        self.assertEqual(1, b["same_playlist_open_seats"])
        self.assertEqual(2, b["members"])
        self.assertEqual(1, b["group_count"])

    def test_a_real_one_seat_limit_is_reported_not_silently_bypassed(self):
        _, settings = self.reg.respond("A", SETTINGS, blob(1, scalar(1, 1)))
        self.assertEqual(1, settings["max_count"])
        self.reg.respond("A", START, match_request("common"))
        _, b = self.reg.respond("B", START, match_request("common"))
        self.assertEqual("matching_queue_full", b["decision"])
        self.assertEqual(1, b["same_playlist_groups"])
        self.assertEqual(0, b["same_playlist_open_seats"])
        self.assertEqual(2, b["group_count"])

    def test_ambiguous_scalar_request_never_changes_reply_wire_or_lobby_state(self):
        for i in range(1, 42):
            result, details = self.reg.respond("A", OBSERVED, scalar(1, 2))
            self.assertEqual(b"\x08\x00", result)
            if i in (1, 20, 40):
                self.assertIsNotNone(details)
                self.assertEqual(2, details["observed_value"])
                self.assertEqual(i, details["observation_count"])
            else:
                self.assertIsNone(details)
        result, details = self.reg.respond("A", OBSERVED, scalar(1, 1))
        self.assertEqual(b"\x08\x00", result)
        self.assertTrue(details["changed"])
        self.assertEqual(0, details["group_count"])
        with self.assertRaises(ValueError):
            self.reg.respond("A", OBSERVED, string(1, "not-scalar"))


if __name__ == "__main__":
    unittest.main()
