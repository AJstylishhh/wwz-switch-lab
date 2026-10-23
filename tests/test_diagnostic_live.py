"""Live WriteADFPack logging: bounded zlib decode; safe markers, no tokens."""
import logging
import unittest
import zlib

from diagnostic_live import safe_live_summary
from post_login import PostLogin
from post_login_wire import DIAGNOSTICS_WRITE
from wwz_wire import blob, fields

MISMATCH = "autogen VersionDataType_Last does not corresponds with backend values"
SECRET = "REDACT_THIS_FAKE_TOKEN_1234567890"


def pack(contents):
    # Real Switch WriteADFPack data=1, entries=2, header=3.
    return (blob(1, zlib.compress(contents)) +
            blob(2, zlib.compress(b"dummy entry")) +
            blob(3, blob(2, b"adf")))


class LiveDiagnosticsTests(unittest.TestCase):
    def test_known_mismatch_detected_in_compressed_pack_without_secret(self):
        raw = pack(b"\x00" + MISMATCH.encode() + b"\x00" + SECRET.encode())
        summary = safe_live_summary(raw)
        self.assertIn(MISMATCH, summary["known_marker_strings"])
        self.assertEqual({"zlib": 2}, summary["verified_decompression"])
        self.assertEqual({"adf": 1}, summary["format_classes"])
        self.assertNotIn(SECRET, str(summary))

    def test_live_handler_ack_and_log_do_not_expose_raw_input(self):
        handler = PostLogin(None)
        raw = pack(b"\x00" + MISMATCH.encode() + b"\x00" + SECRET.encode())
        with self.assertLogs("wwz.mvp", level=logging.INFO) as output:
            reply, info = handler.respond(DIAGNOSTICS_WRITE, raw)
        self.assertEqual({"stage": "diagnostics_ack", "acknowledged_packs": 1}, info)
        self.assertEqual([(1, 0, 0)], list(fields(reply)))
        logs = "\n".join(output.output)
        self.assertIn(MISMATCH, logs)
        self.assertNotIn(SECRET, logs)
        self.assertIn("NOT confirmed as errors", logs)

    def test_empty_supported_pack_keeps_ack(self):
        handler = PostLogin(None)
        # Valid protobuf wrapper but unknown payload coding.
        raw = blob(1, b"\x00\x01") + blob(2, b"\x02") + blob(3, blob(2, b"adf"))
        with self.assertLogs("wwz.mvp", level=logging.INFO) as output:
            reply, info = handler.respond(DIAGNOSTICS_WRITE, raw)
        self.assertEqual("diagnostics_ack", info["stage"])
        self.assertEqual([(1, 0, 0)], list(fields(reply)))
        self.assertIn("known_marker_strings': []", "\n".join(output.output))

    def test_oversized_compressed_text_not_expanded_unboundedly(self):
        # 4 MiB decompression output cap. Marker should not leak from skipped
        # oversized input; the handler must still send an ACK.
        raw = pack((b"x" * (4 * 1024 * 1024 + 16)) + MISMATCH.encode())
        summary = safe_live_summary(raw)
        self.assertNotIn(MISMATCH, summary["known_marker_strings"])
        # The oversized data field is skipped, but the small entries field still decodes.
        self.assertEqual({"zlib": 1}, summary["verified_decompression"])
        reply, _ = PostLogin(None).respond(DIAGNOSTICS_WRITE, raw)
        self.assertEqual([(1, 0, 0)], list(fields(reply)))


if __name__ == "__main__":
    unittest.main()
