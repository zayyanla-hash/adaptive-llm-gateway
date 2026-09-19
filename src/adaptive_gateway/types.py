"""Core request/result types shared by policy, router, server, and SDK."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

VALID_TASK_TYPES = (
    "code",
    "chat",
    "reasoning",
    "vision",
    "private_data",
    "fast",
    "tool_use",
)

VALID_DIFFICULTIES = ("easy", "medium", "hard")


@dataclass(frozen=True)
class TaskRequest:
    prompt: str
    task_type: str = "chat"
    difficulty: str = "medium"
    max_latency_ms: int | None = None
    max_cost_usd: float | None = None
    privacy_local_only: bool = False
    context_tokens: int = 1024
    needs_vision: bool = False
    needs_tools: bool = False
    metadata: dict = field(default_factory=dict)

    def validate(self) -> list[str]:
        problems: list[str] = []
        if not self.prompt or not self.prompt.strip():
            problems.append("prompt must be a non-empty string")
        if self.task_type not in VALID_TASK_TYPES:
            problems.append(f"task_type must be one of {list(VALID_TASK_TYPES)}")
        if self.difficulty not in VALID_DIFFICULTIES:
            problems.append(f"difficulty must be one of {list(VALID_DIFFICULTIES)}")
        if self.max_latency_ms is not None and self.max_latency_ms <= 0:
            problems.append("max_latency_ms must be > 0")
        if self.max_cost_usd is not None and self.max_cost_usd < 0:
            problems.append("max_cost_usd must be >= 0")
        if self.context_tokens <= 0:
            problems.append("context_tokens must be > 0")
        return problems

    @classmethod
    def from_dict(cls, raw: dict) -> TaskRequest:
        if not isinstance(raw, dict):
            raise ValueError("request body must be a JSON object")
        return cls(
            prompt=str(raw.get("prompt", "")),
            task_type=str(raw.get("task_type", "chat")),
            difficulty=str(raw.get("difficulty", "medium")),
            max_latency_ms=raw.get("max_latency_ms"),
            max_cost_usd=raw.get("max_cost_usd"),
            privacy_local_only=bool(raw.get("privacy_local_only", False)),
            context_tokens=int(raw.get("context_tokens", 1024)),
            needs_vision=bool(raw.get("needs_vision", False)),
            needs_tools=bool(raw.get("needs_tools", False)),
            metadata=dict(raw.get("metadata", {})),
        )

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ProviderResult:
    model_id: str
    text: str
    latency_ms: int
    cost_usd: float
    provider: str
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class RankedCandidate:
    model_id: str
    provider: str
    score: float
    subscores: dict
    reason_codes: list[str]
    excluded: bool = False
    exclude_reason: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class AttemptRecord:
    model_id: str
    provider: str
    attempt: int
    ok: bool
    latency_ms: int | None = None
    error_code: str | None = None
    error_message: str | None = None
    timeout_ms: int | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class RouteResult:
    request_id: str
    ok: bool
    escalated: bool
    model_id: str | None
    provider: str | None
    text: str | None
    latency_ms: int | None
    cost_usd: float | None
    attempts: list[AttemptRecord]
    ranked: list[RankedCandidate]
    weights: dict
    error: dict | None = None

    def to_dict(self) -> dict:
        return {
            "request_id": self.request_id,
            "ok": self.ok,
            "escalated": self.escalated,
            "model_id": self.model_id,
            "provider": self.provider,
            "text": self.text,
            "latency_ms": self.latency_ms,
            "cost_usd": self.cost_usd,
            "attempts": [a.to_dict() for a in self.attempts],
            "ranked": [r.to_dict() for r in self.ranked],
            "weights": dict(self.weights),
            "error": self.error,
        }
