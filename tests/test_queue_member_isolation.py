"""Regression: an individual's Start/Stop cannot rewrite a shared queue.

All traffic, users and playlists below are synthetic.
"""
import unittest
from types import SimpleNamespace
from uuid import UUID

from lobby_registry import HANDLERS, LobbyRegistry
from wwz_wire import blob, scalar, string

START = next(path for path, name in HANDLERS.items() if name == "start")
STOP = next(path for path, name in HANDLERS.items() if name == "stop")
MATCH = next(path for path, name in HANDLERS.items() if name == "match_status")


def request(name):
    return blob(1, scalar(1, 12)) + blob(2, scalar(1, 1)) + string(3, name)


class QueueIsolationTests(unittest.TestCase):
    def setUp(self):
        self.reg = LobbyRegistry()
        for n, source in enumerate(("alice", "bob", "chris"), 1):
            self.reg.attach(source, SimpleNamespace(user_guid=UUID(int=n)))

    def pair(self):
        self.reg.respond("alice", START, request("campaign"))
        self.reg.respond("bob", START, request("campaign"))
        self.assertEqual(self.reg.member_group["alice"],
                         self.reg.member_group["bob"])

    def test_bob_stopping_does_not_stop_alice_queue(self):
        self.pair()
        _, details = self.reg.respond("bob", STOP, b"")
        self.assertTrue(details["detached_from_shared_queue"])
        self.assertEqual(1, details["members"])
        self.assertFalse(details["queued"])
        self.assertNotEqual(self.reg.member_group["alice"],
                            self.reg.member_group["bob"])
        alice = self.reg._group("alice")
        bob = self.reg._group("bob")
        self.assertTrue(alice.queued)
        self.assertFalse(bob.queued)
        self.assertEqual(["alice"], alice.members)
        self.assertEqual(["bob"], bob.members)
        self.reg.respond("chris", START, request("campaign"))
        self.assertEqual(self.reg.member_group["alice"],
                         self.reg.member_group["chris"])
        self.assertNotEqual(self.reg.member_group["bob"],
                            self.reg.member_group["chris"])

    def test_change_playlist_while_paired_does_not_drag_teammate(self):
        self.pair()
        old_group = self.reg._group("bob")
        _, meta = self.reg.respond("alice", START, request("horde"))
        self.assertTrue(meta["detached_for_new_search"])
        self.assertEqual("horde", self.reg._group("alice").playlist)
        self.assertTrue(self.reg._group("alice").queued)
        self.assertEqual(["bob"], old_group.members)
        self.assertEqual("campaign", old_group.playlist)
        self.assertTrue(old_group.queued)
        self.reg.respond("chris", START, request("campaign"))
        self.assertEqual(self.reg.member_group["bob"],
                         self.reg.member_group["chris"])
        self.assertNotEqual(self.reg.member_group["alice"],
                            self.reg.member_group["chris"])

    def test_same_playlist_repeated_start_keeps_two_member_group(self):
        self.pair()
        lid = self.reg.member_group["bob"]
        _, info = self.reg.respond("bob", START, request("campaign"))
        self.assertFalse(info["detached_for_new_search"])
        self.assertEqual("already_in_shared_queue", info["decision"])
        self.assertEqual(lid, self.reg.member_group["alice"])
        self.assertEqual(lid, self.reg.member_group["bob"])
        self.assertEqual(1, len(self.reg.groups))
        self.assertTrue(self.reg._group("bob").queued)

    def test_lone_stopped_queue_remains_lone(self):
        self.reg.respond("alice", START, request("campaign"))
        _, info = self.reg.respond("alice", STOP, b"")
        self.assertFalse(info["detached_from_shared_queue"])
        self.assertFalse(self.reg._group("alice").queued)
        self.assertEqual(1, len(self.reg.groups))

    def test_private_squad_not_auto_published(self):
        self.reg.respond("alice", START, request("campaign"))
        self.reg.respond("bob", START, request("campaign"))
        self.reg.respond("bob", STOP, b"")
        self.reg.respond("bob", START, request("horde"))
        self.reg.respond("chris", START, request("campaign"))
        self.assertEqual(2, len(self.reg.groups))


if __name__ == "__main__":
    unittest.main()
