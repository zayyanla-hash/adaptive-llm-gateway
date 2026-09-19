"""Concrete adapters per provider family.

All adapters run **offline by default** on top of the mock transport so the
gateway works with zero credentials. In ``live`` mode each adapter validates
its required env vars and would use ``urllib`` against the real endpoint;
without credentials it raises a structured CONFIG_ERROR instead of hanging.
No live calls are made by tests, eval, or demo.
"""
from __future__ import annotations

import os

from adaptive_gateway.errors import ErrorCode, GatewayError
from adaptive_gateway.providers.base import ProviderAdapter
from adaptive_gateway.providers.mock import MockProvider
from adaptive_gateway.registry import ModelSpec
from adaptive_gateway.types import ProviderResult, TaskRequest

_LIVE_REQUIRED_ENV = {
    "gemini": ("GEMINI_API_KEY",),
    "deepseek": ("DEEPSEEK_API_KEY",),
    "openai-compat": ("OPENAI_COMPAT_BASE_URL",),
    "local-qwen": (),
    "local-bonsai": (),
    "local-glimmer": (),
    "local-muse": (),
}


class ConfiguredAdapter(ProviderAdapter):
    """Family-aware adapter with mock transport + live-mode guard."""

    def __init__(
        self,
        spec: ModelSpec,
        mode: str = "mock",
        latency_ms: int | None = None,
        fail_mode: str = "none",
        cost_usd: float | None = None,
    ) -> None:
        self.spec = spec
        self.model_id = spec.model_id
        self.provider = spec.provider
        self.mode = mode
        est_cost = (spec.cost_per_1k_usd / 1000.0) * 500 if spec.cost_per_1k_usd else 0.0
        self._mock = MockProvider(
            model_id=spec.model_id,
            provider=spec.provider,
            latency_ms=latency_ms if latency_ms is not None else min(spec.avg_latency_ms, 120),
            fail_mode=fail_mode,
            cost_usd=cost_usd if cost_usd is not None else round(est_cost or 0.00005, 6),
            response_prefix=f"[{spec.family}]",
        )

    def _missing_live_env(self) -> list[str]:
        required = _LIVE_REQUIRED_ENV.get(self.provider, ())
        return [k for k in required if not os.environ.get(k)]

    def health_check(self) -> bool:
        if self.mode == "live":
            if self._missing_live_env():
                return False
        return self._mock.health_check()

    def invoke(self, request: TaskRequest, timeout_s: float) -> ProviderResult:
        if self.mode == "live":
            missing = self._missing_live_env()
            if missing:
                raise GatewayError(
                    ErrorCode.CONFIG_ERROR,
                    f"live mode for {self.provider} missing env: {', '.join(missing)}",
                    provider=self.provider,
                )
            # Live HTTP path intentionally not exercised offline; route via
            # mock transport with a clear marker until wired to real creds.
            result = self._mock.invoke(request, timeout_s)
            meta = dict(result.metadata)
            meta["live_requested_without_network"] = True
            return ProviderResult(
                model_id=result.model_id,
                text=result.text,
                latency_ms=result.latency_ms,
                cost_usd=result.cost_usd,
                provider=result.provider,
                metadata=meta,
            )
        return self._mock.invoke(request, timeout_s)


def build_default_adapters(
    specs: list[ModelSpec],
    mode: str = "mock",
    overrides: dict | None = None,
) -> dict[str, ProviderAdapter]:
    """Build one adapter per spec; ``overrides`` maps model_id -> behavior kwargs."""
    overrides = overrides or {}
    adapters: dict[str, ProviderAdapter] = {}
    for spec in specs:
        kw = dict(overrides.get(spec.model_id, {}))
        adapters[spec.model_id] = ConfiguredAdapter(spec, mode=mode, **kw)
    return adapters
