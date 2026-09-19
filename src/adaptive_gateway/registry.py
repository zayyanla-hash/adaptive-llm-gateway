"""Model registry: synthetic, offline catalog of supported models/providers.

Covers the required families without needing credentials or services:
local Qwen / Bonsai / Glimmer / Muse, Gemini, DeepSeek, and a generic
OpenAI-compatible endpoint. All numbers are *synthetic defaults* for
offline routing/scoring — not live benchmarks.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ModelSpec:
    model_id: str
    provider: str
    family: str
    hosted: str  # "local" | "cloud"
    cost_per_1k_usd: float
    avg_latency_ms: int
    quality: float  # 0..1 general capability proxy (synthetic)
    context_window: int
    supports_vision: bool
    supports_tools: bool
    strengths: dict = field(default_factory=dict)  # task_type -> 0..1 affinity

    def to_dict(self) -> dict:
        return {
            "model_id": self.model_id,
            "provider": self.provider,
            "family": self.family,
            "hosted": self.hosted,
            "cost_per_1k_usd": self.cost_per_1k_usd,
            "avg_latency_ms": self.avg_latency_ms,
            "quality": self.quality,
            "context_window": self.context_window,
            "supports_vision": self.supports_vision,
            "supports_tools": self.supports_tools,
            "strengths": dict(self.strengths),
        }


def default_catalog() -> list[ModelSpec]:
    return [
        ModelSpec(
            model_id="qwen3-8b-local",
            provider="local-qwen",
            family="qwen",
            hosted="local",
            cost_per_1k_usd=0.0,
            avg_latency_ms=900,
            quality=0.72,
            context_window=32768,
            supports_vision=False,
            supports_tools=True,
            strengths={"code": 0.85, "chat": 0.7, "reasoning": 0.75, "vision": 0.1,
                        "private_data": 0.9, "fast": 0.6, "tool_use": 0.8},
        ),
        ModelSpec(
            model_id="bonsai-7b-local",
            provider="local-bonsai",
            family="bonsai",
            hosted="local",
            cost_per_1k_usd=0.0,
            avg_latency_ms=500,
            quality=0.60,
            context_window=16384,
            supports_vision=False,
            supports_tools=False,
            strengths={"code": 0.5, "chat": 0.65, "reasoning": 0.5, "vision": 0.05,
                        "private_data": 0.85, "fast": 0.95, "tool_use": 0.2},
        ),
        ModelSpec(
            model_id="glimmer-vl-local",
            provider="local-glimmer",
            family="glimmer",
            hosted="local",
            cost_per_1k_usd=0.0,
            avg_latency_ms=1200,
            quality=0.68,
            context_window=32768,
            supports_vision=True,
            supports_tools=True,
            strengths={"code": 0.55, "chat": 0.7, "reasoning": 0.6, "vision": 0.9,
                        "private_data": 0.9, "fast": 0.5, "tool_use": 0.7},
        ),
        ModelSpec(
            model_id="muse-7b-local",
            provider="local-muse",
            family="muse",
            hosted="local",
            cost_per_1k_usd=0.0,
            avg_latency_ms=700,
            quality=0.64,
            context_window=32768,
            supports_vision=False,
            supports_tools=True,
            strengths={"code": 0.7, "chat": 0.7, "reasoning": 0.65, "vision": 0.1,
                        "private_data": 0.88, "fast": 0.7, "tool_use": 0.75},
        ),
        ModelSpec(
            model_id="gemini-2.5-flash",
            provider="gemini",
            family="gemini",
            hosted="cloud",
            cost_per_1k_usd=0.0004,
            avg_latency_ms=1100,
            quality=0.86,
            context_window=1_000_000,
            supports_vision=True,
            supports_tools=True,
            strengths={"code": 0.8, "chat": 0.9, "reasoning": 0.85, "vision": 0.9,
                        "private_data": 0.2, "fast": 0.7, "tool_use": 0.9},
        ),
        ModelSpec(
            model_id="deepseek-chat-v3",
            provider="deepseek",
            family="deepseek",
            hosted="cloud",
            cost_per_1k_usd=0.0003,
            avg_latency_ms=1400,
            quality=0.88,
            context_window=128_000,
            supports_vision=False,
            supports_tools=True,
            strengths={"code": 1.0, "chat": 0.8, "reasoning": 0.95, "vision": 0.05,
                        "private_data": 0.2, "fast": 0.5, "tool_use": 0.8},
        ),
        ModelSpec(
            model_id="openai-compat-generic",
            provider="openai-compat",
            family="openai-compat",
            hosted="cloud",
            cost_per_1k_usd=0.0006,
            avg_latency_ms=900,
            quality=0.78,
            context_window=128_000,
            supports_vision=True,
            supports_tools=True,
            strengths={"code": 0.75, "chat": 0.85, "reasoning": 0.75, "vision": 0.8,
                        "private_data": 0.3, "fast": 0.75, "tool_use": 0.85},
        ),
    ]


class ModelRegistry:
    """Lookup + filtering over the model catalog (DI-friendly)."""

    def __init__(self, specs: list[ModelSpec] | None = None) -> None:
        self._specs: dict[str, ModelSpec] = {s.model_id: s for s in (specs or default_catalog())}

    def all(self) -> list[ModelSpec]:
        return sorted(self._specs.values(), key=lambda s: s.model_id)

    def get(self, model_id: str) -> ModelSpec | None:
        return self._specs.get(model_id)

    def providers(self) -> list[str]:
        return sorted({s.provider for s in self._specs.values()})
