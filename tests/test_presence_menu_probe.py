"""Regression tests for opt-in observed-presence 200-success probe."""
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest

from enable_presence_menu_probe import (
    EXPECTED_ROUTE_NAMES, RESPONSE, add_probe_routes, update_local_route
)
from mvp_server import App, Server, make_handler, read_routes

ROOT = Path(__file__).resolve().parents[1]


class PresenceMenuProbeTests(unittest.TestCase):
    def test_exactly_five_additions_and_no_unrelated_changes(self):
        original = json.loads((ROOT / "routes.heartbeat-versions9.example.json").read_text())
        modified = add_probe_routes(original)
        self.assertEqual(len(modified), len(original) + 5)
        for name in original:
            self.assertEqual(original[name], modified[name])
        for name in EXPECTED_ROUTE_NAMES:
            self.assertEqual(RESPONSE, modified[name])
        self.assertEqual(modified, add_probe_routes(modified))
        self.assertEqual(5, len(EXPECTED_ROUTE_NAMES))

    def test_private_remote_route_and_nine_heartbeat_entries_survive(self):
        original = json.loads((ROOT / "routes.heartbeat-versions9.example.json").read_text())
        for route in original.values():
            if route.get("handler") == "dequeue":
                route["address"] = "198.51.100.33"  # documentation-only address
            if route.get("handler") == "environment_list":
                for center in route["datacenters"]:
                    for endpoint in center["endpoints"]:
                        endpoint["address"] = "198.51.100.33"

        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "routes.remote.local.json"
            path.write_text(json.dumps(original), encoding="utf-8")
            self.assertEqual(5, update_local_route(path))
            self.assertEqual(0, update_local_route(path))
            result = json.loads(path.read_text())
            self.assertEqual(add_probe_routes(original), result)
            self.assertEqual(15, path.read_text().count("198.51.100.33"))
            for route in result.values():
                if route.get("handler") in ("heartbeat_register", "heartbeat_update"):
                    self.assertEqual([8802288] * 9, route["heartbeat_version_values"])

    def test_refuses_to_overwrite_existing_custom_route(self):
        original = json.loads((ROOT / "routes.heartbeat-versions9.example.json").read_text())
        original[EXPECTED_ROUTE_NAMES[0]] = {"response_hex": "1234"}
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "config.json"
            path.write_text(json.dumps(original), encoding="utf-8")
            before = path.read_bytes()
            with self.assertRaisesRegex(ValueError, "refusing to overwrite"):
                update_local_route(path)
            self.assertEqual(before, path.read_bytes())

    def test_result_is_http_200_with_only_protobuf_success(self):
        base = json.loads((ROOT / "routes.heartbeat-versions9.example.json").read_text())
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "routes.json"
            path.write_text(json.dumps(add_probe_routes(base)), encoding="utf-8")
            routes = read_routes(path)
        server = Server(("127.0.0.1", 0), make_handler(App(routes)))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            for route, body in zip(EXPECTED_ROUTE_NAMES,
                                   (b"\x08\x00\x10\x01", b"\x08\x00",
                                    b"\x08\x01", b"", b"")):
                with self.subTest(route=route):
                    conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
                    try:
                        conn.request("POST", "/" + route, body=body,
                                     headers={"Content-Type": "application/protobuf"})
                        reply = conn.getresponse()
                        self.assertEqual(200, reply.status)
                        self.assertEqual(b"\x08\x00", reply.read())
                    finally:
                        conn.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)


if __name__ == "__main__":
    unittest.main()
