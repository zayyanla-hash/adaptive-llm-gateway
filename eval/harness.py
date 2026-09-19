"""Offline evaluation harness (no network, no credentials, no live claims).

Runs every scenario in eval/fixtures/scenarios.json through the real
policy+router stack with scripted mock providers, checks routing
invariants, and writes:
  - eval/eval-results.json (machine-readable)
  - eval/REPORT.md (human-readable)

Usage:
  python -m eval.harness [--fixtures ... --out ... --report ...]
  pytest tests/test_eval.py
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from adaptive_gateway.config import GatewayConfig  # noqa: E402
from adaptive_gateway.providers.adapters import build_default_adapters  # noqa: E402
from adaptive_gateway.registry import ModelRegistry  # noqa: E402
from adaptive_gateway.router import AdaptiveRouter  # noqa: E402
from adaptive_gateway.types import TaskRequest  # noqa: E402
from adaptive_gateway.version import __version__  # noqa: E402

_HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_FIXTURES = os.path.join(_HERE, "fixtures", "scenarios.json")
DEFAULT_OUT = os.path.join(_HERE, "eval-results.json")
DEFAULT_REPORT = os.path.join(_HERE, "REPORT.md")


def _expand_overrides(raw: dict, model_ids: list[str]) -> dict:
    if "__all__" in raw:
        return {m: dict(raw["__all__"]) for m in model_ids}
    return dict(raw)


def check_expectation(
    scenario: dict, result: dict, registry: ModelRegistry
) -> tuple[bool, list[str]]:
    notes: list[str] = []
    ok = True
    expect = scenario.get("expect", {})

    def fail(msg: str) -> None:
        nonlocal ok
        ok = False
        notes.append("FAIL: " + msg)

    def note(msg: str) -> None:
        notes.append(msg)

    if "ok" in expect and result["ok"] != expect["ok"]:
        fail(f"expected ok={expect['ok']}, got {result['ok']}")
    if "escalated" in expect and result["escalated"] != expect["escalated"]:
        fail(f"expected escalated={expect['escalated']}, got {result['escalated']}")
    if expect.get("error_code"):
        got = (result.get("error") or {}).get("code")
        if got != expect["error_code"]:
            fail(f"expected error {expect['error_code']}, got {got}")
        else:
            note(f"error code {got} as expected")
    if expect.get("hosted") and result["ok"]:
        spec = registry.get(result["model_id"] or "")
        if not spec or spec.hosted != expect["hosted"]:
            fail(f"expected hosted={expect['hosted']}, routed to {result['model_id']}")
        else:
            note(f"hosted={spec.hosted} via {spec.model_id}")
    if expect.get("forbidden_models") and result["ok"]:
        if result["model_id"] in expect["forbidden_models"]:
            fail(f"routed to forbidden model {result['model_id']}")
    if expect.get("must_rank_first_in"):
        top = (result["ranked"] or [{}])[0].get("model_id")
        if top not in expect["must_rank_first_in"]:
            fail(f"expected top rank in {expect['must_rank_first_in']}, got {top}")
        else:
            note(f"top rank {top} acceptable")
    if expect.get("top_candidate"):
        top = (result["ranked"] or [{}])[0].get("model_id")
        if top != expect["top_candidate"]:
            fail(f"expected top {expect['top_candidate']}, got {top}")
        else:
            note(f"top rank {top} exact match")
    if expect.get("requires_capability") and result["ok"]:
        spec = registry.get(result["model_id"] or "")
        cap = expect["requires_capability"]
        good = (spec.supports_vision if cap == "vision" else spec.supports_tools) if spec else False
        if not good:
            fail(f"{result['model_id']} lacks capability {cap}")
        else:
            note(f"capability {cap} satisfied by {spec.model_id if spec else '?'}")
    if expect.get("min_attempts"):
        if len(result["attempts"]) < expect["min_attempts"]:
            fail(f"expected >= {expect['min_attempts']} attempts, got {len(result['attempts'])}")
        else:
            note(f"{len(result['attempts'])} attempts (fallback/retry exercised)")
    if expect.get("first_model_failed"):
        first = (result["attempts"] or [{}])[0]
        if first.get("model_id") != expect["first_model_failed"] or first.get("ok"):
            fail(f"expected first attempt to fail on {expect['first_model_failed']}, got {first}")
        else:
            note(f"fallback after {expect['first_model_failed']} failure")
    if expect.get("failed_with_timeout"):
        codes = [a.get("error_code") for a in result["attempts"]]
        if "PROVIDER_TIMEOUT" not in codes:
            fail(f"expected a PROVIDER_TIMEOUT attempt, got {codes}")
        else:
            note("timeout attempt observed, fallback succeeded")
    if result["ok"] and not result.get("text"):
        fail("ok=True but empty text")
    if not result["ok"] and result.get("text"):
        fail("failed result must not carry text")
    # Privacy invariant: local-only requests must never touch cloud.
    req = scenario.get("request", {})
    if req.get("privacy_local_only") and result["ok"]:
        spec = registry.get(result["model_id"] or "")
        if spec and spec.hosted != "local":
            fail("PRIVACY INVARIANT VIOLATED: cloud model served local-only request")
    return ok, notes


def run_eval(fixtures_path: str = DEFAULT_FIXTURES) -> dict:
    with open(fixtures_path, encoding="utf-8") as fh:
        bundle = json.load(fh)
    scenarios: list[dict] = bundle["scenarios"]
    registry = ModelRegistry()
    model_ids = [s.model_id for s in registry.all()]
    config = GatewayConfig.from_dict({})
    results: list[dict] = []
    passed = 0
    for sc in scenarios:
        overrides = _expand_overrides(sc.get("provider_overrides", {}), model_ids)
        adapters = build_default_adapters(registry.all(), mode="mock", overrides=overrides)
        router = AdaptiveRouter(registry, adapters, config)
        try:
            request = TaskRequest.from_dict(sc["request"])
            res = router.route(request, request_id=f"eval-{sc['id']}")
            rd = res.to_dict()
        finally:
            router.close()
        ok, notes = check_expectation(sc, rd, registry)
        passed += 1 if ok else 0
        results.append({"id": sc["id"], "description": sc.get("description", ""),
                        "passed": ok, "notes": notes, "result": rd})
    return {
        "gateway_version": __version__,
        "generated_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "mode": "offline-synthetic-mocks",
        "disclaimer": ("Synthetic offline fixtures with mock providers. "
                       "Not a live benchmark; makes no quality/latency claims "
                       "about real providers."),
        "total": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "pass_rate": round(passed / len(results), 4) if results else 0.0,
        "scenarios": results,
    }


def write_report(payload: dict, path: str) -> None:
    lines = [
        "# Adaptive Gateway — Offline Eval Report",
        "",
        f"- Version: `{payload['gateway_version']}`",
        f"- Generated: `{payload['generated_at']}`",
        f"- Mode: `{payload['mode']}`",
        f"- Result: **{payload['passed']}/{payload['total']} passed "
        f"({payload['pass_rate'] * 100:.1f}%)**",
        "",
        "> " + payload["disclaimer"],
        "",
        "| Scenario | Pass | Routed model | Attempts | Notes |",
        "|---|---|---|---|---|",
    ]
    for sc in payload["scenarios"]:
        r = sc["result"]
        mark = "PASS" if sc["passed"] else "FAIL"
        routed = r.get("model_id") or r.get("error", {}).get("code", "—")
        lines.append(f"| `{sc['id']}` | {mark} | `{routed}` "
                     f"| {len(r['attempts'])} | {'; '.join(sc['notes'])[:160]} |")
    lines += ["",
              "## Decision-trace sample (first scenario)",
              "",
              "```json",
              json.dumps(payload["scenarios"][0]["result"]["ranked"][:3], indent=2)[:2000],
              "```",
              ""]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run offline gateway eval")
    parser.add_argument("--fixtures", default=DEFAULT_FIXTURES)
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--report", default=DEFAULT_REPORT)
    args = parser.parse_args()
    payload = run_eval(args.fixtures)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
    write_report(payload, args.report)
    print(f"eval: {payload['passed']}/{payload['total']} passed "
          f"-> {args.out}, {args.report}")
    if payload["failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
