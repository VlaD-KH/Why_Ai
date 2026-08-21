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

    def test_functional_veto_on_missing_tests(self):
        """Проверка вето при добавлении продуктового кода без юнит-тестов."""
        diff = "+ def new_feature(): return 42\n"
        res = self.reviewer.review_diff(diff, ["Core/feature.py"])
        self.assertEqual(res["quorum_decision"], "REJECTED_BY_QUORUM")
        self.assertEqual(res["perspectives"]["functional"]["decision"], "REJECT")


if __name__ == "__main__":
    unittest.main()
