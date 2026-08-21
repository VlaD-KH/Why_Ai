#!/usr/bin/env python3
"""
Unit tests for Core/ContextFit.py
Verifies import graph generation and centrality calculations.
"""

import unittest
from pathlib import Path
from Core.ContextFit import ContextFitManager


class TestContextFit(unittest.TestCase):

    def setUp(self):
        self.manager = ContextFitManager(repo_path=".")

    def test_compute_centrality(self):
        """Проверка расчета центральности кодовой базы."""
        centrality = self.manager.compute_centrality()
        self.assertIsInstance(centrality, dict)
        self.assertGreater(len(centrality), 0)
        # Все оценки должны быть в диапазоне [0.0, 1.0]
        for file, score in centrality.items():
            self.assertTrue(0.0 <= score <= 1.0, f"Неверный score {score} для {file}")

    def test_compact_context(self):
        """Проверка алгоритма сжатия контекста."""
        result = self.manager.compact_context(token_deficit=1000)
        self.assertIn("approx_tokens_freed", result)
        self.assertIn("retained_files", result)
        self.assertIn("evicted_files", result)


if __name__ == "__main__":
    unittest.main()
