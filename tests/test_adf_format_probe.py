"""Synthetic, non-identifying tests for read-only WWZ diagnostic format triage."""
import json
from pathlib import Path
import tempfile
import unittest
import zlib

from adf_format_probe import analyze, characterize
from diagnostic_deep_probe import DIAG_ROUTE
from wwz_wire import blob


class FormatProbeTests(unittest.TestCase):
    def test_text_and_json_do_not_leak_values(self):
        private = b'{"nickname":"private-user","state":"offline","error":"none"}'
        result = characterize(private)
        self.assertEqual("json", result["format"])
        self.assertIn("offline", result["keyword_hits"])
        self.assertNotIn("private-user", str(result))

    def test_binary_and_bad_json(self):
        self.assertEqual("opaque_binary", characterize(b"\xff\xfe\xff")["format"])
        self.assertEqual("utf8_text", characterize(b"simple diagnostic")["format"])

    def test_local_compressed_parts_only(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            (folder / "example.json").write_text(json.dumps({"path": DIAG_ROUTE}))
            (folder / "example.bin").write_bytes(
                blob(1, zlib.compress(b'{"Error":"private-user-nickname"}')) +
                blob(2, zlib.compress(b"\x00\x00\xff\xff")))
            result = analyze(folder)
            self.assertEqual(1, result["part_counts"]["data_decompressed"])
            self.assertEqual(1, result["part_counts"]["entries_decompressed"])
            self.assertEqual(1, result["decoded_format_classes"]["data:json"])
            self.assertNotIn("private-user-nickname", str(result))


if __name__ == "__main__":
    unittest.main()
