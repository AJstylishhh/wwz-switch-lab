"""Binary-grounded nine-entry heartbeat regression; no original game data."""
from datetime import datetime, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from mvp_server import read_routes
from post_login_wire import (
    HEARTBEAT_REGISTER, HEARTBEAT_UPDATE,
    heartbeat_register_result, heartbeat_update_result,
)
from set_heartbeat_versions import set_version_count, update_local_route
from wwz_wire import fields

ROOT = Path(__file__).resolve().parents[1]
VALUES = [8802288] * 9


class FrozenDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        return datetime(2026, 10, 23, 12, 0, 0, tzinfo=timezone.utc)


def payload_versions(reply, typed_field):
    envelope = next(data for n, wire, data in fields(reply)
                    if n == typed_field and wire == 2)
    inner = next(data for n, wire, data in fields(envelope)
                 if n == 1 and wire == 2)
    versions_blob = next(data for n, wire, data in fields(inner)
                         if n == 1 and wire == 2)
    return list(fields(versions_blob))


class HeartbeatNineTests(unittest.TestCase):
    def test_only_versions_differ_from_baseline_fixture(self):
        base = json.loads((ROOT / "routes.environment-production-shape.example.json").read_text())
        nine = json.loads((ROOT / "routes.heartbeat-versions9.example.json").read_text())
        self.assertEqual(set(base), set(nine))
        expected = set_version_count(base, 9)
        self.assertEqual(expected, nine)

        with patch("mvp_server.datetime", FrozenDateTime):
            original = read_routes(ROOT / "routes.environment-production-shape.example.json")
            altered = read_routes(ROOT / "routes.heartbeat-versions9.example.json")
        self.assertEqual(set(original), set(altered))
        for route in original:
            if route in (HEARTBEAT_REGISTER, HEARTBEAT_UPDATE):
                self.assertEqual(VALUES, altered[route][1]["heartbeat_version_values"])
            else:
                self.assertEqual(original[route], altered[route])

    def test_both_heartbeat_replies_have_nine_unpacked_int64_entries(self):
        for typed, raw in (
            (438369230, heartbeat_register_result(version_values=VALUES)),
            (417677176, heartbeat_update_result(version_values=VALUES)),
        ):
            self.assertEqual([(1, 0, 8802288)] * 9,
                             payload_versions(raw, typed))

    def test_remote_route_updater_preserves_all_unrelated_values(self):
        example = json.loads((ROOT / "routes.heartbeat-versions4.example.json").read_text())
        public_ip = "198.51.100.33"  # reserved example IP, not the user's.
        for config in example.values():
            if config.get("handler") == "dequeue":
                config["address"] = public_ip
            if config.get("handler") == "environment_list":
                for center in config["datacenters"]:
                    for endpoint in center["endpoints"]:
                        endpoint["address"] = public_ip

        with TemporaryDirectory() as temp:
            path = Path(temp) / "routes.remote.local.json"
            path.write_text(json.dumps(example), encoding="utf-8")
            update_local_route(path, 9)
            converted = json.loads(path.read_text())
            self.assertEqual(set_version_count(example, 9), converted)
            self.assertEqual(public_ip, next(
                v["address"] for v in converted.values()
                if v.get("handler") == "dequeue"))
            self.assertEqual(15, path.read_text().count(public_ip))
        self.assertEqual(4, next(
            len(v["heartbeat_version_values"]) for v in example.values()
            if v.get("handler") == "heartbeat_register"))

    def test_invalid_count_or_missing_handler_does_not_modify_file(self):
        example = json.loads((ROOT / "routes.environment-production-shape.example.json").read_text())
        with self.assertRaises(ValueError):
            set_version_count(example, 0)
        with self.assertRaises(ValueError):
            set_version_count(example, 21)
        invalid = {k: v for k, v in example.items()
                   if v.get("handler") != "heartbeat_update"}
        with TemporaryDirectory() as temp:
            path = Path(temp) / "routes.json"
            path.write_text(json.dumps(invalid), encoding="utf-8")
            original = path.read_text()
            with self.assertRaises(ValueError):
                update_local_route(path, 9)
            self.assertEqual(original, path.read_text())


if __name__ == "__main__":
    unittest.main()
