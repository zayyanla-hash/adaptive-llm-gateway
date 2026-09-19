"""In-memory telemetry: latency / cost / outcome / reason-code tracking."""
from __future__ import annotations

import threading
import time
from collections import Counter


class TelemetryStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.started_at = time.time()
        self.total_requests = 0
        self.total_ok = 0
        self.total_escalated = 0
        self.by_model_ok: Counter = Counter()
        self.by_model_fail: Counter = Counter()
        self.by_reason: Counter = Counter()
        self.by_error: Counter = Counter()
        self.latencies_ms: list[int] = []
        self.total_cost_usd = 0.0

    def record_request(
        self,
        *,
        ok: bool,
        escalated: bool,
        model_id: str | None,
        latency_ms: int | None,
        cost_usd: float | None,
        reason_codes: list[str],
        error_code: str | None,
        success: bool,
    ) -> None:
        with self._lock:
            self.total_requests += 1
            if ok:
                self.total_ok += 1
            if escalated:
                self.total_escalated += 1
            if model_id and success:
                self.by_model_ok[model_id] += 1
            elif model_id:
                self.by_model_fail[model_id] += 1
            for rc in reason_codes:
                self.by_reason[rc] += 1
            if error_code:
                self.by_error[error_code] += 1
            if latency_ms is not None:
                self.latencies_ms.append(latency_ms)
                if len(self.latencies_ms) > 5000:
                    del self.latencies_ms[:1000]
            if cost_usd:
                self.total_cost_usd += cost_usd

    @staticmethod
    def _rate(ok: int, total: int) -> float:
        return round(ok / total, 4) if total else 0.0

    def snapshot(self) -> dict:
        with self._lock:
            lat = sorted(self.latencies_ms)

            def pct(p: float) -> float | None:
                if not lat:
                    return None
                idx = min(len(lat) - 1, int(p * len(lat)))
                return float(lat[idx])
            return {
                "uptime_s": round(time.time() - self.started_at, 1),
                "total_requests": self.total_requests,
                "total_ok": self.total_ok,
                "success_rate": self._rate(self.total_ok, self.total_requests),
                "total_escalated": self.total_escalated,
                "by_model_ok": dict(self.by_model_ok),
                "by_model_fail": dict(self.by_model_fail),
                "by_reason_code": dict(self.by_reason),
                "by_error_code": dict(self.by_error),
                "latency_ms": {
                    "count": len(lat),
                    "p50": pct(0.5),
                    "p95": pct(0.95),
                    "max": float(lat[-1]) if lat else None,
                },
                "total_cost_usd": round(self.total_cost_usd, 6),
            }
