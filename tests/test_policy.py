"""Policy engine unit tests: multi-signal scoring, gates, determinism."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from adaptive_gateway.config import GatewayConfig
from adaptive_gateway.policy import score_candidates
from adaptive_gateway.registry import ModelRegistry
from adaptive_gateway.types import TaskRequest


class TestPolicy(unittest.TestCase):
    def setUp(self):
        self.registry = ModelRegistry()
        self.config = GatewayConfig.from_dict({})

    def test_private_local_only_excludes_cloud(self):
        req = TaskRequest(prompt="summarize notes", task_type="private_data",
                          privacy_local_only=True)
        ranked = score_candidates(req, self.registry.all(), {}, {}, self.config)
        safe = [c for c in ranked if not c.excluded]
        self.assertTrue(safe, "expected some safe local candidates")
        for c in safe:
            spec = self.registry.get(c.model_id)
            self.assertEqual(spec.hosted, "local")
        cloud = [c for c in ranked if c.model_id == "gemini-2.5-flash"]
        self.assertTrue(cloud[0].excluded)
        self.assertIn("PRIVACY_VIOLATION", cloud[0].reason_codes)

    def test_vision_gate(self):
        req = TaskRequest(prompt="describe image", task_type="vision", needs_vision=True)
        ranked = score_candidates(req, self.registry.all(), {}, {}, self.config)
        safe_ids = {c.model_id for c in ranked if not c.excluded}
        self.assertIn("glimmer-vl-local", safe_ids)
        self.assertIn("gemini-2.5-flash", safe_ids)
        self.assertNotIn("qwen3-8b-local", safe_ids)

    def test_context_overflow_excluded(self):
        req = TaskRequest(prompt="x", context_tokens=2_000_000)
        ranked = score_candidates(req, self.registry.all(), {}, {}, self.config)
        bonsai = next(c for c in ranked if c.model_id == "bonsai-7b-local")
        self.assertTrue(bonsai.excluded)
        self.assertIn("CONTEXT_OVERFLOW", bonsai.reason_codes)

    def test_deterministic_tiebreak(self):
        req = TaskRequest(prompt="hello", task_type="chat")
        r1 = score_candidates(req, self.registry.all(), {}, {}, self.config)
        r2 = score_candidates(req, self.registry.all(), {}, {}, self.config)
        self.assertEqual([c.model_id for c in r1], [c.model_id for c in r2])
        self.assertEqual([c.score for c in r1], [c.score for c in r2])

    def test_reason_codes_and_trace_present(self):
        req = TaskRequest(prompt="fib in python", task_type="code", difficulty="hard")
        ranked = score_candidates(req, self.registry.all(), {}, {}, self.config)
        for c in ranked:
            if not c.excluded:
                self.assertTrue(c.reason_codes, "safe candidates need reason codes")
                self.assertEqual(set(c.subscores),
                                 {"task_affinity", "quality", "latency", "cost",
                                  "privacy", "context", "tools", "health", "history"})

    def test_circuit_open_excludes(self):
        req = TaskRequest(prompt="hello", task_type="chat")
        ranked = score_candidates(req, self.registry.all(),
                                  {"bonsai-7b-local": False}, {}, self.config)
        b = next(c for c in ranked if c.model_id == "bonsai-7b-local")
        self.assertTrue(b.excluded)
        self.assertIn("HEALTH_CIRCUIT_OPEN", b.reason_codes)


if __name__ == "__main__":
    unittest.main()
