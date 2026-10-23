"""Synthetic regression tests for the isolated WWZ PresenceConnect 300s experiment."""
import json
from pathlib import Path
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from mvp_server import read_routes
from post_login_wire import PRESENCE_CONNECT, presence_connect_result
from wwz_wire import fields


def children(raw, field):
    return [value for name, wire, value in fields(raw) if name == field and wire == 2]


class PresenceDurationTests(unittest.TestCase):
    def test_one_setting_different(self):
        root = Path(__file__).resolve().parents[1]
        base = json.loads((root / "routes.environment-production-shape.example.json").read_text())
        trial = json.loads((root / "routes.presence-300.example.json").read_text())
        self.assertEqual(set(base), set(trial))
        for name in base:
            expected = dict(base[name])
            if expected.get("handler") == "presence_connect":
                expected["presence_available_seconds"] = 300
            self.assertEqual(expected, trial[name])

        # Both configs request date_ms="now". Freeze startup time for this
        # comparison; otherwise a 1ms clock tick is a false difference.
        class FrozenDateTime(datetime):
            @classmethod
            def now(cls, tz=None):
                return datetime(2026, 10, 23, 12, 0, 0, tzinfo=timezone.utc)

        with patch("mvp_server.datetime", FrozenDateTime):
            original = read_routes(root / "routes.environment-production-shape.example.json")
            changed = read_routes(root / "routes.presence-300.example.json")
        self.assertEqual(set(original), set(changed))
        for path in original:
            if path != PRESENCE_CONNECT:
                self.assertEqual(original[path], changed[path])
        self.assertEqual(0, original[PRESENCE_CONNECT][1]["presence_available_seconds"])
        self.assertEqual(300, changed[PRESENCE_CONNECT][1]["presence_available_seconds"])

    def test_wire_encode_only_one_varint(self):
        original = presence_connect_result()
        changed = presence_connect_result(300)
        field = 347012296
        def extract(raw):
            inner = children(children(raw, field)[0], 1)[0]
            values = [(n, w, v) for n, w, v in fields(inner)]
            return values
        self.assertEqual([(1, 0, 0)], extract(original))
        self.assertEqual([(1, 0, 300)], extract(changed))
        self.assertEqual(original, presence_connect_result(0))

    def test_invalid_presence_duration_is_rejected(self):
        for value in (-1, 3601, "300", None):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    presence_connect_result(value)


if __name__ == "__main__":
    unittest.main()
