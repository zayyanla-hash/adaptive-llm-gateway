"""Stdlib HTTP service exposing POST /route (+ /health, /metrics).

Zero runtime dependencies: built on http.server.ThreadingHTTPServer.
Graceful shutdown on SIGINT/SIGTERM; every response carries X-Request-ID.
"""
from __future__ import annotations

import json
import signal
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from adaptive_gateway.config import GatewayConfig
from adaptive_gateway.providers.adapters import build_default_adapters
from adaptive_gateway.registry import ModelRegistry
from adaptive_gateway.router import AdaptiveRouter
from adaptive_gateway.types import TaskRequest
from adaptive_gateway.version import __version__

MAX_BODY_BYTES = 256 * 1024


def build_router(config: GatewayConfig | None = None,
                 overrides: dict | None = None) -> AdaptiveRouter:
    cfg = config or GatewayConfig.from_dict({})
    registry = ModelRegistry()
    adapters = build_default_adapters(registry.all(), mode=cfg.mode, overrides=overrides)
    return AdaptiveRouter(registry, adapters, cfg)


class _Handler(BaseHTTPRequestHandler):
    router: AdaptiveRouter  # set by serve()

    def log_message(self, fmt: str, *args: object) -> None:  # quieter default log
        pass

    def _send(self, status: int, payload: dict, request_id: str) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Request-ID", request_id)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        rid = f"req-{uuid.uuid4().hex[:12]}"
        path = urlparse(self.path).path
        if path == "/health":
            checks = {}
            for spec in self.router.registry.all():
                adapter = self.router.adapters.get(spec.model_id)
                try:
                    checks[spec.model_id] = bool(adapter.health_check()) if adapter else False
                except Exception:
                    checks[spec.model_id] = False
            self._send(200, {"status": "ok", "version": __version__,
                             "mode": self.router.config.mode, "models": checks}, rid)
        elif path == "/metrics":
            self._send(200, self.router.telemetry.snapshot(), rid)
        elif path in ("/", "/docs"):
            self._send(200, {"service": "adaptive-llm-gateway", "version": __version__,
                             "routes": ["POST /route", "GET /health", "GET /metrics"]}, rid)
        else:
            self._send(404, {"error": {"code": "NOT_FOUND", "message": f"no route {path}"}}, rid)

    def do_POST(self) -> None:  # noqa: N802
        rid = self.headers.get("X-Request-ID") or f"req-{uuid.uuid4().hex[:12]}"
        path = urlparse(self.path).path
        if path != "/route":
            self._send(404, {"error": {"code": "NOT_FOUND", "message": f"no route {path}"}}, rid)
            return
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY_BYTES:
            self._send(413, {"error": {"code": "VALIDATION_ERROR",
                                       "message": "body too large", "request_id": rid}}, rid)
            return
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode("utf-8") or "{}")
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._send(400, {"error": {"code": "VALIDATION_ERROR",
                                       "message": "invalid JSON body", "request_id": rid}}, rid)
            return
        try:
            request = TaskRequest.from_dict(body)
        except ValueError as exc:
            self._send(400, {"error": {"code": "VALIDATION_ERROR",
                                       "message": str(exc), "request_id": rid}}, rid)
            return
        result = self.router.route(request, request_id=rid)
        self._send(200 if result.ok else 503 if result.escalated else 500,
                   result.to_dict(), rid)


def serve(host: str = "127.0.0.1", port: int = 8080,
          config: GatewayConfig | None = None,
          overrides: dict | None = None) -> ThreadingHTTPServer:
    router = build_router(config, overrides)
    _Handler.router = router
    server = ThreadingHTTPServer((host, port), _Handler)
    server.daemon_threads = True

    def _stop(signum: int, frame: object) -> None:
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)
    try:
        print(f"adaptive-llm-gateway v{__version__} listening on http://{host}:{port} "
              f"(mode={router.config.mode})")
        server.serve_forever()
    finally:
        router.close()
    return server
