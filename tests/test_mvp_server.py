"""Local-only HTTP/1.1 and protobuf wire tests; NOT a Switch interoperability test."""
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest

from mvp_server import App, make_server, read_routes
from wwz_wire import ENVIRONMENT_ROUTE, environment_result, fields, blob, string, scalar, describe_environment_request


class TestMvp(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)
        self.route_path = self.folder / "routes.json"
        self.route_path.write_text(json.dumps({ENVIRONMENT_ROUTE: {
            "handler": "environment_list", "address": "192.168.137.1",
            "port": 11704, "name": "wwz-production.wwzapi.com",
            "environment_id": "Retail", "region": "local"}}))
        self.server = make_server("127.0.0.1", 0, App(read_routes(self.route_path)))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)

    def tearDown(self):
        self.conn.close()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(3)
        self.temp.cleanup()

    def test_health_and_keepalive(self):
        self.conn.request("GET", "/healthz")
        response = self.conn.getresponse()
        self.assertEqual(200, response.status)
        response.read()
        self.conn.request("GET", "/healthz")
        response = self.conn.getresponse()
        self.assertEqual(200, response.status)
        response.read()

    def test_environment_route(self):
        self.conn.request("POST", ENVIRONMENT_ROUTE, blob(1, string(1, "Retail")))
        response = self.conn.getresponse()
        self.assertEqual(200, response.status)
        self.assertEqual("application/protobuf", response.getheader("Content-Type"))
        data = response.read()
        self.assertEqual([(1, 0), (86868329, 2)], [(n, w) for n, w, _ in fields(data)])
        self.assertEqual(data, environment_result("192.168.137.1", 11704,
                        "wwz-production.wwzapi.com", "Retail", "local"))

    def test_unknown_rpc(self):
        self.conn.request("POST", "/" + "f"*32 + ".svc/" + "e"*32, b"")
        response = self.conn.getresponse()
        self.assertEqual(404, response.status)
        response.read()

    def test_request_metadata_redaction(self):
        request = blob(1, string(1, "Retail") + string(2, "PREBUILD") +
                       string(5, "sensitive-fingerprint")) + blob(2, string(1, "x"))
        result = describe_environment_request(request)
        self.assertEqual(1, result["service_versions"])
        self.assertNotIn("sensitive-fingerprint", str(result))

    def test_bad_config(self):
        self.route_path.write_text(json.dumps({"INVALID": {"response_hex": "0800"}}))
        with self.assertRaises(ValueError):
            read_routes(self.route_path)


if __name__ == "__main__":
    unittest.main()
