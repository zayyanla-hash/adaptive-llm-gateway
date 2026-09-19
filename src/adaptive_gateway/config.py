"""Gateway configuration with strict validation.

Configuration can come from defaults, a dict (JSON file), and environment
variable overrides. Validation fails fast with structured problems so
misconfiguration is caught at startup, not mid-request.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

DEFAULT_WEIGHTS = {
    "task_affinity": 0.20,
    "quality": 0.20,
    "latency": 0.15,
    "cost": 0.10,
    "privacy": 0.10,
    "context": 0.08,
    "tools": 0.07,
    "health": 0.05,
    "history": 0.05,
}


@dataclass(frozen=True)
class GatewayConfig:
    weights: dict = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))
    max_attempts_per_provider: int = 2
    default_timeout_ms: int = 8000
    max_total_ms: int = 30000
    max_concurrency: int = 16
    health_fail_threshold: int = 3
    health_cooldown_s: float = 30.0
    mode: str = "mock"  # mock | live

    def validate(self) -> list[str]:
        problems: list[str] = []
        expected = set(DEFAULT_WEIGHTS)
        if set(self.weights or {}) != expected:
            problems.append(f"weights must contain exactly {sorted(expected)}")
        else:
            total = sum(float(v) for v in self.weights.values())
            if abs(total - 1.0) > 1e-6:
                problems.append(f"weights must sum to 1.0 (got {total})")
            for k, v in self.weights.items():
                try:
                    f = float(v)
                except (TypeError, ValueError):
                    problems.append(f"weight {k} must be numeric")
                    continue
                if not 0.0 <= f <= 1.0:
                    problems.append(f"weight {k} must be in [0,1]")
        if self.max_attempts_per_provider < 1 or self.max_attempts_per_provider > 5:
            problems.append("max_attempts_per_provider must be in [1,5]")
        if self.default_timeout_ms <= 0:
            problems.append("default_timeout_ms must be > 0")
        if self.max_total_ms <= 0:
            problems.append("max_total_ms must be > 0")
        if self.max_concurrency < 1 or self.max_concurrency > 256:
            problems.append("max_concurrency must be in [1,256]")
        if self.mode not in ("mock", "live"):
            problems.append("mode must be 'mock' or 'live'")
        return problems

    @classmethod
    def from_dict(cls, raw: dict | None) -> GatewayConfig:
        raw = raw or {}
        weights = dict(raw.get("weights", DEFAULT_WEIGHTS))
        return cls(
            weights=weights,
            max_attempts_per_provider=int(raw.get("max_attempts_per_provider", 2)),
            default_timeout_ms=int(raw.get("default_timeout_ms", 8000)),
            max_total_ms=int(raw.get("max_total_ms", 30000)),
            max_concurrency=int(raw.get("max_concurrency", 16)),
            health_fail_threshold=int(raw.get("health_fail_threshold", 3)),
            health_cooldown_s=float(raw.get("health_cooldown_s", 30.0)),
            mode=str(raw.get("mode", os.environ.get("GATEWAY_MODE", "mock"))),
        )

    @classmethod
    def from_env(cls) -> GatewayConfig:
        raw: dict = {"mode": os.environ.get("GATEWAY_MODE", "mock")}
        weights_json = os.environ.get("GATEWAY_WEIGHTS_JSON")
        if weights_json:
            try:
                raw["weights"] = json.loads(weights_json)
            except json.JSONDecodeError as exc:
                raise ValueError(f"GATEWAY_WEIGHTS_JSON is not valid JSON: {exc}") from exc
        for key, env in (
            ("max_attempts_per_provider", "GATEWAY_MAX_ATTEMPTS_PER_PROVIDER"),
            ("default_timeout_ms", "GATEWAY_DEFAULT_TIMEOUT_MS"),
            ("max_total_ms", "GATEWAY_MAX_TOTAL_MS"),
            ("max_concurrency", "GATEWAY_MAX_CONCURRENCY"),
        ):
            if os.environ.get(env):
                raw[key] = os.environ[env]
        cfg = cls.from_dict(raw)
        problems = cfg.validate()
        if problems:
            raise ValueError("invalid GatewayConfig: " + "; ".join(problems))
        return cfg


def load_config(path: str | None = None) -> GatewayConfig:
    """Load config from an optional JSON file layered over env/defaults."""
    base: dict = {}
    if path and os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            loaded = json.load(fh)
        if not isinstance(loaded, dict):
            raise ValueError("config file must contain a JSON object")
        base = loaded
    # Env overrides win over file for explicitly set keys.
    env_cfg = GatewayConfig.from_env()
    merged = dict(base)
    # Re-apply env-provided values on top of the file.
    if os.environ.get("GATEWAY_MODE"):
        merged["mode"] = os.environ["GATEWAY_MODE"]
    if os.environ.get("GATEWAY_WEIGHTS_JSON"):
        merged["weights"] = json.loads(os.environ["GATEWAY_WEIGHTS_JSON"])
    for key, env in (
        ("max_attempts_per_provider", "GATEWAY_MAX_ATTEMPTS_PER_PROVIDER"),
        ("default_timeout_ms", "GATEWAY_DEFAULT_TIMEOUT_MS"),
        ("max_total_ms", "GATEWAY_MAX_TOTAL_MS"),
        ("max_concurrency", "GATEWAY_MAX_CONCURRENCY"),
    ):
        if os.environ.get(env):
            merged[key] = type(getattr(env_cfg, key))(os.environ[env])
    cfg = GatewayConfig.from_dict(merged)
    problems = cfg.validate()
    if problems:
        raise ValueError("invalid GatewayConfig: " + "; ".join(problems))
    return cfg
