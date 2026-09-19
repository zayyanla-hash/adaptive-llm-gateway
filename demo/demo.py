"""End-to-end demo with mock providers (no network, no creds).

Scenarios: coding task, private-data (local-only), vision task, fast task,
plus failure/retry/fallback and escalation paths. Prints a readable trace.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from adaptive_gateway.config import GatewayConfig  # noqa: E402
from adaptive_gateway.providers.adapters import build_default_adapters  # noqa: E402
from adaptive_gateway.registry import ModelRegistry  # noqa: E402
from adaptive_gateway.router import AdaptiveRouter  # noqa: E402
from adaptive_gateway.sdk import GatewaySDK  # noqa: E402
from adaptive_gateway.types import TaskRequest  # noqa: E402


def _show(title: str, result: dict) -> None:
    print(f"\n=== {title} ===")
    print(f"ok={result['ok']} escalated={result['escalated']} "
          f"model={result['model_id']} provider={result['provider']} "
          f"latency={result['latency_ms']}ms cost=${result['cost_usd']}")
    if result["text"]:
        print(f"text: {result['text'][:150]}")
    if result["error"]:
        print(f"error: {result['error']['code']}: {result['error']['message'][:150]}")
    top3 = [(c["model_id"], c["score"]) for c in result["ranked"][:3]]
    print(f"top-3: {top3}")
    attempts = [(a["model_id"], a["ok"], a.get("error_code")) for a in result["attempts"]]
    print(f"attempts: {attempts}")


def main() -> None:
    registry = ModelRegistry()
    config = GatewayConfig.from_dict({})
    sdk = GatewaySDK(config=config)
    try:
        _show("1. coding task (hard)", sdk.route(
            "Refactor this async pool to fix the reconnect race.",
            task_type="code", difficulty="hard", context_tokens=4000))
        _show("2. private-data local-only", sdk.route(
            "Summarize these discharge notes.", task_type="private_data",
            difficulty="medium", privacy_local_only=True, context_tokens=2000))
        _show("3. vision task", sdk.route(
            "Describe the chart in this screenshot.", task_type="vision",
            difficulty="medium", needs_vision=True, context_tokens=1500))
        _show("4. fast task (tight SLO)", sdk.route(
            "ping", task_type="fast", difficulty="easy",
            max_latency_ms=600, context_tokens=64))
    finally:
        sdk.close()

    # 5. failure -> fallback (top code pick forced to error)
    adapters = build_default_adapters(
        registry.all(), mode="mock", overrides={"deepseek-chat-v3": {"fail_mode": "error"}})
    router = AdaptiveRouter(registry, adapters, config)
    try:
        _show("5. fallback after primary failure",
              router.route(TaskRequest(prompt="Write quicksort in Rust.",
                                       task_type="code", difficulty="hard"),
                           request_id="demo-fallback").to_dict())
    finally:
        router.close()

    # 6. escalation (total outage)
    adapters = build_default_adapters(
        registry.all(), mode="mock",
        overrides={s.model_id: {"fail_mode": "error"} for s in registry.all()})
    router = AdaptiveRouter(registry, adapters, config)
    try:
        _show("6. escalation (all providers fail)",
              router.route(TaskRequest(prompt="Hello?", task_type="chat"),
                           request_id="demo-escalation").to_dict())
    finally:
        router.close()

    print("\nDemo complete. Telemetry:", sdk.router.telemetry.snapshot())


if __name__ == "__main__":
    main()
