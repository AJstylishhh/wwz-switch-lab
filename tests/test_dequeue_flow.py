"""Offline integration: Enqueue -> Dequeue -> stable SignInResult -> reject unknown token."""
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest

from auth_dequeue import DEQUEUE_ROUTE, parse_dequeue
from queue_state import ENQUEUE_ROUTE
from mvp_server import App, make_server, read_routes
from wwz_wire import blob, string, scalar, fields


def version(index):
    return blob(2, string(1, f"{index:032x}") + scalar(2, 5) + scalar(3, 9))


def find(data, number):
    return next(v for n, w, v in fields(data) if n == number)


class TestDequeue(unittest.TestCase):
    def test_full_http_exchange(self):
        with tempfile.TemporaryDirectory() as temp:
            cfg = Path(temp) / "routes.json"
            cfg.write_text(json.dumps({
                ENQUEUE_ROUTE: {"handler": "enqueue"},
                DEQUEUE_ROUTE: {"handler": "dequeue", "address": "192.168.137.1",
                                "port": 11704, "name": "wwz-production.wwzapi.com"}
            }))
            server = make_server("127.0.0.1", 0, App(read_routes(cfg)))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
            try:
                enqueue = (blob(1, string(1, "Retail")) + blob(2, b"x" * 16) +
                           blob(3, b"fictional-credential") + blob(4, b"provider") +
                           blob(5, blob(1, b"test")) + blob(6, b"2026"))
                conn.request("POST", ENQUEUE_ROUTE, enqueue)
                reply = conn.getresponse()
                self.assertEqual(200, reply.status)
                token = find(find(find(find(reply.read(), 262225376), 1), 1), 1).decode()
                self.assertEqual(51, len(token))
                dequeue = blob(1, token.encode()) + b"".join(version(i) for i in range(19))
                self.assertEqual(813, len(dequeue))
                self.assertEqual(19, len(parse_dequeue(dequeue)[1]))
                responses = []
                for _ in range(2):
                    conn.request("POST", DEQUEUE_ROUTE, dequeue)
                    reply = conn.getresponse()
                    self.assertEqual(200, reply.status)
                    self.assertEqual("application/protobuf", reply.getheader("Content-Type"))
                    body = reply.read()
                    self.assertEqual([(1, 0), (323326796, 2)],
                                     [(n, w) for n, w, v in fields(body)])
                    sign_in = find(find(body, 323326796), 1)
                    self.assertTrue(find(sign_in, 1).startswith(b"lab-auth-"))
                    self.assertEqual(20, sum(n == 5 for n, w, v in fields(sign_in)))
                    self.assertTrue(find(find(sign_in, 8), 1))
                    responses.append(body)
                self.assertEqual(responses[0], responses[1])
                conn.request("POST", DEQUEUE_ROUTE, blob(1, b"wrong") + version(0))
                reply = conn.getresponse()
                self.assertEqual(400, reply.status)
                reply.read()
            finally:
                conn.close()
                server.shutdown()
                server.server_close()
                thread.join(timeout=3)

    def test_bad_wire_format(self):
        with self.assertRaises(ValueError):
            parse_dequeue(b"\x08\x00")
        with self.assertRaises(ValueError):
            parse_dequeue(blob(1, b"token"))


if __name__ == "__main__":
    unittest.main()
