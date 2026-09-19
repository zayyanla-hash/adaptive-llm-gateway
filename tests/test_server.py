"""Server integration tests: POST /route, /health, /metrics over real HTTP."""
import json
import os
import sys
import threading
import unittest
import urllib.error
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from adaptive_gateway.config import GatewayConfig
from adaptive_gateway.server import _Handler, build_router


def _start_server():
    router = build_router(GatewayConfig.from_dict({}))
    _Handler.router = router
    from http.server import ThreadingHTTPServer
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    server.daemon_threads = True
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, router, port


def _post(port, payload):
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/route",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.status, json.loads(resp.read().decode())


def _get(port, path):
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=10) as resp:
        return resp.status, json.loads(resp.read().decode())


class TestServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server, cls.router, cls.port = _start_server()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.router.close()

    def test_route_ok(self):
        status, body = _post(self.port, {"prompt": "hello", "task_type": "chat"})
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])
        self.assertIn("ranked", body)
        self.assertIn("request_id", body)

    def test_route_private_stays_local(self):
        status, body = _post(self.port, {"prompt": "notes", "task_type": "private_data",
                                         "privacy_local_only": True})
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])
        self.assertNotIn(body["model_id"], ("gemini-2.5-flash", "deepseek-chat-v3"))

    def test_route_invalid_json_body(self):
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/route", data=b"{nope",
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            urllib.request.urlopen(req, timeout=10)
            self.fail("expected HTTP 400")
        except urllib.error.HTTPError as exc:
            self.assertEqual(exc.code, 400)

    def test_health_and_metrics(self):
        s, health = _get(self.port, "/health")
        self.assertEqual(s, 200)
        self.assertEqual(health["status"], "ok")
        self.assertIn("qwen3-8b-local", health["models"])
        s, metrics = _get(self.port, "/metrics")
        self.assertEqual(s, 200)
        self.assertIn("total_requests", metrics)


if __name__ == "__main__":
    unittest.main()
