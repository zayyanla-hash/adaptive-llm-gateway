# Adaptive Gateway — Offline Eval Report

- Version: `0.1.0`
- Generated: `2026-09-19T10:18:26.537099+00:00`
- Mode: `offline-synthetic-mocks`
- Result: **10/10 passed (100.0%)**

> Synthetic offline fixtures with mock providers. Not a live benchmark; makes no quality/latency claims about real providers.

| Scenario | Pass | Routed model | Attempts | Notes |
|---|---|---|---|---|
| `coding-hard` | PASS | `deepseek-chat-v3` | 1 | hosted=cloud via deepseek-chat-v3; top rank deepseek-chat-v3 acceptable |
| `private-data-local-only` | PASS | `qwen3-8b-local` | 1 | hosted=local via qwen3-8b-local |
| `vision-needs-glimmer-or-cloud` | PASS | `glimmer-vl-local` | 1 | capability vision satisfied by glimmer-vl-local |
| `fast-tight-slo` | PASS | `bonsai-7b-local` | 1 | top rank bonsai-7b-local exact match |
| `fallback-on-primary-failure` | PASS | `gemini-2.5-flash` | 3 | 3 attempts (fallback/retry exercised); fallback after deepseek-chat-v3 failure |
| `retry-then-success-flaky` | PASS | `bonsai-7b-local` | 10 | 10 attempts (fallback/retry exercised) |
| `timeout-fallback` | PASS | `muse-7b-local` | 3 | 3 attempts (fallback/retry exercised); timeout attempt observed, fallback succeeded |
| `escalation-all-fail` | PASS | `ALL_PROVIDERS_FAILED` | 14 | error code ALL_PROVIDERS_FAILED as expected |
| `escalation-no-safe-candidate` | PASS | `NO_SAFE_CANDIDATE` | 0 | error code NO_SAFE_CANDIDATE as expected |
| `tools-require-function-calls` | PASS | `qwen3-8b-local` | 1 | capability tools satisfied by qwen3-8b-local |

## Decision-trace sample (first scenario)

```json
[
  {
    "model_id": "deepseek-chat-v3",
    "provider": "deepseek",
    "score": 0.7863,
    "subscores": {
      "task_affinity": 1.0,
      "quality": 0.952,
      "latency": 0.3,
      "cost": 0.7692,
      "privacy": 0.7,
      "context": 1.0,
      "tools": 0.7,
      "health": 1.0,
      "history": 0.5
    },
    "reason_codes": [
      "CONTEXT_FIT",
      "COST_DEFAULT",
      "HEALTH_OK",
      "HISTORY_NEUTRAL",
      "LATENCY_DEFAULT",
      "PRIVACY_CLOUD_OK",
      "QUALITY_STRONG",
      "TOOL_AVAILABLE",
      "TYPE_AFFINITY_HIGH"
    ],
    "excluded": false,
    "exclude_reason": null
  },
  {
    "model_id": "gemini-2.5-flash",
    "provider": "gemini",
    "score": 0.7617,
    "subscores": {
      "task_affinity": 0.8,
      "quality": 0.944,
      "latency": 0.45,
      "cost": 0.7143,
      "privacy": 0.7,
      "context": 1.0,
      "tools": 0.7,
      "health": 1.0,
      "history": 0.5
    },
    "reason_codes": [
      "CONTEXT_FIT",
      "COST_DEFAULT",
      "HEALTH_OK",
      "HISTORY_NEUTRAL",
      "LATENCY_DEFAULT",
      "PRIVACY_CLOUD_OK",
      "QUALITY_STRONG",
      "TOOL_AVAILABLE",
      "TYPE_AFFINITY_HIGH"
    ],
    "excluded": false,
    "exclude_reason": null
  },
  {
    "model_id": "openai-compat-generic",
    "provider": "openai-compat",
    "score": 0.7114,
    "subscores": {
      "task_affinity": 0.75,
      "quality": 0.712,
      "latency": 0.55,
      "cost": 0.625,
      "privacy": 0.7,
      "context": 1.0,
      "tools": 0.7,
      "health": 1.0,
      "history": 0.5
    },
    "reason_codes": [
      "CONTEXT_FIT",
      "COST_DEFAULT",
      "HEALTH_OK",
      "HISTORY_NEUTRAL",
      "LATENCY_DEFAULT",
      "PRIVACY_CLOUD_OK",
      "QUALITY_ADEQUATE",
      "TOOL_AVAILABLE",
      "TYPE_AFFINITY_HIGH"
    ],
    "excluded": false,
    "exclude_reason": null
  }
]
```
