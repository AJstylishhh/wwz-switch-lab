"""Synthetic privacy and local-only echo tests for the WWZ UDP probe."""
import contextlib
import io
import socket
import threading
import unittest

from udp_probe_compare import echo_eligible, monitor, record_packet, printable_summary
from collections import Counter


class UdpCompareTests(unittest.TestCase):
    def test_local_echo_allowlist(self):
        self.assertTrue(echo_eligible(b"x" * 38, "192.168.137.13"))
        self.assertTrue(echo_eligible(b"x" * 38, "127.0.0.1"))
        self.assertFalse(echo_eligible(b"x" * 38, "8.8.8.8"))
        self.assertFalse(echo_eligible(b"x" * 38, "192.168.138.13"))
        self.assertFalse(echo_eligible(b"x" * 37, "192.168.137.13"))
        self.assertFalse(echo_eligible(b"x" * 38, "bogus"))

    def test_summaries_omit_raw_data_or_address(self):
        state = {
            "packets": 0, "sizes": Counter(), "digests": Counter(),
            "source_sockets": set(), "reflected": 0,
            "reflection_failures": 0, "reflection_skipped": 0,
            "first_at": None, "last_at": None,
        }
        payload = b"secret-key-privateuser" + b"x" * 16
        record_packet(state, payload, ("192.168.137.13", 12345))
        record_packet(state, payload, ("192.168.137.13", 12345))
        result = printable_summary(state)
        self.assertEqual(2, result["packets_received"])
        self.assertEqual(1, result["unique_payloads"])
        self.assertEqual([2], result["repeated_payload_groups"])
        self.assertNotIn("secret-key", str(result))
        self.assertNotIn("192.168", str(result))
        self.assertNotIn("12345", str(result))

    def test_optional_echo_only_for_38_bytes(self):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as socket_for_port:
            socket_for_port.bind(("127.0.0.1", 0))
            port = socket_for_port.getsockname()[1]
        started = threading.Event()
        result = []
        error = []
        output = io.StringIO()

        def worker():
            try:
                with contextlib.redirect_stdout(output):
                    result.append(monitor("127.0.0.1", port, echo_38=True,
                                          timeout=5, packet_limit=3, ready=started))
            except Exception as exc:
                error.append(exc)
                started.set()

        t = threading.Thread(target=worker, daemon=True)
        t.start()
        self.assertTrue(started.wait(3))
        secret_packet = b"p" * 38
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
            sender.settimeout(1)
            sender.sendto(secret_packet, ("127.0.0.1", port))
            self.assertEqual(secret_packet, sender.recvfrom(100)[0])
            sender.sendto(secret_packet, ("127.0.0.1", port))
            self.assertEqual(secret_packet, sender.recvfrom(100)[0])
            sender.sendto(b"q" * 37, ("127.0.0.1", port))
        t.join(6)
        self.assertFalse(t.is_alive())
        self.assertFalse(error, error)
        self.assertEqual(3, result[0]["packets_received"])
        self.assertEqual(2, result[0]["reflected"])
        self.assertEqual(1, result[0]["reflection_skipped"])
        self.assertEqual(2, result[0]["unique_payloads"])
        self.assertEqual([2], result[0]["repeated_payload_groups"])
        self.assertNotIn("127.0.0.1", output.getvalue())


if __name__ == "__main__":
    unittest.main()
