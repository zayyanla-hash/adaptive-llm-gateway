"""Provider adapter interface."""
from __future__ import annotations

import abc

from adaptive_gateway.types import ProviderResult, TaskRequest


class ProviderAdapter(abc.ABC):
    """A provider knows how to serve one model_id with a bounded call."""

    model_id: str
    provider: str

    @abc.abstractmethod
    def invoke(self, request: TaskRequest, timeout_s: float) -> ProviderResult:
        """Invoke the model. Must respect timeout_s (raise on expiry)."""

    @abc.abstractmethod
    def health_check(self) -> bool:
        """Lightweight availability probe. Never raises."""

    def describe(self) -> dict:
        return {"model_id": self.model_id, "provider": self.provider}
