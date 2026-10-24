"""Cross-playlist pairing is an explicit two-client *diagnostic*, never default.

A real title may not permit these two playlists in one game. We force only
one unambiguous pair of independently authenticated solo searchers, then
check whether state notification and public profiles can proceed.
"""
import unittest
from types import SimpleNamespace
from uuid import UUID

from lobby_registry import HANDLERS, LobbyRegistry
from mvp_server import App
from wwz_wire import blob, scalar, string

START = next(k for k, v in HANDLERS.items() if v == "start")
STOP = next(k for k, v in HANDLERS.items() if v == "stop")


def start(name):
    return blob(1, scalar(1, 2)) + blob(2, scalar(1, 0)) + string(3, name)


class CrossPlaylistProbeTests(unittest.TestCase):
    def setUp(self):
        self.reg = LobbyRegistry()
        for n, source in enumerate(("citron", "switch", "third"), 1):
            self.reg.attach(source, SimpleNamespace(user_guid=UUID(int=n)))

    def test_default_incompatible_playlists_stay_separate(self):
        self.reg.respond("citron", START, start("story-pve"))
        _, info = self.reg.respond("switch", START, start("browse-all"))
        self.assertEqual("playlist_differs", info["decision"])
        self.assertEqual(2, len(self.reg.groups))

    def test_opt_in_pairs_on_first_search_without_changing_labels(self):
        self.reg.respond("citron", START, start("story-pve"))
        _, info = self.reg.respond("switch", START, start("browse-all"),
                                   public_discovery=True, cross_playlist_probe=True)
        self.assertEqual("experimental_cross_playlist_pair", info["decision"])
        self.assertEqual(2, info["members"])
        self.assertTrue(info["forced_cross_playlist"])
        self.assertEqual(1, len(self.reg.groups))
        g = self.reg._group("citron")
        self.assertEqual({"citron": "story-pve", "switch": "browse-all"},
                         g.requested_playlists)
        self.assertEqual("story-pve", g.playlist)  # owner is not overwritten
        self.assertEqual(1, g.roster_revision)

    def test_repeating_both_original_playlists_keeps_shared_group(self):
        self.reg.respond("citron", START, start("story-pve"))
        self.reg.respond("switch", START, start("browse-all"),
                         cross_playlist_probe=True)
        lid = self.reg.member_group["citron"]
        for _ in range(4):
            _, info_b = self.reg.respond("switch", START, start("browse-all"),
                                         cross_playlist_probe=True)
            _, info_a = self.reg.respond("citron", START, start("story-pve"),
                                         cross_playlist_probe=True)
            self.assertEqual("already_in_shared_queue", info_b["decision"])
            self.assertEqual("already_in_shared_queue", info_a["decision"])
            self.assertEqual(lid, self.reg.member_group["switch"])
        self.assertEqual(1, len(self.reg.groups))

    def test_three_queued_solo_groups_refuse_forced_ambiguity(self):
        self.reg.respond("citron", START, start("story-pve"))
        self.reg.respond("switch", START, start("browse-all"))
        _, info = self.reg.respond("third", START, start("horde-pve"),
                                   cross_playlist_probe=True)
        self.assertEqual("playlist_differs", info["decision"])
        self.assertEqual(3, len(self.reg.groups))

    def test_same_playlist_priority_over_forced_match(self):
        self.reg.respond("citron", START, start("story-pve"))
        self.reg.respond("switch", START, start("browse-all"))
        _, info = self.reg.respond("third", START, start("story-pve"),
                                   cross_playlist_probe=True)
        self.assertEqual("joined_existing_queue", info["decision"])
        self.assertNotIn("forced_cross_playlist", info)
        self.assertEqual(self.reg.member_group["citron"],
                         self.reg.member_group["third"])
        self.assertNotEqual(self.reg.member_group["switch"],
                            self.reg.member_group["third"])

    def test_a_new_playlist_after_force_detaches_one_player(self):
        self.reg.respond("citron", START, start("story-pve"))
        self.reg.respond("switch", START, start("browse-all"),
                         cross_playlist_probe=True)
        _, info = self.reg.respond("switch", START, start("new-world"),
                                   cross_playlist_probe=True)
        self.assertTrue(info["detached_for_new_search"])
        self.assertEqual(["citron"], self.reg._group("citron").members)
        self.assertEqual("story-pve", self.reg._group("citron").playlist)
        self.assertEqual("new-world", self.reg._group("switch").playlist)

    def test_probe_requires_public_discovery_and_session_ids(self):
        with self.assertRaises(ValueError):
            App({}, lab_cross_playlist_probe=True, lobby_mvp=True,
                lobby_session_ids=True)
        with self.assertRaises(ValueError):
            App({}, lab_cross_playlist_probe=True, public_lobby_discovery=True,
                lobby_mvp=True)
        app = App({}, lab_cross_playlist_probe=True, public_lobby_discovery=True,
                  lobby_mvp=True, lobby_session_ids=True)
        self.assertTrue(app.lab_cross_playlist_probe)


if __name__ == "__main__":
    unittest.main()
