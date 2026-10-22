"""Integration tests with real localhost UDP packets."""
import http.client
import json
import socket
import threading
import unittest

from p2p_lab import Directory, ControlServer, UDPServer, REGISTER, ACK


class DirectoryTests(unittest.TestCase):
    def test_registration_and_opaque_forward(self):
        d = Directory()
        host = d.create()
        guest = d.join(host["room"])
        with self.assertRaises(ValueError):
            d.join(host["room"])
        a = ("127.0.0.1", 10001)
        b = ("127.0.0.1", 10002)
        self.assertEqual((ACK, a), d.packet(REGISTER + host["token"].encode(), a))
        self.assertEqual((ACK, b), d.packet(REGISTER + guest["token"].encode(), b))
        payload = b"\0\xff\x01some opaque bytes"
        self.assertEqual((payload, b), d.packet(payload, a))
        self.assertEqual((payload, a), d.packet(payload, b))
        self.assertIsNone(d.packet(payload, ("127.0.0.1", 9000)))
        self.assertTrue(d.status(host["token"])["guest_ready"])

    def test_udp_loopback(self):
        d = Directory()
        host = d.create()
        guest = d.join(host["room"])
        server = UDPServer(("127.0.0.1", 0), d)
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        a = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        b = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            a.settimeout(2)
            b.settimeout(2)
            a.sendto(REGISTER + host["token"].encode(), server.server_address)
            self.assertEqual(ACK, a.recvfrom(4096)[0])
            b.sendto(REGISTER + guest["token"].encode(), server.server_address)
            self.assertEqual(ACK, b.recvfrom(4096)[0])
            payload = b"\0\xf9\x00hello"
            a.sendto(payload, server.server_address)
            self.assertEqual(payload, b.recvfrom(4096)[0])
        finally:
            a.close()
            b.close()
            server.shutdown()
            server.server_close()
            t.join(2)

    def test_http_directory(self):
        d = Directory()
        server = ControlServer(("127.0.0.1", 0), d)
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        c = http.client.HTTPConnection(*server.server_address, timeout=2)
        try:
            def call(path, body):
                c.request("POST", path, json.dumps(body),
                          {"Content-Type": "application/json"})
                r = c.getresponse()
                return r.status, json.loads(r.read())
            code, host = call("/lab/create", {})
            self.assertEqual(200, code)
            code, guest = call("/lab/join", {"room": host["room"]})
            self.assertEqual(200, code)
            self.assertNotEqual(host["token"], guest["token"])
            code, _ = call("/lab/join", {"room": host["room"]})
            self.assertEqual(400, code)
            code, status = call("/lab/status", {"token": guest["token"]})
            self.assertEqual("guest", status["role"])
        finally:
            c.close()
            server.shutdown()
            server.server_close()
            t.join(2)


if __name__ == "__main__":
    unittest.main()
