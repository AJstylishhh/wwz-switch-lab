"""Privacy and grouping tests for batch WWZ RPC analysis."""
import json
import tempfile
import unittest
from pathlib import Path

from rpc_batch_probe import analyze, candidates, shape
from wwz_wire import blob, scalar, string


class BatchProbeTests(unittest.TestCase):
    def test_known_shapes(self):
        heartbeat = string(1, "0.1.DEV.8802288/PREBUILD") + scalar(2, 1) + scalar(3, 1)
        self.assertEqual(30, len(heartbeat))
        self.assertIn("IUserHeartbeatService_RegisterVersioned", candidates(shape(heartbeat)))
        self.assertEqual(26, len(string(1, "0.1.DEV.8802288/PREBUILD")))
        self.assertIn("IDataCenterService_GetDataCentersOccupation",
                      candidates(shape(string(1, "0.1.DEV.8802288/PREBUILD"))))
        self.assertIn("IDiagnosticDataService_WriteADFPack",
                      candidates(shape(blob(1, b"a"*15) + blob(2, b"b"*13)
                                       + blob(3, b"c"*12))))

    def test_captures_grouped_without_contents(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            for name, route, payload in (
                ("a", "/a.svc/z", blob(1, b"confidential-account")),
                ("b", "/a.svc/z", blob(1, b"other-secret")),
                ("c", "/b.svc/z", b""),
            ):
                (folder / (name+".json")).write_text(json.dumps({"path": route}))
                (folder / (name+".bin")).write_bytes(payload)
            result = analyze(folder)
            self.assertEqual(2, len(result["services"]))
            self.assertEqual(2, result["services"][0]["observations"])
            self.assertNotIn("confidential-account", str(result))
            self.assertNotIn("other-secret", str(result))


if __name__ == "__main__":
    unittest.main()
