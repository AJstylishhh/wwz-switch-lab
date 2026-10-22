"""Offline synthetic tests: only fixed marker labels leave the ADF capture."""
import json
from pathlib import Path
import tempfile
import unittest
import zlib

from adf_failure_timeline import analyze, close_hits, safe_part_summary
from diagnostic_deep_probe import DIAG_ROUTE
from wwz_wire import blob


class TimelineTests(unittest.TestCase):
    def test_nearby_and_separated(self):
        self.assertTrue(close_hits([5, 500], [550]))
        self.assertFalse(close_hits([5, 500], [800]))
        info = safe_part_summary(b"account-private error: not connected" +
                                 b"x" * 200 + b"timeout")
        self.assertIn("error+not_connected",
                      info["keyword_pairs_within_96_bytes"])
        self.assertNotIn("error+timeout",
                         info["keyword_pairs_within_96_bytes"])
        self.assertNotIn("account-private", str(info))

    def test_order_and_section_without_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for filename, payload in (
                ("20261022T010101Z", b"credentials-personal error not connected"),
                ("20261022T010102Z", b"private-user timeout failed"),
            ):
                (root / (filename+".json")).write_text(json.dumps({"path": DIAG_ROUTE}))
                (root / (filename+".bin")).write_bytes(
                    blob(1, zlib.compress(payload)) +
                    blob(2, zlib.compress(b"binary no signal")))
            summary = analyze(root)
            self.assertEqual(2, summary["packs_examined"])
            self.assertEqual(1, summary["occurrence_totals"]["error"])
            self.assertEqual(1, summary["occurrence_totals"]["failed"])
            self.assertIn("data:error", summary["packs_with_keyword_by_section"])
            self.assertNotIn("credentials-personal", str(summary))
            self.assertNotIn("private-user", str(summary))
            self.assertNotIn("20261022", str(summary))


if __name__ == "__main__":
    unittest.main()
