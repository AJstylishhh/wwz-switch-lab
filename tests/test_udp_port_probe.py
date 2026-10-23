"""Synthetic local-only UDP observer test; no WWZ online services."""
import logging
import socket
import threading
import time
import unittest

from udp_port_probe import monitor


class UdpProbeTests(unittest.TestCase):
    def test_two_datagrams_one_peer(self):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as receiver:
            receiver.bind(("127.0.0.1", 0))
            port = receiver.getsockname()[1]
        result = []
        errors = []
        def listen():
            try:
                result.append(monitor("127.0.0.1", port, packet_limit=2, timeout=4))
            except Exception as exc:
                errors.append(exc)
        with self.assertLogs("wwz.udp-probe", level=logging.INFO) as captured:
            worker = threading.Thread(target=listen, daemon=True)
            worker.start()
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
                time.sleep(.15)
                for item in (b"private-udp-packet1", b"private-udp-packet2"):
                    sender.sendto(item, ("127.0.0.1", port))
                    time.sleep(.03)
            worker.join(5)
        self.assertFalse(worker.is_alive())
        self.assertFalse(errors, errors)
        self.assertEqual([(2, 1)], result)
        logs = "\n".join(captured.output)
        self.assertNotIn("private-udp", logs)
        self.assertNotIn("127.0.0.1", logs)

    def test_invalid_listener_options(self):
        for params in ({"port": 0}, {"port": 65536}, {"packet_limit": -1},
                       {"timeout": -1}):
            with self.assertRaises(ValueError):
                monitor(**params)


if __name__ == "__main__":
    unittest.main()
