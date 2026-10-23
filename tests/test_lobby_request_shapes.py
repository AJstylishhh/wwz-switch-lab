"""Lobby protocol observability and normal client-close handling tests."""
import http.client
import logging
from http.server import BaseHTTPRequestHandler
from unittest.mock import patch
import unittest

from mvp_server import App, Server, make_handler
from request_shape import unknown_request_summary, shape, eligible
from wwz_wire import blob, scalar


PRESENCE_SERVICE = "/b89429154e224660837a4a307391b0b4.svc/"
UNKNOWN_LOBBY = PRESENCE_SERVICE + "b2a1ab68eb464d7796c4e9f49247d3c8"
REDLYNX = "/redlynx.api.endpointdispatcher.endpointdispatcherapi/getenvironmentinfo"


class RequestShapeTests(unittest.TestCase):
    def test_protobuf_shapes_no_values_or_tokens(self):
        secret = b"fake-lobby-join-code-EXTREMELY-SECRET"
        raw = scalar(1, 6) + blob(2, secret)
        summary = unknown_request_summary(UNKNOWN_LOBBY, raw)
        self.assertEqual({
            "bytes": len(raw), "format": "protobuf",
            "fields": [{"field": 1, "wire": 0},
                       {"field": 2, "wire": 2, "size": len(secret)}]
        }, summary)
        self.assertNotIn(secret.decode(), str(summary))

    def test_limit_bad_wire_and_path_eligibility(self):
        self.assertEqual({"bytes": 2050, "format": "over_limit"},
                         shape(b"x" * 2050))
        self.assertEqual({"bytes": 1, "format": "unknown"}, shape(b"\xff"))
        self.assertTrue(eligible(REDLYNX))
        self.assertTrue(eligible(UNKNOWN_LOBBY))
        self.assertFalse(eligible("/random"))
        self.assertIsNone(unknown_request_summary("/not-our-route", b"test"))

    def test_unknown_and_redlynx_still_404_but_log_safe_shape(self):
        server = Server(("127.0.0.1", 0), make_handler(App({})))
        import threading
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with self.assertLogs("wwz.mvp", level=logging.INFO) as log:
                for route, raw in [(UNKNOWN_LOBBY, scalar(1, 2)),
                                   (REDLYNX, scalar(1, 8))]:
                    conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
                    try:
                        conn.request("POST", route, body=raw)
                        reply = conn.getresponse()
                        self.assertEqual(404, reply.status)
                        reply.read()
                    finally:
                        conn.close()
            logs = "\n".join(log.output)
            self.assertIn("Unimplemented RPC request shape", logs)
            self.assertIn("Unimplemented RedLynx environment request shape", logs)
            self.assertIn("'wire': 0", logs)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

    def test_connection_shutdown_exceptions_suppressed_only(self):
        Handler = make_handler(App({}))
        instance = Handler.__new__(Handler)
        for exc in (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            with self.subTest(exc=exc):
                with patch.object(BaseHTTPRequestHandler, "handle", side_effect=exc):
                    instance.handle()
        with patch.object(BaseHTTPRequestHandler, "handle",
                          side_effect=ValueError("unrelated bug")):
            with self.assertRaisesRegex(ValueError, "unrelated bug"):
                instance.handle()


if __name__ == "__main__":
    unittest.main()
