"""Config + registry + SDK + eval-invariants tests."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from adaptive_gateway.config import GatewayConfig, load_config
from adaptive_gateway.registry import ModelRegistry
from adaptive_gateway.sdk import GatewaySDK
from adaptive_gateway.types import TaskRequest


class TestConfigRegistry(unittest.TestCase):
    def test_default_config_valid(self):
        cfg = GatewayConfig.from_dict({})
        self.assertEqual(cfg.validate(), [])

    def test_bad_weights_rejected(self):
        cfg = GatewayConfig.from_dict({"weights": {"a": 1.0}})
        self.assertTrue(cfg.validate())

    def test_load_config_file(self):
        cfg = GatewayConfig.from_dict({})
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            json.dump({"max_attempts_per_provider": 3,
                       "weights": dict(cfg.weights)}, fh)
            path = fh.name
        try:
            loaded = load_config(path)
            self.assertEqual(loaded.max_attempts_per_provider, 3)
        finally:
            os.unlink(path)

    def test_registry_covers_required_families(self):
        reg = ModelRegistry()
        ids = {s.model_id for s in reg.all()}
        for required in ("qwen3-8b-local", "bonsai-7b-local", "glimmer-vl-local",
                         "muse-7b-local", "gemini-2.5-flash", "deepseek-chat-v3",
                         "openai-compat-generic"):
            self.assertIn(required, ids)
        locals_ = [s for s in reg.all() if s.hosted == "local"]
        self.assertGreaterEqual(len(locals_), 4)


class TestSDK(unittest.TestCase):
    def test_sdk_route_dict_shape(self):
        sdk = GatewaySDK()
        try:
            out = sdk.route("hello", task_type="chat")
            self.assertTrue(out["ok"])
            self.assertIn("ranked", out)
            self.assertIn("attempts", out)
        finally:
            sdk.close()

    def test_request_validation(self):
        req = TaskRequest(prompt="", task_type="bogus")
        problems = req.validate()
        self.assertGreaterEqual(len(problems), 2)


class TestEvalHarness(unittest.TestCase):
    def test_eval_passes_offline(self):
        from eval.harness import run_eval
        payload = run_eval()
        self.assertEqual(payload["failed"], 0, json.dumps(payload, indent=2)[:3000])
        self.assertGreaterEqual(payload["total"], 8)


if __name__ == "__main__":
    unittest.main()
