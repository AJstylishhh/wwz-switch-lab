"""Regression tests: opt-in provider environment is the only changed sign-in field."""
import json
from pathlib import Path
import tempfile
import unittest
from uuid import UUID

from auth_dequeue import Identity, encode_signin
from mvp_server import read_routes
from wwz_wire import fields

DUMMY = Identity(
    auth="dummy-auth", diagnostic="dummy-diagnostic", access="dummy-access",
    provider="dummy-provider", user_guid=UUID("00000000-0000-4000-8000-000000000001"),
    provider_user="dummy-user")
SETTINGS = dict(address="192.168.137.1", port=11704,
                name="wwz-production.wwzapi.com")


def find(data, n):
    return next(v for k, wire, v in fields(data) if k == n)


def signin(data):
    return find(find(data, 323326796), 1)


class ProviderEnvironmentTests(unittest.TestCase):
    def test_default_unchanged_but_alternative_contains_retail(self):
        baseline = encode_signin(DUMMY, ["service-a"], **SETTINGS)
        retail = encode_signin(DUMMY, ["service-a"], **SETTINGS,
                               provider_environment="Retail")
        self.assertFalse(any(n == 10 for n, _, _ in fields(signin(baseline))))
        optional = find(signin(retail), 10)
        self.assertEqual([(2, 0, 2)], list(fields(optional)))
        # Prove no other field was modified.
        without_optional = [(n, w, v) for n, w, v in fields(signin(retail)) if n != 10]
        self.assertEqual(list(fields(signin(baseline))), without_optional)

    def test_invalid_environments_are_rejected(self):
        with self.assertRaises(ValueError):
            encode_signin(DUMMY, ["service-a"], **SETTINGS,
                          provider_environment="UnknownServer")

    def test_alternate_route_file_is_single_variable(self):
        project = Path(__file__).resolve().parents[1]
        baseline = json.loads((project / "routes.mvp.example.json").read_text())
        retail = json.loads((project / "routes.provider-retail.example.json").read_text())
        self.assertEqual(set(baseline), set(retail))
        dequeue = next(k for k in baseline if baseline[k]["handler"] == "dequeue")
        self.assertEqual({**baseline[dequeue], "provider_environment": "Retail"},
                         retail[dequeue])
        for name in baseline:
            if name != dequeue:
                self.assertEqual(baseline[name], retail[name])
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "config.json"
            config.write_text(json.dumps(retail))
            parsed = read_routes(config)
            self.assertEqual("Retail", parsed["/" + dequeue][1]["provider_environment"])


if __name__ == "__main__":
    unittest.main()
