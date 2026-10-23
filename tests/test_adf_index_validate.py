"""Synthetic regression tests for a coherent ADF index vs false positives."""
import json
from pathlib import Path
import struct
import tempfile
import unittest
import zlib

from adf_index_validate import candidate, inspect, summarize
from diagnostic_deep_probe import DIAG_ROUTE
from wwz_wire import blob


class ADFIndexValidationTests(unittest.TestCase):
    @staticmethod
    def intervals(order="<"):
        return b"".join(struct.pack(order + "III", start, 10, 0xABCD1234)
                        for start in range(0, 100, 10))

    def test_contiguous_index_is_strong(self):
        report = candidate(self.intervals(), 100, "little", 0, 1)
        self.assertTrue(report["strong_sequential_candidate"])
        self.assertEqual(100.0, report["adjacent_pct"])
        self.assertEqual(100.0, report["covered_data_pct"])
        self.assertEqual(100.0, report["distinct_offsets_pct"])

    def test_in_bounds_randomish_integer_pairs_are_not_strong(self):
        records = b"".join(struct.pack("<III", start, 1, 2)
                           for start in range(0, 100, 10))
        report = candidate(records, 100, "little", 0, 1)
        self.assertEqual(100.0, report["in_bounds_pct"])
        self.assertFalse(report["strong_sequential_candidate"])
        self.assertLess(report["adjacent_pct"], 50.0)
        self.assertLess(report["covered_data_pct"], 50.0)

    def test_big_endian_is_separate_hypothesis(self):
        entries = self.intervals(">")
        self.assertTrue(candidate(entries, 100, "big", 0, 1)["strong_sequential_candidate"])
        self.assertFalse(any(r["strong_sequential_candidate"] and r["order"] == "little"
                             for r in inspect(b"x" * 100, entries)))

    def test_wrong_width_and_zero_records(self):
        self.assertIsNone(candidate(b"\0" * 15, 100, "little", 0, 1))
        result = candidate(b"\0" * 120, 100, "little", 0, 1)
        self.assertIsNone(result)

    def test_grouped_output_contains_no_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            data = b"Sensitive private player " * 5
            records = self.intervals()
            for i in range(3):
                (folder / (f"pack{i}.json")).write_text(
                    json.dumps({"path": DIAG_ROUTE}), encoding="utf8")
                body = data if i < 2 else data + b"extra"
                (folder / (f"pack{i}.bin")).write_bytes(
                    blob(1, zlib.compress(body)) +
                    blob(2, zlib.compress(records)))
            summary = summarize(folder)
            self.assertEqual(3, summary["packs_examined"])
            self.assertEqual(2, summary["unique_exact_payloads"])
            self.assertNotIn("Sensitive", str(summary))
            self.assertNotIn("private player", str(summary))
            self.assertNotIn("pack0", str(summary))
            self.assertNotIn("byte_order=little", str(summary))


if __name__ == "__main__":
    unittest.main()
