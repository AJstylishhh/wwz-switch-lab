"""Test that optional mock data center is schema-shaped and default stays stable."""
import json
from pathlib import Path
import tempfile
import unittest

from mvp_server import read_routes
from wwz_wire import ENVIRONMENT_ROUTE, environment_result, fields


def nested(data, number):
    return next(value for field, wire, value in fields(data) if field == number and wire == 2)


class EnvironmentDatacenterTests(unittest.TestCase):
    def test_optional_datacenter_is_not_in_default(self):
        base = environment_result("192.168.137.1", 11704,
                                  "wwz-production.wwzapi.com", "Retail", "local")
        with_dc = environment_result("192.168.137.1", 11704,
                                     "wwz-production.wwzapi.com", "Retail", "local",
                                     datacenter_id="local")
        def environment(raw):
            return nested(nested(nested(raw, 86868329), 1), 1)
        self.assertFalse(any(n == 5 for n, w, _ in fields(environment(base))))
        dc = nested(environment(with_dc), 5)
        self.assertEqual(b"local", nested(dc, 1))
        self.assertTrue(nested(dc, 4))
        self.assertNotEqual(base, with_dc)

    def test_config_is_opt_in(self):
        with tempfile.TemporaryDirectory() as tmp:
            routes = json.loads((Path(__file__).resolve().parents[1] /
                                  "routes.datacenter.example.json").read_text())
            route = Path(tmp) / "config.json"
            route.write_text(json.dumps(routes))
            data = read_routes(route)[ENVIRONMENT_ROUTE][1]
            self.assertTrue(data)
            env = nested(nested(nested(data, 86868329), 1), 1)
            self.assertTrue(any(n == 5 for n, w, _ in fields(env)))


if __name__ == "__main__":
    unittest.main()
