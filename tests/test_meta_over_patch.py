#!/usr/bin/env python3
"""
Unit tests for Core/MetaOverPatch.py
Verifies failure pattern analysis and refactor plan generation.
"""

import unittest
from pathlib import Path
from Core.MetaOverPatch import MetaOverPatchEngine


class TestMetaOverPatch(unittest.TestCase):

    def setUp(self):
        self.engine = MetaOverPatchEngine(workspace_root=Path("."))

    def test_load_and_analyze(self):
        """Проверка загрузки сбоев и анализа паттернов."""
        analysis = self.engine.analyze_patterns()
        self.assertIn("total_failures_recorded", analysis)
        self.assertIn("distribution_by_type", analysis)
        self.assertGreaterEqual(analysis["total_failures_recorded"], 1)

    def test_generate_refactor_plan(self):
        """Проверка генерации плана рефакторинга Meta-over-Patch."""
        plan = self.engine.generate_refactor_plan()
        self.assertIn("title", plan)
        self.assertIn("steps", plan)


if __name__ == "__main__":
    unittest.main()
