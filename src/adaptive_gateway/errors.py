"""Structured error taxonomy for the gateway.

Every failure that crosses the router/server boundary carries a stable
machine-readable ``code`` plus a human message, the offending provider
(if any), whether a retry could help, and the request id.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ErrorCode(str, Enum):
    VALIDATION_ERROR = "VALIDATION_ERROR"
    CONFIG_ERROR = "CONFIG_ERROR"
    PRIVACY_VIOLATION = "PRIVACY_VIOLATION"
    CONTEXT_OVERFLOW = "CONTEXT_OVERFLOW"
    TOOL_UNSUPPORTED = "TOOL_UNSUPPORTED"
    NO_SAFE_CANDIDATE = "NO_SAFE_CANDIDATE"
    PROVIDER_TIMEOUT = "PROVIDER_TIMEOUT"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    RATE_LIMITED = "RATE_LIMITED"
    ALL_PROVIDERS_FAILED = "ALL_PROVIDERS_FAILED"
    TIMEOUT_BUDGET_EXCEEDED = "TIMEOUT_BUDGET_EXCEEDED"
    ESCALATION_REQUIRED = "ESCALATION_REQUIRED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


_RETRYABLE = {
    ErrorCode.PROVIDER_TIMEOUT: True,
    ErrorCode.PROVIDER_ERROR: True,
    ErrorCode.RATE_LIMITED: True,
    ErrorCode.TIMEOUT_BUDGET_EXCEEDED: False,
    ErrorCode.ALL_PROVIDERS_FAILED: False,
    ErrorCode.NO_SAFE_CANDIDATE: False,
    ErrorCode.ESCALATION_REQUIRED: False,
    ErrorCode.VALIDATION_ERROR: False,
    ErrorCode.CONFIG_ERROR: False,
    ErrorCode.PRIVACY_VIOLATION: False,
    ErrorCode.CONTEXT_OVERFLOW: False,
    ErrorCode.TOOL_UNSUPPORTED: False,
    ErrorCode.INTERNAL_ERROR: False,
}


@dataclass(eq=False)
class GatewayError(Exception):
    code: ErrorCode
    message: str
    provider: str | None = None
    request_id: str | None = None
    retryable: bool | None = None
    details: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.retryable is None:
            self.retryable = _RETRYABLE.get(self.code, False)

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"[{self.code.value}] {self.message}"

    def to_dict(self) -> dict:
        return {
            "code": self.code.value,
            "message": self.message,
            "provider": self.provider,
            "request_id": self.request_id,
            "retryable": bool(self.retryable),
            "details": dict(self.details),
        }
