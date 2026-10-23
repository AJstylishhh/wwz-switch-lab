"""Single-variable environment response envelope experiment."""
import json
from pathlib import Path
import tempfile
import unittest

from mvp_server import read_routes
from wwz_wire import ENVIRONMENT_ROUTE, environment_result, fields

SETTINGS = dict(
    address="192.168.137.1", port=11704,
    name="wwz-production.wwzapi.com",
    environment_id="Retail", region="local",
)


class EnvironmentEnvelopeTests(unittest.TestCase):
    def test_only_optional_retcode_differ(self):
        baseline = environment_result(**SETTINGS)
        alternate = environment_result(**SETTINGS, include_retcode=False)
        self.assertEqual([(1, 0), (86868329, 2)],
                         [(n, w) for n, w, _ in fields(baseline)])
        self.assertEqual([(86868329, 2)],
                         [(n, w) for n, w, _ in fields(alternate)])
        self.assertEqual(baseline[2:], alternate)
        self.assertEqual(alternate, environment_result(**SETTINGS, include_retcode=False))

    def test_alt_config_only_adds_one_option(self):
        root = Path(__file__).resolve().parents[1]
        baseline = json.loads((root / "routes.mvp.example.json").read_text())
        altered = json.loads((root / "routes.environment-envelope.example.json").read_text())
        self.assertEqual(set(baseline), set(altered))
        for name in baseline:
            expected = dict(baseline[name])
            if expected.get("handler") == "environment_list":
                expected["include_retcode"] = False
            self.assertEqual(expected, altered[name])
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "routes.json"
            path.write_text(json.dumps(altered))
            self.assertEqual([(86868329, 2)],
                [(n, w) for n, w, v in fields(read_routes(path)[ENVIRONMENT_ROUTE][1])])


if __name__ == "__main__":
    unittest.main()
