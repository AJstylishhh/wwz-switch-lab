"""Synthetic HasSubscription A/B response tests; never calls Nintendo services."""
import http.client
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest
from uuid import UUID

from auth_dequeue import Identity, encode_signin, SIGNIN_RESULT_FIELD
from enable_multiplayer_subscription_probe import DEQUEUE, update, modify_file
from mvp_server import App, Server, make_handler, read_routes
from wwz_wire import fields

ROOT = Path(__file__).resolve().parents[1]


def find_field(raw, n):
    return [v for field, wire, v in fields(raw) if field == n]


def signin_info(raw):
    typed = find_field(raw, SIGNIN_RESULT_FIELD)
    assert len(typed) == 1
    data = find_field(typed[0], 1)
    assert len(data) == 1
    return find_field(data[0], 10)


class MultiplayerSubscriptionProbeTests(unittest.TestCase):
    def test_default_absent_probes_true_false_fields(self):
        identity = Identity("fake-auth", "fake-diagnostic", "fake-access",
                            "fake-provider", UUID(int=7), "fake-user")
        common = dict(address="127.0.0.1", port=11704, name="PresenceService")
        baseline = encode_signin(identity, ["PresenceService"], **common)
        self.assertEqual([], signin_info(baseline))
        true = encode_signin(identity, ["PresenceService"],
                             provider_has_subscription=True, **common)
        false = encode_signin(identity, ["PresenceService"],
                              provider_has_subscription=False, **common)
        self.assertEqual([1], find_field(signin_info(true)[0], 1))
        self.assertEqual([0], find_field(signin_info(false)[0], 1))
        for value in (1, "true", [], {}):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "boolean"):
                    encode_signin(identity, ["PresenceService"],
                                  provider_has_subscription=value, **common)

    def test_exactly_one_route_modified_and_roundtrip(self):
        base = json.loads((ROOT / "routes.heartbeat-versions9.example.json").read_text())
        copy = update(base)
        self.assertEqual(set(copy), set(base))
        for key in base:
            if key != DEQUEUE:
                self.assertEqual(base[key], copy[key])
        self.assertEqual(True, copy[DEQUEUE]["provider_has_subscription"])
        self.assertEqual(copy, update(copy))
        self.assertEqual(base, update(copy, undo=True))
        with TemporaryDirectory() as d:
            file = Path(d) / "routes.remote.local.json"
            file.write_text(json.dumps(base))
            modify_file(file)
            result = json.loads(file.read_text())
            self.assertEqual(copy, result)
            modify_file(file, undo=True)
            self.assertEqual(base, json.loads(file.read_text()))

    def test_collision_refused(self):
        base = json.loads((ROOT / "routes.heartbeat-versions9.example.json").read_text())
        base[DEQUEUE]["provider_has_subscription"] = False
        with self.assertRaisesRegex(ValueError, "refusing"):
            update(base)
        with self.assertRaisesRegex(ValueError, "customized"):
            update(base, undo=True)

    def test_malformed_config_rejected_while_valid_config_accepts_boolean(self):
        base = json.loads((ROOT / "routes.heartbeat-versions9.example.json").read_text())
        with TemporaryDirectory() as temp:
            path = Path(temp) / "routes.json"
            path.write_text(json.dumps(update(base)))
            decoded = read_routes(path)
            entry = "/"+DEQUEUE
            self.assertIs(decoded[entry][1]["provider_has_subscription"], True)
            base[DEQUEUE]["provider_has_subscription"] = "true"
            path.write_text(json.dumps(base))
            with self.assertRaisesRegex(ValueError, "boolean"):
                read_routes(path)


if __name__ == "__main__":
    unittest.main()
