"""Router tests: fallback, retry, timeout, escalation, validation."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from adaptive_gateway.config import GatewayConfig
from adaptive_gateway.providers.adapters import build_default_adapters
from adaptive_gateway.registry import ModelRegistry
from adaptive_gateway.router import AdaptiveRouter
from adaptive_gateway.types import TaskRequest


def make_router(overrides=None, **cfg_kw):
    registry = ModelRegistry()
    config = GatewayConfig.from_dict(cfg_kw or {})
    adapters = build_default_adapters(registry.all(), mode="mock", overrides=overrides)
    return registry, AdaptiveRouter(registry, adapters, config)


class TestRouter(unittest.TestCase):
    def test_success_carries_trace(self):
        _, router = make_router()
        try:
            res = router.route(TaskRequest(prompt="hello", task_type="chat"))
            self.assertTrue(res.ok)
            self.assertFalse(res.escalated)
            self.assertIsNotNone(res.model_id)
            self.assertTrue(res.ranked)
            self.assertTrue(res.attempts and res.attempts[0].ok)
            self.assertTrue(res.weights)
        finally:
            router.close()

    def test_fallback_on_error(self):
        # Force the top code pick to fail; router must still succeed via fallback.
        _, router = make_router({"deepseek-chat-v3": {"fail_mode": "error"}})
        try:
            res = router.route(TaskRequest(prompt="quicksort", task_type="code",
                                           difficulty="hard"), request_id="t-fallback")
            self.assertTrue(res.ok, f"expected fallback success, got {res.error}")
            self.assertGreaterEqual(len(res.attempts), 2)
            self.assertEqual(res.attempts[0].model_id, "deepseek-chat-v3")
            self.assertFalse(res.attempts[0].ok)
        finally:
            router.close()

    def test_timeout_fallback(self):
        _, router = make_router({"bonsai-7b-local": {"fail_mode": "timeout"}},
                                default_timeout_ms=400)
        try:
            res = router.route(TaskRequest(prompt="hi", task_type="fast",
                                           max_latency_ms=300))
            codes = [a.error_code for a in res.attempts]
            self.assertIn("PROVIDER_TIMEOUT", codes)
        finally:
            router.close()

    def test_escalation_all_fail(self):
        registry = ModelRegistry()
        overrides = {s.model_id: {"fail_mode": "error"} for s in registry.all()}
        _, router = make_router(overrides)
        try:
            res = router.route(TaskRequest(prompt="hi", task_type="chat"),
                               request_id="t-escalate")
            self.assertFalse(res.ok)
            self.assertTrue(res.escalated)
            self.assertIsNone(res.text)
            self.assertEqual(res.error["code"], "ALL_PROVIDERS_FAILED")
        finally:
            router.close()

    def test_escalation_no_safe_candidate(self):
        _, router = make_router()
        try:
            res = router.route(TaskRequest(
                prompt="x", task_type="vision", privacy_local_only=True,
                needs_vision=True, context_tokens=99_999_999))
            self.assertFalse(res.ok)
            self.assertTrue(res.escalated)
            self.assertEqual(res.error["code"], "NO_SAFE_CANDIDATE")
        finally:
            router.close()

    def test_validation_error(self):
        _, router = make_router()
        try:
            res = router.route(TaskRequest(prompt="   ", task_type="nope"))
            self.assertFalse(res.ok)
            self.assertTrue(res.escalated)
            self.assertEqual(res.error["code"], "VALIDATION_ERROR")
        finally:
            router.close()

    def test_retry_same_provider_before_fallback(self):
        # Flaky bonsai fails on odd global calls; isolate it as the only healthy
        # provider so the router must retry it.
        registry = ModelRegistry()
        overrides = {s.model_id: {"fail_mode": "error"} for s in registry.all()}
        overrides["bonsai-7b-local"] = {"fail_mode": "flaky", "latency_ms": 10}
        config = GatewayConfig.from_dict({})
        adapters = build_default_adapters(registry.all(), mode="mock", overrides=overrides)
        router = AdaptiveRouter(registry, adapters, config)
        try:
            # First call primes the flaky counter; second exercises retry-then-success
            # deterministically regardless of counter parity.
            seen_retry = False
            for i in range(4):
                res = router.route(TaskRequest(prompt=f"hi {i}", task_type="chat"))
                if res.ok and len(res.attempts) >= 2:
                    seen_retry = True
                    break
            self.assertTrue(seen_retry, "expected a retry-then-success within 4 calls")
        finally:
            router.close()


if __name__ == "__main__":
    unittest.main()
