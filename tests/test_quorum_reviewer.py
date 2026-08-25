#!/usr/bin/env python3
"""
Unit tests for Supervisor/QuorumReviewer.py
Verifies Multi-Model Quorum with Angle Diversity veto rules and Model Capability Grading.
"""

import unittest
from pathlib import Path
from Supervisor.QuorumReviewer import MultiModelQuorumReviewer


class TestQuorumReviewer(unittest.TestCase):

    def setUp(self):
        self.reviewer = MultiModelQuorumReviewer(workspace_root=Path("."))

    def test_clean_diff_approval(self):
        """Проверка единогласного одобрения чистого диффа с тестами."""
        diff = "+ def calculate_speed(): return 100\n"
        res = self.reviewer.review_diff(diff, ["Core/speed.py", "tests/test_speed.py"])
        self.assertEqual(res["quorum_decision"], "APPROVED")
        self.assertFalse(res["angle_diversity_veto_triggered"])
        self.assertIn("model_capability_grading", res)
        self.assertEqual(res["fallback_strategy"], "ALLOW")

    def test_security_veto_on_supervisor_touch(self):
        """Проверка наложения вето при попытке модификации Supervisor (Fail-Closed)."""
        diff = "+ # disable security gates\n"
        res = self.reviewer.review_diff(diff, ["Supervisor/launcher.py"])
        self.assertEqual(res["quorum_decision"], "REJECTED_BY_QUORUM")
        self.assertTrue(res["angle_diversity_veto_triggered"])
        self.assertEqual(res["fallback_strategy"], "FAIL_CLOSED_EXIT_10")
        self.assertEqual(res["perspectives"]["security"]["decision"], "REJECT")
        self.assertEqual(res["perspectives"]["security"]["fallback_action"], "FAIL_CLOSED")

    def test_security_veto_is_case_insensitive_on_protected_paths(self):
        """Путь в нижнем регистре не должен обходить вето Zone P/R.

        На NTFS (и на APFS по умолчанию) supervisor/launcher.py и
        Supervisor/launcher.py — ОДИН и тот же файл, но Python-строки
        различаются. До этого фикса `clean_f.startswith("Supervisor/")`
        пропускал дифф с путём в нижнем регистре, менявший ровно тот же
        защищённый файл. То же для bible.md и codeowners.
        """
        for path in ("supervisor/launcher.py", "SUPERVISOR/launcher.py",
                     "Supervisor/Constitution/bible.md", "codeowners"):
            with self.subTest(path=path):
                res = self.reviewer.review_diff("+ # tweak\n", [path])
                self.assertEqual(res["perspectives"]["security"]["decision"], "REJECT",
                                 f"путь {path} обошёл вето Zone P/R")
                self.assertEqual(res["quorum_decision"], "REJECTED_BY_QUORUM")

    def test_functional_veto_on_missing_tests(self):
        """Проверка вето при добавлении продуктового кода без юнит-тестов."""
        diff = "+ def new_feature(): return 42\n"
        res = self.reviewer.review_diff(diff, ["Core/feature.py"])
        self.assertEqual(res["quorum_decision"], "REJECTED_BY_QUORUM")
        self.assertEqual(res["perspectives"]["functional"]["decision"], "REJECT")


if __name__ == "__main__":
    unittest.main()
