#!/usr/bin/env python3
"""
Unit tests for Core/PolicyDriftVector.py
Verifies vector embeddings, cosine similarity, and semantic drift detection.
"""

import unittest
from pathlib import Path
from Core.PolicyDriftVector import PolicyDriftVectorAnalyzer


class TestPolicyDriftVector(unittest.TestCase):

    def setUp(self):
        self.analyzer = PolicyDriftVectorAnalyzer(workspace_root=Path("."))

    def test_identical_policy_similarity(self):
        """Проверка сходства идентичных текстов политик (Similarity = 1.0)."""
        policy_text = "enforcement:\n  diff_is_authoritative: true\n  mixed_diff_policy: MAX_RISK_WINS\n"
        res = self.analyzer.evaluate_drift(policy_text, policy_text)
        self.assertEqual(res["semantic_similarity"], 1.0)
        self.assertTrue(res["safe"])

    def test_semantic_drift_detection(self):
        """Проверка фиксации опасного семантического дрейфа."""
        base = "enforcement:\n  diff_is_authoritative: true\n  mixed_diff_policy: MAX_RISK_WINS\n"
        mutated = "enforcement:\n  diff_is_authoritative: false\n  mixed_diff_policy: MIN_RISK\n"
        res = self.analyzer.evaluate_drift(base, mutated)
        self.assertFalse(res["safe"])
        self.assertEqual(res["status"], "SEMANTIC_POLICY_DRIFT_DETECTED")


if __name__ == "__main__":
    unittest.main()
