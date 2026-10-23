"""TLS visibility regression tests; no client packet or real certificate."""
import logging
import unittest
from unittest.mock import patch

from mvp_server import App, Server, make_handler


class FakeTLSSocket:
    def settimeout(self, seconds):
        self.timeout = seconds

    def version(self):
        return "TLSv1.2"

    def selected_alpn_protocol(self):
        return "http/1.1"


class TLSVisibilityTests(unittest.TestCase):
    def test_success_logs_protocol_not_client_identity(self):
        server = Server(("127.0.0.1", 0), make_handler(App({})))
        try:
            fake = FakeTLSSocket()
            with patch("http.server.ThreadingHTTPServer.get_request",
                       return_value=(fake, ("192.168.137.115", 43132))), \
                 patch("mvp_server.ssl.SSLSocket", FakeTLSSocket), \
                 self.assertLogs("wwz.mvp", level=logging.INFO) as output:
                sock, addr = server.get_request()
            self.assertIs(sock, fake)
            self.assertEqual(addr, ("192.168.137.115", 43132))
            self.assertIn("TLS handshake OK", "\n".join(output.output))
            self.assertIn("alpn=http/1.1", "\n".join(output.output))
            self.assertNotIn("192.168.137.115", "\n".join(output.output))
        finally:
            server.server_close()

    def test_handshake_reset_logs_type_without_sensitive_detail(self):
        server = Server(("127.0.0.1", 0), make_handler(App({})))
        try:
            with patch("http.server.ThreadingHTTPServer.get_request",
                       side_effect=ConnectionResetError("client=192.168.137.115")), \
                 self.assertLogs("wwz.mvp", level=logging.WARNING) as output:
                with self.assertRaises(ConnectionResetError):
                    server.get_request()
            logs = "\n".join(output.output)
            self.assertIn("TCP/TLS accept failed", logs)
            self.assertIn("ConnectionResetError", logs)
            self.assertNotIn("192.168.137.115", logs)
        finally:
            server.server_close()


if __name__ == "__main__":
    unittest.main()
