"""Rolling historical success per (model, task_type) as EWMA in [0,1]."""
from __future__ import annotations


class SuccessHistory:
    def __init__(self, alpha: float = 0.3) -> None:
        self.alpha = alpha
        self._scores: dict[tuple[str, str], float] = {}

    def record(self, model_id: str, task_type: str, ok: bool) -> None:
        key = (model_id, task_type)
        prev = self._scores.get(key, 0.5)
        self._scores[key] = prev + self.alpha * ((1.0 if ok else 0.0) - prev)

    def scores_for(self, task_type: str) -> dict[str, float]:
        return {m: s for (m, t), s in self._scores.items() if t == task_type}

    def snapshot(self) -> dict[str, float]:
        return {f"{m}:{t}": round(s, 4) for (m, t), s in self._scores.items()}
