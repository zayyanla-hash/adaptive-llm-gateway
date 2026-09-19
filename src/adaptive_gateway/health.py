"""Health monitor with circuit-breaker semantics (per model)."""
from __future__ import annotations

import time


class HealthMonitor:
    def __init__(self, fail_threshold: int = 3, cooldown_s: float = 30.0) -> None:
        self.fail_threshold = fail_threshold
        self.cooldown_s = cooldown_s
        self._fails: dict[str, int] = {}
        self._opened_at: dict[str, float] = {}

    def mark_success(self, model_id: str) -> None:
        self._fails[model_id] = 0
        self._opened_at.pop(model_id, None)

    def mark_failure(self, model_id: str) -> None:
        n = self._fails.get(model_id, 0) + 1
        self._fails[model_id] = n
        if n >= self.fail_threshold:
            self._opened_at.setdefault(model_id, time.time())

    def is_available(self, model_id: str) -> bool:
        opened = self._opened_at.get(model_id)
        if opened is None:
            return True
        if time.time() - opened >= self.cooldown_s:
            self._opened_at.pop(model_id, None)
            self._fails[model_id] = 0
            return True
        return False

    def snapshot(self) -> dict[str, bool]:
        # NOTE: snapshot must not mutate cooldown state implicitly for all keys
        # without ids; callers pass explicit model lists. Kept side-effect free.
        return {}

    def availability_map(self, model_ids: list[str]) -> dict[str, bool]:
        return {m: self.is_available(m) for m in model_ids}
