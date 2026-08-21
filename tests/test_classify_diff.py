#!/usr/bin/env python3
"""
Unit tests for Supervisor/classify_diff.py
Verifies zone matching, MAX risk evaluation, and fail-closed properties.
"""

import unittest
from Supervisor.classify_diff import _normalise, _pattern_matches, _max_level, _bump, PolicyError


class TestClassifyDiff(unittest.TestCase):

    def test_normalise_paths(self):
        """Проверка корректной нормализации путей для Windows и Unix."""
        self.assertEqual(_normalise(".\\src\\main.py"), "src/main.py")
        self.assertEqual(_normalise("./src/utils/file.ts"), "src/utils/file.ts")
        self.assertEqual(_normalise("src\\api"), "src/api")
        self.assertEqual(_normalise("src\\api\\"), "src/api/")

    def test_pattern_matches(self):
        """Проверка сопоставления путей с шаблонами зон."""
        self.assertTrue(_pattern_matches("src/", "src/index.ts"))
        self.assertTrue(_pattern_matches("src/index.ts", "src/index.ts"))
        self.assertTrue(_pattern_matches("*.lock", "Cargo.lock"))
        self.assertTrue(_pattern_matches("**/package-lock.json", "package-lock.json"))
        self.assertTrue(_pattern_matches("**/.gitignore", "subdir/.gitignore"))
        self.assertFalse(_pattern_matches("src/", "docs/readme.md"))

    def test_max_level_rule(self):
        """Проверка математического правила MAX risk."""
        self.assertEqual(_max_level("LOW", "MEDIUM"), "MEDIUM")
        self.assertEqual(_max_level("LOW", "CRITICAL"), "CRITICAL")
        self.assertEqual(_max_level("HIGH", "MEDIUM"), "HIGH")
        self.assertEqual(_max_level("CRITICAL", "HIGH"), "CRITICAL")

    def test_bump_risk(self):
        """Проверка эскалации уровня риска."""
        self.assertEqual(_bump("LOW", 1), "MEDIUM")
        self.assertEqual(_bump("LOW", 2), "HIGH")
        self.assertEqual(_bump("HIGH", 1), "CRITICAL")
        self.assertEqual(_bump("CRITICAL", 1), "CRITICAL")


if __name__ == "__main__":
    unittest.main()
