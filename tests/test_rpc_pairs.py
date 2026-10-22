"""Test structural GUID pairing without a game binary."""
import unittest

from rpc_pairs import infer_pairs


class PairTests(unittest.TestCase):
    def test_repeated_service_follows_unique_methods(self):
        guids = ["111", "abc", "222", "abc", "abc", "333", "def", "444", "def"]
        rows = [{"guid": guid, "record_va": hex(i * 24)}
                for i, guid in enumerate(guids)]
        pairs = infer_pairs(rows)
        self.assertEqual([("111", "abc"), ("222", "abc"),
                          ("333", "def"), ("444", "def")],
                         [(p["method_guid"], p["service_guid"]) for p in pairs])
        self.assertTrue(all(".svc/" in p["route"] for p in pairs))


if __name__ == "__main__":
    unittest.main()
