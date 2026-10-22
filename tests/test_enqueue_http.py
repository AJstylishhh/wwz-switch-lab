"""HTTP tests for stateful Enqueue reply (no test-console or account required)."""
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
from mvp_server import read_routes, App, make_server
from queue_state import ENQUEUE_ROUTE
from wwz_wire import blob, string, fields


class LiveQueueTests(unittest.TestCase):
    def test_enqueue_repeated_and_malformed(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"routes.json"
            path.write_text(json.dumps({ENQUEUE_ROUTE:{"handler":"enqueue"}}))
            server=make_server("127.0.0.1",0,App(read_routes(path)))
            worker=threading.Thread(target=server.serve_forever,daemon=True)
            worker.start()
            conn=http.client.HTTPConnection("127.0.0.1",server.server_port,timeout=3)
            try:
                raw=(blob(1,string(1,"Retail"))+blob(2,b"user")+blob(3,b"private-secret")
                     +blob(4,b"provider")+blob(5,blob(1,b"test"))+blob(6,b"2026"))
                answers=[]
                for _ in range(2):
                    conn.request("POST",ENQUEUE_ROUTE,raw)
                    reply=conn.getresponse()
                    self.assertEqual(200,reply.status)
                    self.assertEqual("application/protobuf",reply.getheader("Content-Type"))
                    answers.append(reply.read())
                self.assertEqual(answers[0],answers[1])
                self.assertEqual([(1,0),(262225376,2)],
                                 [(n,w) for n,w,_ in fields(answers[0])])
                conn.request("POST",ENQUEUE_ROUTE,b"\x08\x00")
                reply=conn.getresponse()
                self.assertEqual(400,reply.status)
                reply.read()
            finally:
                conn.close()
                server.shutdown()
                server.server_close()
                worker.join(3)


if __name__=="__main__":
    unittest.main()
