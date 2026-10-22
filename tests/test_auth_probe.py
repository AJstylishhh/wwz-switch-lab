"""No Switch/official backend access required."""
import json
from pathlib import Path
import tempfile
import unittest

from wwz_wire import blob, string, scalar, fields
from auth_probe import summarize, select_capture, AUTH_ROUTE
from auth_queue_candidate import candidate


class AuthTests(unittest.TestCase):
    def test_no_sensitive_values_in_summary(self):
        request = (blob(1, string(1, "Retail") + string(2, "version")) +
                   string(2, "secret-login") + string(3, "secret-password") +
                   string(4, "provider") + blob(5, b"\x0a\x00") +
                   string(6, "v1"))
        result = summarize(request)
        self.assertEqual("Enqueue", result["candidates"][0]["method"])
        self.assertEqual(6, len(result["fields"]))
        self.assertNotIn("secret-", json.dumps(result))

    def test_capture_directory_filter(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t)
            (p / "new.json").write_text(json.dumps({"path": AUTH_ROUTE, "length": 3}))
            (p / "new.bin").write_bytes(b"\x0a\x01x")
            (p / "old.json").write_text(json.dumps({"path": "/unrelated.svc/route"}))
            (p / "old.bin").write_bytes(b"")
            self.assertEqual(p / "new.bin", select_capture(p))

    def test_queue_field_is_exact(self):
        response = list(fields(candidate("testing")))
        self.assertEqual([(1, 0), (262225376, 2)],
                         [(n, w) for n, w, _ in response])
        wrapper = list(fields(response[1][2]))
        position = list(fields(wrapper[0][2]))
        token = list(fields(position[0][2]))
        self.assertEqual(b"testing", token[0][2])
        self.assertEqual(2, token[1][2])


if __name__ == "__main__":
    unittest.main()
