"""Synthetic tests for 12-byte WWZ diagnostic index table hypothesis."""
import json
from pathlib import Path
import struct
import tempfile
import unittest
import zlib

from adf_entry_layout_probe import record_layout, summarize
from diagnostic_deep_probe import DIAG_ROUTE
from wwz_wire import blob


class ADFEntryLayoutTests(unittest.TestCase):
    def test_inbounds_three_integer_records(self):
        entries = b"".join(struct.pack("<III", offset, size, 255)
                           for offset, size in ((0, 3), (10, 5), (25, 6), (40, 4)))
        report = record_layout(entries, 100)
        self.assertTrue(report["multiple_of_12"])
        self.assertEqual(4, report["entry_count_if_12_bytes"])
        self.assertIn({"offset_column": 0, "length_column": 1,
                       "in_bounds_nonempty_pct": 100.0},
                      report["candidate_offset_length_columns"])
        self.assertNotIn("255", str(report))

    def test_repeated_zero_records_are_not_taken_as_offsets(self):
        report = record_layout(b"\0" * 120, 100)
        self.assertEqual([], report["candidate_offset_length_columns"])

    def test_local_fingerprints_not_printed(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            payload = b"private-person error timeout"
            entries = b"".join(struct.pack("<III", i, 2, 0) for i in (0, 5, 10))
            for idx in range(3):
                (folder / (f"pack{idx}.json")).write_text(
                    json.dumps({"path": DIAG_ROUTE}))
                data = payload if idx < 2 else payload + b"extra"
                (folder / (f"pack{idx}.bin")).write_bytes(
                    blob(1, zlib.compress(data)) +
                    blob(2, zlib.compress(entries)))
            result = summarize(folder)
            self.assertEqual(3, result["packs_examined"])
            self.assertEqual(3, result["entries_multiple_of_12"])
            self.assertEqual([2], result["exact_duplicate_payload_groups"])
            self.assertNotIn("private-person", str(result))
            self.assertNotIn("error timeout", str(result))


if __name__ == "__main__":
    unittest.main()
