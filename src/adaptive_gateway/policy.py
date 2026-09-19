"""Deterministic policy engine: multi-signal scoring with reason codes.

This is NOT a keyword router. Every candidate model is scored across nine
signals (task affinity, expected quality, latency, cost, privacy, context,
tool capability, health, history). Hard safety gates (privacy, context,
required capabilities, circuit-open health) exclude candidates before
ranking. Output is a ranked list plus a decision trace (subscores, reason
codes, weights) so any decision is auditable.

Scoring is fully deterministic: same inputs -> same ranking; ties break by
model_id sort.
"""
from __future__ import annotations

from adaptive_gateway.config import GatewayConfig
from adaptive_gateway.registry import ModelSpec
from adaptive_gateway.types import RankedCandidate, TaskRequest

DIFFICULTY_QUALITY_FLOOR = {"easy": 0.0, "medium": 0.55, "hard": 0.75}


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def score_candidates(
    request: TaskRequest,
    specs: list[ModelSpec],
    health: dict[str, bool] | None = None,
    history_scores: dict[str, float] | None = None,
    config: GatewayConfig | None = None,
) -> list[RankedCandidate]:
    from adaptive_gateway.config import GatewayConfig as _GC

    cfg = config or _GC.from_dict({})
    weights = cfg.weights
    health = health or {}
    history_scores = history_scores or {}
    ranked: list[RankedCandidate] = []

    for spec in sorted(specs, key=lambda s: s.model_id):
        reasons: list[str] = []
        sub: dict[str, float] = {}

        # --- Hard gates (exclusions) ---
        if request.privacy_local_only and spec.hosted != "local":
            ranked.append(RankedCandidate(
                spec.model_id, spec.provider, 0.0, {},
                ["PRIVACY_VIOLATION"], True, "cloud model for local-only task"))
            continue
        if request.context_tokens > spec.context_window:
            ranked.append(RankedCandidate(spec.model_id, spec.provider, 0.0, {},
                                          ["CONTEXT_OVERFLOW"], True, "context exceeds window"))
            continue
        if request.needs_vision and not spec.supports_vision:
            ranked.append(RankedCandidate(spec.model_id, spec.provider, 0.0, {},
                                          ["TOOL_MISSING_VISION"], True, "vision required"))
            continue
        if request.needs_tools and not spec.supports_tools:
            ranked.append(RankedCandidate(spec.model_id, spec.provider, 0.0, {},
                                          ["TOOL_MISSING_FUNCTION_CALLS"], True, "tools required"))
            continue
        if health.get(spec.model_id) is False:
            ranked.append(RankedCandidate(spec.model_id, spec.provider, 0.0, {},
                                          ["HEALTH_CIRCUIT_OPEN"], True, "circuit open"))
            continue

        # --- Soft signals (0..1 each) ---
        affinity = float(spec.strengths.get(request.task_type, 0.5))
        sub["task_affinity"] = _clamp01(affinity)
        reasons.append("TYPE_AFFINITY_HIGH" if affinity >= 0.75 else
                       ("TYPE_AFFINITY_MED" if affinity >= 0.5 else "TYPE_AFFINITY_LOW"))

        floor = DIFFICULTY_QUALITY_FLOOR.get(request.difficulty, 0.0)
        if spec.quality >= floor + 0.1:
            sub["quality"] = _clamp01(0.6 + 0.4 * spec.quality)
            reasons.append("QUALITY_STRONG")
        elif spec.quality >= floor:
            sub["quality"] = _clamp01(0.4 + 0.4 * spec.quality)
            reasons.append("QUALITY_ADEQUATE")
        else:
            sub["quality"] = _clamp01(0.2 * spec.quality)
            reasons.append("QUALITY_WEAK_FOR_DIFFICULTY")

        if request.max_latency_ms:
            ratio = spec.avg_latency_ms / max(1, request.max_latency_ms)
            sub["latency"] = _clamp01(1.0 - min(1.0, ratio))
            reasons.append("LATENCY_SLO_RISK" if ratio > 0.8 else "LATENCY_SLO_FIT")
        else:
            # Prefer faster models, normalized against 2s reference.
            sub["latency"] = _clamp01(1.0 - min(1.0, spec.avg_latency_ms / 2000.0))
            reasons.append("LATENCY_DEFAULT")

        est_cost = (spec.cost_per_1k_usd / 1000.0) * max(1, request.context_tokens) / 2
        if request.max_cost_usd is not None:
            if est_cost <= request.max_cost_usd:
                if est_cost == 0:
                    sub["cost"] = 1.0
                else:
                    sub["cost"] = _clamp01(1.0 - est_cost / (request.max_cost_usd + 1e-9) * 0.5)
                reasons.append("COST_WITHIN_BUDGET")
            else:
                sub["cost"] = 0.0
                reasons.append("COST_OVER_BUDGET")
        else:
            sub["cost"] = 1.0 if est_cost == 0 else _clamp01(1.0 / (1.0 + est_cost * 500))
            reasons.append("COST_DEFAULT")
        # Free local models get a small explicit marker when cost matters.
        if est_cost == 0 and request.max_cost_usd is not None:
            reasons.append("COST_FREE_LOCAL")

        if request.privacy_local_only:
            sub["privacy"] = 1.0 if spec.hosted == "local" else 0.0
            reasons.append("PRIVACY_OK_LOCAL")
        else:
            sub["privacy"] = 1.0 if spec.hosted == "local" else 0.7
            reasons.append("PRIVACY_OK" if spec.hosted == "local" else "PRIVACY_CLOUD_OK")

        headroom = spec.context_window / max(1, request.context_tokens)
        sub["context"] = _clamp01(min(1.0, headroom / 8.0))
        reasons.append("CONTEXT_FIT" if headroom >= 2 else "CONTEXT_TIGHT")

        tool_score = 0.5
        if request.needs_tools or request.needs_vision:
            tool_score = 1.0  # passed hard gate
            reasons.append("TOOL_CAPABLE")
        elif spec.supports_tools:
            tool_score = 0.7
            reasons.append("TOOL_AVAILABLE")
        else:
            reasons.append("TOOL_NOT_NEEDED")
        sub["tools"] = tool_score

        if spec.model_id in health:
            sub["health"] = 1.0 if health[spec.model_id] else 0.0
            reasons.append("HEALTH_OK" if health[spec.model_id] else "HEALTH_DEGRADED")
        else:
            sub["health"] = 0.8
            reasons.append("HEALTH_UNKNOWN")

        hist = history_scores.get(spec.model_id, 0.5)
        sub["history"] = _clamp01(hist)
        if hist >= 0.7:
            reasons.append("HISTORY_GOOD")
        elif hist < 0.35:
            reasons.append("HISTORY_POOR")
        else:
            reasons.append("HISTORY_NEUTRAL")

        total = sum(sub[k] * float(weights[k]) for k in
                    ("task_affinity", "quality", "latency", "cost", "privacy",
                     "context", "tools", "health", "history"))
        ranked.append(RankedCandidate(
            model_id=spec.model_id, provider=spec.provider,
            score=round(total, 4), subscores={k: round(v, 4) for k, v in sub.items()},
            reason_codes=sorted(set(reasons)),
        ))

    # Safe candidates first by score desc, then model_id; excluded sink to bottom.
    ranked.sort(key=lambda c: (c.excluded, -c.score, c.model_id))
    return ranked
