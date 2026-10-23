"""Offline tests for opt-in upstream-shaped WWZ EnvironmentList fixture.

No real account data, copyrighted client bytes or public game endpoints.
"""
import json
from pathlib import Path
import tempfile
import time
import unittest

from mvp_server import read_routes
from wwz_wire import ENVIRONMENT_ROUTE, environment_result, fields


def children(data, number):
    return [value for n, wire, value in fields(data) if n == number and wire == 2]


def scalar_value(data, number):
    return [value for n, wire, value in fields(data) if n == number and wire == 0]


class ProductionEnvironmentShapeTests(unittest.TestCase):
    def test_local_four_centers_fourteen_udp_endpoints(self):
        base = Path(__file__).resolve().parents[1]
        path = base / "routes.environment-production-shape.example.json"
        conf = json.loads(path.read_text())
        env_conf = next(v for v in conf.values() if v.get("handler") == "environment_list")
        dequeue_conf = next(v for v in conf.values() if v.get("handler") == "dequeue")
        self.assertEqual("prod-Master-https", env_conf["environment_id"])
        self.assertEqual("West Europe", env_conf["region"])
        self.assertEqual("prod-Master-https", dequeue_conf["name"])
        self.assertEqual(4, len(env_conf["datacenters"]))
        self.assertEqual(14, sum(len(dc["endpoints"]) for dc in env_conf["datacenters"]))
        self.assertTrue(all(ep["address"] == "192.168.137.1"
                            for dc in env_conf["datacenters"] for ep in dc["endpoints"]))
        before = int(time.time() * 1000)
        raw = read_routes(path)[ENVIRONMENT_ROUTE][1]
        after = int(time.time() * 1000)
        self.assertEqual([86868329], [n for n, _, _ in fields(raw)])
        envelope = children(raw, 86868329)[0]
        env_list = children(envelope, 1)[0]
        timestamp = scalar_value(env_list, 2)[0]
        self.assertLessEqual(before, timestamp)
        self.assertLessEqual(timestamp, after)
        environment = children(env_list, 1)[0]
        self.assertEqual(b"prod-Master-https", children(environment, 2)[0])
        self.assertEqual(b"West Europe", children(environment, 3)[0])
        api_endpoint = children(environment, 1)[0]
        self.assertEqual([1], scalar_value(api_endpoint, 4))  # HTTPS
        centers = children(environment, 5)
        self.assertEqual(4, len(centers))
        game_eps = [ep for dc in centers for ep in children(dc, 4)]
        self.assertEqual(14, len(game_eps))
        for ep in game_eps:
            self.assertEqual(b"192.168.137.1", children(ep, 2)[0])
            self.assertEqual([50000], scalar_value(ep, 3))
            self.assertEqual([4], scalar_value(ep, 4))  # UDP
        self.assertFalse(scalar_value(environment, 6))  # optional maintenance omitted

    def test_heartbeat_and_occupation_consistent_with_environment(self):
        from post_login_wire import (
            heartbeat_register_result, heartbeat_update_result, data_center_result,
        )
        root = Path(__file__).resolve().parents[1]
        config = json.loads((root / "routes.environment-production-shape.example.json").read_text())
        env_conf = next(v for v in config.values() if v.get("handler") == "environment_list")
        ids = [dc["id"] for dc in env_conf["datacenters"]]
        parsed = read_routes(root / "routes.environment-production-shape.example.json")
        for method in ("heartbeat_register", "heartbeat_update", "datacenter_occupation"):
            params = next(v for v in config.values() if v.get("handler") == method)
            self.assertEqual(ids, params["datacenter_ids"])
        envelope_defs = (
            (heartbeat_register_result(data_centers=ids), 438369230, 4),
            (heartbeat_update_result(data_centers=ids), 417677176, 3),
            (data_center_result(data_centers=ids), 536714262, 1),
        )
        for reply, wrapper_num, repeated_field in envelope_defs:
            wrapper = children(reply, wrapper_num)[0]
            # List<DataCenterOccupation> has repeated data=1 directly;
            # heartbeat results contain a nested result data=1.
            container = wrapper if wrapper_num == 536714262 else children(wrapper, 1)[0]
            occupations = children(container, repeated_field)
            self.assertEqual(ids, [children(x, 1)[0].decode("utf-8") for x in occupations])
        self.assertEqual(4, sum(1 for _ in env_conf["datacenters"]))

    def test_original_fixture_still_matches_original_function(self):
        root = Path(__file__).resolve().parents[1]
        base = json.loads((root / "routes.mvp.example.json").read_text())
        cfg = next(v for v in base.values() if v["handler"] == "environment_list")
        value = read_routes(root / "routes.mvp.example.json")[ENVIRONMENT_ROUTE][1]
        self.assertEqual(value, environment_result(
            cfg["address"], cfg["port"], cfg["name"], cfg["environment_id"],
            cfg["region"], datacenter_id=cfg.get("datacenter_id"),
            include_retcode=cfg.get("include_retcode", True)))


if __name__ == "__main__":
    unittest.main()
