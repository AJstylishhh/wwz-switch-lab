"""Synthetic, no credentials: repeated int64 UserVersions experiment."""
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from mvp_server import read_routes
from post_login import PostLogin
from post_login_wire import (
    HEARTBEAT_REGISTER, HEARTBEAT_UPDATE, heartbeat_register_result,
    heartbeat_update_result,
)
from wwz_wire import blob, scalar, string, fields

ROOT = Path(__file__).resolve().parents[1]
BUILD = "0.1.DEV.8802288/PREBUILD"
VALUES = [8802288] * 4


def get_bytes(raw, field):
    return next(value for n, wire, value in fields(raw) if n == field and wire == 2)


def versions(reply, typed_field):
    inner = get_bytes(get_bytes(reply, typed_field), 1)
    user_versions = get_bytes(inner, 1)
    return list(fields(user_versions))


class FrozenDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        return datetime(2026, 10, 23, 12, 0, 0, tzinfo=timezone.utc)


class HeartbeatVersionsTests(unittest.TestCase):
    def test_fixture_only_changes_heartbeat_version_lists(self):
        base = json.loads((ROOT / "routes.environment-production-shape.example.json").read_text())
        trial = json.loads((ROOT / "routes.heartbeat-versions4.example.json").read_text())
        self.assertEqual(set(base), set(trial))
        for route in base:
            expected = dict(base[route])
            if expected.get("handler") in ("heartbeat_register", "heartbeat_update"):
                expected["heartbeat_version_values"] = VALUES
            self.assertEqual(expected, trial[route])

        # Date='now' must be identical to compare the ENVIRONMENT RPC bytes.
        with patch("mvp_server.datetime", FrozenDateTime):
            original = read_routes(ROOT / "routes.environment-production-shape.example.json")
            altered = read_routes(ROOT / "routes.heartbeat-versions4.example.json")
        self.assertEqual(set(original), set(altered))
        for path in original:
            if path in (HEARTBEAT_REGISTER, HEARTBEAT_UPDATE):
                self.assertEqual(VALUES, altered[path][1]["heartbeat_version_values"])
                self.assertIsNone(original[path][1]["heartbeat_version_values"])
            else:
                self.assertEqual(original[path], altered[path])

    def test_wire_encodes_four_nonpacked_int64_in_both_results(self):
        register = heartbeat_register_result(version_values=VALUES)
        update = heartbeat_update_result(version_values=VALUES)
        self.assertEqual([(1, 0, 8802288)] * 4, versions(register, 438369230))
        self.assertEqual([(1, 0, 8802288)] * 4, versions(update, 417677176))
        self.assertEqual([], versions(heartbeat_register_result(), 438369230))
        self.assertEqual([], versions(heartbeat_update_result(), 417677176))

    def test_handler_passes_values_and_safe_count(self):
        handler = PostLogin(None)
        register = string(1, BUILD) + scalar(2, 1) + scalar(3, 1)
        update = (string(1, BUILD) + scalar(2, 1) + blob(3, b"\x0a\x00") +
                  scalar(4, 1) + blob(5, b""))
        raw, info = handler.respond(
            HEARTBEAT_REGISTER, register, heartbeat_version_values=VALUES)
        self.assertEqual(4, info["version_count"])
        self.assertEqual(4, len(versions(raw, 438369230)))
        raw, info = handler.respond(
            HEARTBEAT_UPDATE, update, heartbeat_version_values=VALUES)
        self.assertEqual(4, info["version_count"])
        self.assertEqual(4, len(versions(raw, 417677176)))

    def test_invalid_or_inconsistent_values_rejected(self):
        from post_login_wire import user_versions
        for value in ([], [-1], [2**63], [True], ["8802288"], list(range(21))):
            with self.subTest(version_values=value), self.assertRaises(ValueError):
                user_versions(value)

        trial = json.loads((ROOT / "routes.heartbeat-versions4.example.json").read_text())
        updater = next(v for v in trial.values() if v.get("handler") == "heartbeat_update")
        updater["heartbeat_version_values"] = [8802288, 8802288]
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "routes.json"
            path.write_text(json.dumps(trial), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "identical version values"):
                read_routes(path)


if __name__ == "__main__":
    unittest.main()
