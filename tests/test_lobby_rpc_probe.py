"""Regression tests for reversible exact-guid lobby 404-vs-success A/B."""
import http.client
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest

from enable_lobby_rpc_probe import ROUTES, BARE, TARGETS, update_file, with_probe_routes
from enable_presence_menu_probe import add_probe_routes
from enable_presence_status_probe import modify_routes
from mvp_server import App, Server, make_handler, read_routes

ROOT = Path(__file__).resolve().parents[1]


def config():
    base = json.loads((ROOT / "routes.heartbeat-versions9.example.json").read_text())
    return modify_routes(add_probe_routes(base))


class LobbyRpcProbeTests(unittest.TestCase):
    def test_seven_exact_routes_only_and_rollback(self):
        original = config()
        mutated = with_probe_routes(original)
        self.assertEqual(7, len(TARGETS))
        self.assertEqual(len(mutated), len(original) + 7)
        for name, value in original.items():
            self.assertEqual(value, mutated[name])
        self.assertTrue(all(mutated[p] == BARE for p in ROUTES))
        self.assertEqual(mutated, with_probe_routes(mutated))
        self.assertEqual(original, with_probe_routes(mutated, undo=True))
        self.assertEqual(original, with_probe_routes(original, undo=True))

    def test_live_public_ips_and_nine_heartbeat_versions_survive(self):
        original = config()
        for c in original.values():
            if c.get("handler") == "dequeue":
                c["address"] = "198.51.100.33"
            if c.get("handler") == "environment_list":
                for dc in c["datacenters"]:
                    for ep in dc["endpoints"]:
                        ep["address"] = "198.51.100.33"
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "routes.remote.local.json"
            path.write_text(json.dumps(original), encoding="utf-8")
            self.assertEqual(7, update_file(path))
            after = json.loads(path.read_text())
            self.assertEqual(15, path.read_text().count("198.51.100.33"))
            for c in after.values():
                if c.get("handler") in ("heartbeat_register", "heartbeat_update"):
                    self.assertEqual([8802288]*9, c["heartbeat_version_values"])
            self.assertEqual(0, update_file(path))
            self.assertEqual(7, update_file(path, undo=True))
            self.assertEqual(original, json.loads(path.read_text()))

    def test_refuses_replace_or_delete_customized_routes_without_modifying_file(self):
        original = config()
        original[ROUTES[0]] = {"response_hex": "deadbeef"}
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "routes.json"
            path.write_text(json.dumps(original), encoding="utf-8")
            original_bytes = path.read_bytes()
            for undo in (False, True):
                with self.subTest(undo=undo):
                    with self.assertRaisesRegex(ValueError, "customized route"):
                        update_file(path, undo=undo)
                    self.assertEqual(original_bytes, path.read_bytes())

    def test_exact_http_200_only_seven_paths(self):
        original = config()
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "routes.json"
            path.write_text(json.dumps(with_probe_routes(original)))
            decoded = read_routes(path)
        server = Server(("127.0.0.1", 0), make_handler(App(decoded)))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            for route in ROUTES:
                with self.subTest(route=route):
                    conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
                    try:
                        conn.request("POST", "/" + route, body=b"")
                        r = conn.getresponse()
                        self.assertEqual(200, r.status)
                        self.assertEqual(b"\x08\x00", r.read())
                    finally:
                        conn.close()
            # Unobserved presence method should remain 404.
            conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
            try:
                conn.request("POST", "/b89429154e224660837a4a307391b0b4.svc/" + "a"*32, body=b"")
                r = conn.getresponse()
                self.assertEqual(404, r.status)
                r.read()
            finally:
                conn.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)


if __name__ == "__main__":
    unittest.main()
