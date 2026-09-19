"""Mock provider: deterministic offline stand-in for every adapter.

Behaviors are scripted per model_id so tests, eval, and demo can exercise
success, errors, and timeouts without any network or credentials.
"""
from __future__ import annotations

import time

from adaptive_gateway.errors import ErrorCode, GatewayError
from adaptive_gateway.providers.base import ProviderAdapter
from adaptive_gateway.types import ProviderResult, TaskRequest


class MockProvider(ProviderAdapter):
    def __init__(
        self,
        model_id: str,
        provider: str,
        latency_ms: int = 50,
        fail_mode: str = "none",  # none | error | timeout | flaky
        cost_usd: float = 0.0001,
        response_prefix: str = "[mock]",
        _fail_counter: dict | None = None,
    ) -> None:
        self.model_id = model_id
        self.provider = provider
        self.latency_ms = latency_ms
        self.fail_mode = fail_mode
        self.cost_usd = cost_usd
        self.response_prefix = response_prefix
        self.calls = 0
        self._shared = _fail_counter if _fail_counter is not None else {"n": 0}

    def health_check(self) -> bool:
        return self.fail_mode != "error"

    def invoke(self, request: TaskRequest, timeout_s: float) -> ProviderResult:
        self.calls += 1
        self._shared["n"] += 1
        latency_s = self.latency_ms / 1000.0
        if self.fail_mode == "timeout":
            # Sleep past the timeout so the router's timeout guard fires.
            time.sleep(timeout_s + 0.05)
            raise GatewayError(
                ErrorCode.PROVIDER_TIMEOUT,
                f"mock {self.model_id} exceeded timeout",
                provider=self.provider,
            )
        if self.fail_mode == "error":
            raise GatewayError(
                ErrorCode.PROVIDER_ERROR,
                f"mock {self.model_id} scripted failure",
                provider=self.provider,
            )
        if self.fail_mode == "flaky" and self._shared["n"] % 2 == 1:
            raise GatewayError(
                ErrorCode.PROVIDER_ERROR,
                f"mock {self.model_id} flaky failure (odd call)",
                provider=self.provider,
            )
        if latency_s > timeout_s:
            time.sleep(timeout_s + 0.02)
            raise GatewayError(
                ErrorCode.PROVIDER_TIMEOUT,
                f"mock {self.model_id} latency exceeds timeout",
                provider=self.provider,
            )
        time.sleep(min(latency_s, 0.05))  # keep suites fast; report scripted latency
        text = (
            f"{self.response_prefix}:{self.model_id} "
            f"task={request.task_type} diff={request.difficulty} :: "
            f"{request.prompt[:120]}"
        )
        return ProviderResult(
            model_id=self.model_id,
            text=text,
            latency_ms=self.latency_ms,
            cost_usd=self.cost_usd,
            provider=self.provider,
            metadata={"mock": True, "fail_mode": self.fail_mode},
        )
