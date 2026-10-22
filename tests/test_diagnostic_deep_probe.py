"""Synthetic tests for safe, bounded ADF diagnostic inspection."""
import gzip
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
import zlib

from diagnostic_deep_probe import (
    analyze, inspect_pack, bounded_decompress, MAX_DECODED, DIAG_ROUTE,
)
from wwz_wire import blob, scalar


class DiagnosticDeepTests(unittest.TestCase):
    def test_zlib_and_gzip_marker_redaction(self):
        body = b"private-user-data CS_NoServiceEndpoint secret-password"
        header = blob(2, b"json") + scalar(3, 1) + scalar(4, 2) + (
            blob(8, blob(1, b"PlayerUser") + blob(2, b"private-identifier")))
        pack = blob(1, zlib.compress(body)) + blob(2, gzip.compress(body)) + blob(3, header)
        result = inspect_pack(pack)
        matches = {name for part in result["parts"] for name in part["markers"]}
        self.assertEqual({"CS_NoServiceEndpoint"}, matches)
        self.assertEqual(["zlib"], result["parts"][0]["verified"])
        self.assertEqual(["gzip"], result["parts"][1]["verified"])
        self.assertEqual("json", result["headers"][0]["format_class"])
        self.assertNotIn("private-user-data", str(result))
        self.assertNotIn("private-identifier", str(result))

    def test_decompression_bomb_rejected(self):
        oversized = zlib.compress(b"x" * (MAX_DECODED + 100))
        self.assertIsNone(bounded_decompress(oversized, 15))

    def test_zip_is_bounded_and_redacted(self):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("secret-player-name.txt",
                             b"CS_InvalidACLToken private-console-key")
        result = inspect_pack(blob(1, stream.getvalue()))
        self.assertEqual(["zip"], result["parts"][0]["verified"])
        self.assertEqual(["CS_InvalidACLToken"], result["parts"][0]["markers"])
        self.assertNotIn("private-console-key", str(result))

    def test_grouped_reports_no_captured_values(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "one.json").write_text(json.dumps({"path": DIAG_ROUTE}))
            (root / "one.bin").write_bytes(blob(
                1, zlib.compress(b"CS_RequiredComponentIsNotConnected sensitive")))
            result = analyze(root)
            self.assertEqual(1, result["diagnostic_packs"])
            self.assertEqual(["CS_RequiredComponentIsNotConnected"],
                             result["known_error_markers"])
            self.assertNotIn("sensitive", str(result))


if __name__ == "__main__":
    unittest.main()
