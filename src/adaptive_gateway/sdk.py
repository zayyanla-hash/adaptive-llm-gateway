"""Reusable SDK / core library.

Two entry points:
  - :class:`GatewaySDK` — in-process use (import and call; DI-friendly).
  - :class:`GatewayHTTPClient` — thin urllib client for the HTTP service.

Both keep the same TaskRequest/RouteResult dict shapes as POST /route.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from adaptive_gateway.config import GatewayConfig
from adaptive_gateway.router import AdaptiveRouter
from adaptive_gateway.server import build_router
from adaptive_gateway.types import RouteResult, TaskRequest


class GatewaySDK:
    """In-process gateway client (no HTTP needed)."""

    def __init__(self, router: AdaptiveRouter | None = None,
                 config: GatewayConfig | None = None,
                 overrides: dict | None = None) -> None:
        self.router = router or build_router(config, overrides)

    def route(self, prompt: str, **kwargs: object) -> dict:
        request = TaskRequest(prompt=prompt, **kwargs)  # type: ignore[arg-type]
        return self.router.route(request).to_dict()

    def route_request(self, request: TaskRequest, request_id: str | None = None) -> RouteResult:
        return self.router.route(request, request_id=request_id)

    def close(self) -> None:
        self.router.close()


class GatewayHTTPClient:
    """Minimal stdlib HTTP client for a running gateway service."""

    def __init__(self, base_url: str = "http://127.0.0.1:8080", timeout_s: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s

    def route(self, prompt: str, **kwargs: object) -> dict:
        payload = {"prompt": prompt, **kwargs}
        req = urllib.request.Request(
            self.base_url + "/route",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            # Surface HTTP errors with bodies when available.
            if isinstance(exc, urllib.error.HTTPError):
                try:
                    return json.loads(exc.read().decode("utf-8"))
                except Exception:
                    pass
            raise

    def health(self) -> dict:
        with urllib.request.urlopen(self.base_url + "/health", timeout=self.timeout_s) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def metrics(self) -> dict:
        with urllib.request.urlopen(self.base_url + "/metrics", timeout=self.timeout_s) as resp:
            return json.loads(resp.read().decode("utf-8"))
