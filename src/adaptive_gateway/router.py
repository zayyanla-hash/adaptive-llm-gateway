"""Adaptive router: policy ranking + fallback chains + bounded retries/timeouts.

Flow per request:
  1. validate request
  2. score candidates via policy engine (with health + history signals)
  3. if no safe candidate -> structured escalation (NO_SAFE_CANDIDATE)
  4. else walk ranked list; per provider up to max_attempts with per-attempt
     timeout; record attempts, health, history, telemetry
  5. first success wins; if all fail -> escalation (ALL_PROVIDERS_FAILED)

Concurrency is bounded by a semaphore; total wall-clock is bounded by
max_total_ms. All decisions carry request_id + full decision trace.
"""
from __future__ import annotations

import concurrent.futures
import threading
import time
import uuid

from adaptive_gateway.config import GatewayConfig
from adaptive_gateway.errors import ErrorCode, GatewayError
from adaptive_gateway.health import HealthMonitor
from adaptive_gateway.history import SuccessHistory
from adaptive_gateway.policy import score_candidates
from adaptive_gateway.providers.base import ProviderAdapter
from adaptive_gateway.registry import ModelRegistry
from adaptive_gateway.telemetry import TelemetryStore
from adaptive_gateway.types import AttemptRecord, RankedCandidate, RouteResult, TaskRequest


class AdaptiveRouter:
    def __init__(
        self,
        registry: ModelRegistry,
        adapters: dict[str, ProviderAdapter],
        config: GatewayConfig | None = None,
        health: HealthMonitor | None = None,
        history: SuccessHistory | None = None,
        telemetry: TelemetryStore | None = None,
    ) -> None:
        self.registry = registry
        self.adapters = adapters
        self.config = config or GatewayConfig.from_dict({})
        problems = self.config.validate()
        if problems:
            raise ValueError("invalid GatewayConfig: " + "; ".join(problems))
        self.health = health or HealthMonitor(
            fail_threshold=self.config.health_fail_threshold,
            cooldown_s=self.config.health_cooldown_s,
        )
        self.history = history or SuccessHistory()
        self.telemetry = telemetry or TelemetryStore()
        self._sema = threading.Semaphore(self.config.max_concurrency)
        self._pool = concurrent.futures.ThreadPoolExecutor(
            max_workers=self.config.max_concurrency, thread_name_prefix="gateway-invoke"
        )

    def close(self) -> None:
        self._pool.shutdown(wait=True, cancel_futures=True)

    # -- public API -----------------------------------------------------
    def route(self, request: TaskRequest, request_id: str | None = None) -> RouteResult:
        rid = request_id or f"req-{uuid.uuid4().hex[:12]}"
        problems = request.validate()
        if problems:
            err = GatewayError(ErrorCode.VALIDATION_ERROR, "; ".join(problems), request_id=rid)
            return self._escalation(request, rid, [], [], err)
        if not self._sema.acquire(timeout=self.config.max_total_ms / 1000.0):
            err = GatewayError(ErrorCode.TIMEOUT_BUDGET_EXCEEDED,
                               "gateway at concurrency limit", request_id=rid)
            return self._escalation(request, rid, [], [], err)
        try:
            return self._route_inner(request, rid)
        finally:
            self._sema.release()

    # -- internals ------------------------------------------------------
    def _route_inner(self, request: TaskRequest, rid: str) -> RouteResult:
        specs = self.registry.all()
        avail = self.health.availability_map([s.model_id for s in specs])
        hist = self.history.scores_for(request.task_type)
        ranked = score_candidates(request, specs, avail, hist, self.config)
        safe = [c for c in ranked if not c.excluded]

        if not safe:
            err = GatewayError(
                ErrorCode.NO_SAFE_CANDIDATE,
                "no safe candidate: privacy/context/capability/health gates excluded all models",
                request_id=rid,
                details={"ranked": [c.to_dict() for c in ranked]},
            )
            return self._escalation(request, rid, ranked, [], err)

        attempts: list[AttemptRecord] = []
        deadline = time.time() + self.config.max_total_ms / 1000.0
        last_error: GatewayError | None = None

        for cand in safe:
            adapter = self.adapters.get(cand.model_id)
            if adapter is None:
                attempts.append(AttemptRecord(cand.model_id, cand.provider, 1, False,
                                              error_code=ErrorCode.CONFIG_ERROR.value,
                                              error_message="no adapter registered"))
                continue
            for n in range(1, self.config.max_attempts_per_provider + 1):
                remaining = deadline - time.time()
                if remaining <= 0:
                    last_error = GatewayError(ErrorCode.TIMEOUT_BUDGET_EXCEEDED,
                                              "total routing budget exceeded",
                                              provider=cand.provider, request_id=rid)
                    attempts.append(AttemptRecord(cand.model_id, cand.provider, n, False,
                                                  error_code=last_error.code.value,
                                                  error_message=last_error.message))
                    return self._escalation(request, rid, ranked, attempts, last_error)
                timeout_ms = self._timeout_for(request)
                timeout_s = min(timeout_ms / 1000.0, max(0.05, remaining))
                try:
                    fut = self._pool.submit(adapter.invoke, request, timeout_s)
                    try:
                        result = fut.result(timeout=timeout_s + 0.25)
                    except concurrent.futures.TimeoutError:
                        fut.cancel()
                        raise GatewayError(ErrorCode.PROVIDER_TIMEOUT,
                                           f"{cand.model_id} timed out after {timeout_ms}ms",
                                           provider=cand.provider,
                                           request_id=rid) from None
                    self.health.mark_success(cand.model_id)
                    self.history.record(cand.model_id, request.task_type, True)
                    attempts.append(AttemptRecord(
                        cand.model_id, cand.provider, n, True,
                        latency_ms=result.latency_ms, timeout_ms=timeout_ms))
                    self.telemetry.record_request(
                        ok=True, escalated=False, model_id=cand.model_id,
                        latency_ms=result.latency_ms, cost_usd=result.cost_usd,
                        reason_codes=cand.reason_codes, error_code=None, success=True)
                    return RouteResult(rid, True, False, result.model_id, result.provider,
                                       result.text, result.latency_ms, result.cost_usd,
                                       attempts, ranked, dict(self.config.weights), None)
                except GatewayError as exc:
                    exc.request_id = exc.request_id or rid
                    last_error = exc
                    self.health.mark_failure(cand.model_id)
                    self.history.record(cand.model_id, request.task_type, False)
                    attempts.append(AttemptRecord(
                        cand.model_id, cand.provider, n, False, timeout_ms=timeout_ms,
                        error_code=exc.code.value, error_message=exc.message))
                    if not exc.retryable and exc.code != ErrorCode.PROVIDER_ERROR:
                        break  # non-retryable for this provider -> next candidate
                    # else retry same provider until attempts exhausted, then fall through
                except Exception as exc:  # defensive: never leak raw exceptions
                    last_error = GatewayError(ErrorCode.INTERNAL_ERROR, f"internal: {exc}",
                                              provider=cand.provider, request_id=rid)
                    self.health.mark_failure(cand.model_id)
                    attempts.append(AttemptRecord(
                        cand.model_id, cand.provider, n, False, timeout_ms=timeout_ms,
                        error_code=last_error.code.value, error_message=last_error.message))
                    break

        err = GatewayError(
            ErrorCode.ALL_PROVIDERS_FAILED,
            f"all {len(safe)} safe candidates failed; "
            f"last: {last_error.message if last_error else 'n/a'}",
            request_id=rid,
            details={"attempts": [a.to_dict() for a in attempts]},
        )
        return self._escalation(request, rid, ranked, attempts, err)

    def _timeout_for(self, request: TaskRequest) -> int:
        if request.max_latency_ms:
            return max(100, min(self.config.default_timeout_ms, request.max_latency_ms))
        return self.config.default_timeout_ms

    def _escalation(self, request: TaskRequest, rid: str, ranked: list[RankedCandidate],
                    attempts: list[AttemptRecord], err: GatewayError) -> RouteResult:
        err.request_id = err.request_id or rid
        reasons = ["ESCALATION_REQUIRED"]
        for c in ranked:
            reasons.extend(c.reason_codes)
        self.telemetry.record_request(
            ok=False, escalated=True, model_id=None, latency_ms=None, cost_usd=None,
            reason_codes=sorted(set(reasons)), error_code=err.code.value, success=False)
        payload = err.to_dict()
        payload["hint"] = ("escalate to human review / queue for later; "
                           "no safe or successful model for this request")
        return RouteResult(rid, False, True, None, None, None, None, None,
                           attempts, ranked, dict(self.config.weights), payload)
