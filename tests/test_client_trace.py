"""Privacy-limited client correlation on a concurrent WWZ lab server."""
import http.client
import logging
import re
import threading
import unittest

from mvp_server import App, Server, make_handler


class ClientTraceTests(unittest.TestCase):
    def test_opt_in_ephemeral_tags_do_not_reveal_source_or_credentials(self):
        ip_a = "198.51.100.10"
        ip_b = "198.51.100.11"
        secret_a = "lab-auth-DO_NOT_LOG_999"
        secret_b = "lab-auth-DO_NOT_LOG_333"
        app = App({}, trace_clients=True)
        a = app.observation_label(ip_a, {"Authorization": secret_a})
        again = app.observation_label(ip_a, {"Authorization": secret_a})
        b = app.observation_label(ip_b, {"Authorization": secret_b})
        self.assertEqual(a, again)
        self.assertNotEqual(a, b)
        for private in (ip_a, ip_b, secret_a, secret_b):
            self.assertNotIn(private, a + b)
        self.assertRegex(a, r"source_tag=[a-f0-9]{12}")
        self.assertRegex(a, r"credential_tag=[a-f0-9]{12}")
        self.assertIn("credential_header=authorization", a)
        self.assertNotEqual(
            app.observation_label(ip_a, {"Authorization": secret_b}), a)
        # Default is intentionally silent. Restarted app has a new random key.
        self.assertEqual("", App({}).observation_label(ip_a, {"Authorization": secret_a}))
        self.assertNotEqual(a, App({}, trace_clients=True).observation_label(
            ip_a, {"Authorization": secret_a}))

    def test_ip_only_without_known_auth_headers(self):
        app = App({}, trace_clients=True)
        a = app.observation_label("192.0.2.21", {})
        self.assertIn("source_tag=", a)
        self.assertNotIn("credential_tag=", a)
        self.assertEqual(a, app.observation_label("192.0.2.21", {"User-Agent": "example"}))

    def test_http_logging_exposes_only_tags(self):
        app = App({}, trace_clients=True)
        server = Server(("127.0.0.1", 0), make_handler(app))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with self.assertLogs("wwz.mvp", level=logging.INFO) as logs:
                conn = http.client.HTTPConnection(
                    "127.0.0.1", server.server_port, timeout=3)
                try:
                    conn.request(
                        "POST", "/not-a-service", body=b"",
                        headers={"Authorization": "lab-auth-SYNTHETIC_SECRET"})
                    resp = conn.getresponse()
                    self.assertEqual(404, resp.status)
                    resp.read()
                finally:
                    conn.close()
            output = "\n".join(logs.output)
            self.assertIn("source_tag=", output)
            self.assertIn("credential_tag=", output)
            self.assertNotIn("lab-auth-SYNTHETIC_SECRET", output)
            self.assertNotIn("127.0.0.1", output)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)


if __name__ == "__main__":
    unittest.main()
