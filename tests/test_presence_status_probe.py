"""Typed status-probe regression tests: exact protobuf fields, reversible edit."""
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest

from enable_presence_menu_probe import add_probe_routes
from enable_presence_status_probe import (
    SERVICE, TYPE_FIELD, METHOD_CANDIDATES, modify_routes,
    presence_status_reply, update_local_routes
)
from mvp_server import App, Server, make_handler, read_routes
from wwz_wire import fields

ROOT = Path(__file__).resolve().parents[1]


def nested_data(reply):
    top = list(fields(reply))
    assert top[0] == (1, 0, 0)
    assert len(top) == 2 and top[1][0] == TYPE_FIELD
    wrapped = list(fields(top[1][2]))
    assert len(wrapped) == 1 and wrapped[0][0] == 1
    return list(fields(wrapped[0][2]))


class TypedPresenceProbeTests(unittest.TestCase):
    def fixture(self):
        original = json.loads(
            (ROOT / "routes.heartbeat-versions9.example.json").read_text())
        return add_probe_routes(original)

    def test_descriptor_nested_fields_and_menu_state(self):
        self.assertEqual(1, nested_data(presence_status_reply("user"))[0][0])
        self.assertEqual(2, nested_data(presence_status_reply("squad"))[0][0])
        match = nested_data(presence_status_reply("matchmake"))
        self.assertEqual(3, match[0][0])
        response_fields = list(fields(match[0][2]))
        self.assertEqual((1, 0, 0), response_fields[0])
        inner_status = list(fields(response_fields[1][2]))
        self.assertEqual([(1, 0, 0)], inner_status)  # msMenu=0
        with self.assertRaises(ValueError):
            presence_status_reply("arbitrary")

    def test_exactly_three_changed_and_everything_else_preserved(self):
        original = self.fixture()
        typed = modify_routes(original)
        affected = {f"{SERVICE}.svc/{m}" for m in METHOD_CANDIDATES}
        self.assertEqual(3, len(affected))
        self.assertEqual({key for key in original if original[key] != typed[key]},
                         affected)
        for key in affected:
            self.assertNotEqual(original[key], typed[key])
        self.assertEqual(original, modify_routes(typed, undo=True))
        self.assertEqual(typed, modify_routes(typed))

    def test_local_ip_and_heartbeat_versions_unchanged(self):
        original = self.fixture()
        for data in original.values():
            if data.get("handler") == "dequeue":
                data["address"] = "198.51.100.33"
            if data.get("handler") == "environment_list":
                for dc in data["datacenters"]:
                    for ep in dc["endpoints"]:
                        ep["address"] = "198.51.100.33"
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "routes.remote.local.json"
            path.write_text(json.dumps(original), encoding="utf-8")
            update_local_routes(path)
            modified = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(modify_routes(original), modified)
            self.assertEqual(15, path.read_text().count("198.51.100.33"))
            for conf in modified.values():
                if conf.get("handler") in ("heartbeat_register", "heartbeat_update"):
                    self.assertEqual([8802288] * 9, conf["heartbeat_version_values"])
            update_local_routes(path, undo=True)
            self.assertEqual(original, json.loads(path.read_text()))

    def test_require_explicit_opt_in_existing_success_stubs(self):
        with self.assertRaisesRegex(ValueError, "missing presence success route"):
            modify_routes(json.loads((ROOT / "routes.heartbeat-versions9.example.json").read_text()))
        original = self.fixture()
        key = f"{SERVICE}.svc/{next(iter(METHOD_CANDIDATES))}"
        original[key] = {"response_hex": "ffff"}
        with self.assertRaisesRegex(ValueError, "refusing to overwrite"):
            modify_routes(original)

    def test_exact_http_wire_reply_for_all_three(self):
        original = self.fixture()
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "routes.json"
            path.write_text(json.dumps(modify_routes(original)), encoding="utf-8")
            routes = read_routes(path)
        server = Server(("127.0.0.1", 0), make_handler(App(routes)))
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            samples = {
                "squad": b"\x08\x00\x10\x00",
                "matchmake": b"\x08\x00",
                "user": b"",
            }
            for method, kind in METHOD_CANDIDATES.items():
                conn = http.client.HTTPConnection(
                    "127.0.0.1", server.server_port, timeout=3)
                try:
                    conn.request("POST", f"/{SERVICE}.svc/{method}",
                                 body=samples[kind],
                                 headers={"Content-Type": "application/protobuf"})
                    response = conn.getresponse()
                    self.assertEqual(200, response.status)
                    self.assertEqual(presence_status_reply(kind), response.read())
                finally:
                    conn.close()
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=3)


if __name__ == "__main__":
    unittest.main()
