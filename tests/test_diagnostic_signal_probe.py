"""Offline tests for diagnostic signal scan, without real player data."""
import json
from pathlib import Path
import tempfile
import unittest

from diagnostic_signal_probe import analyze, safe_summary, DIAG_ROUTE
from wwz_wire import blob


class DiagnosticProbeTests(unittest.TestCase):
    def test_allowlist_only(self):
        raw = (blob(1, b"secret-user-name CS_NoServiceEndpoint private-value") +
               blob(2, b"private-password") + blob(3, b""))
        item = safe_summary(raw)
        self.assertEqual(["CS_NoServiceEndpoint"], item["known_error_markers"])
        self.assertNotIn("secret-user-name", str(item))
        self.assertNotIn("private-password", str(item))

    def test_missing_hits_not_a_clean_bill(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            (folder / "capture.json").write_text(json.dumps({"path": DIAG_ROUTE}))
            (folder / "capture.bin").write_bytes(blob(1, b"opaque-facts"))
            result = analyze(folder)
            self.assertEqual(1, result["captures"])
            self.assertEqual([], result["known_error_markers"])
            self.assertIn("does not mean there was no error", result["note"])


if __name__ == "__main__":
    unittest.main()
