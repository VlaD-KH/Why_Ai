#!/usr/bin/env python3
"""
Тест: tests/test_why_ai_config.py
Назначение: Верификация загрузки why_ai_config.yaml, валидации Feature Flags и матрицы градаций моделей.
"""

import os
import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "Supervisor"))
sys.path.insert(0, str(ROOT_DIR / "Core"))

from miniyaml import parse_yaml


class TestWhyAiConfig(unittest.TestCase):
    def setUp(self):
        self.config_path = ROOT_DIR / "why_ai_config.yaml"

    def test_config_exists_and_parses(self):
        self.assertTrue(self.config_path.exists(), "why_ai_config.yaml должен существовать в корне Why_Ai")
        content = self.config_path.read_text(encoding="utf-8")
        data = parse_yaml(content)
        self.assertIsInstance(data, dict)
        self.assertEqual(data.get("system", {}).get("project_name"), "Why_Ai")
        self.assertEqual(data.get("system", {}).get("version"), "1.1.0-gold")

    def test_feature_flags_structure(self):
        content = self.config_path.read_text(encoding="utf-8")
        data = parse_yaml(content)
        modules = data.get("modules", {})

        # Living Identity
        self.assertIn("living_identity", modules)
        self.assertTrue(modules["living_identity"]["enabled"])
        self.assertEqual(modules["living_identity"]["identity_file"], "Core/identity.md")
        self.assertTrue(modules["living_identity"]["context_fit_pin"])

        # Background Consciousness & Idempotency Gate (отключено в prod_evo)
        self.assertIn("background_consciousness", modules)
        self.assertFalse(modules["background_consciousness"]["enabled"])
        self.assertEqual(modules["background_consciousness"]["tick_interval_seconds"], 300)
        self.assertTrue(modules["background_consciousness"]["idempotency_gate"]["require_failure_binding"])
        self.assertTrue(modules["background_consciousness"]["idempotency_gate"]["shrink_only_ratchet"])

        # Swarm Visualizer
        self.assertIn("swarm_visualizer", modules)
        self.assertTrue(modules["swarm_visualizer"]["enabled"])
        self.assertEqual(modules["swarm_visualizer"]["stream_protocol"], "SSE")

    def test_model_capability_classes(self):
        content = self.config_path.read_text(encoding="utf-8")
        data = parse_yaml(content)
        classes = data.get("llm_orchestration", {}).get("model_capability_classes", [])
        self.assertEqual(len(classes), 3)

        class_ids = [c["class_id"] for c in classes]
        self.assertIn("class_1_executor", class_ids)
        self.assertIn("class_2_architect", class_ids)
        self.assertIn("class_3_arbitrator", class_ids)


if __name__ == "__main__":
    unittest.main()
