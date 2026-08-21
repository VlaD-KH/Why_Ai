#!/usr/bin/env python3
"""
Unit tests for Supervisor/CommitGate.py
Verifies two-stage SHA-256 fingerprint verification and merge gating.
"""

import unittest
from pathlib import Path
from Supervisor.CommitGate import ReviewedCommitGate


class TestCommitGate(unittest.TestCase):

    def setUp(self):
        self.gate = ReviewedCommitGate(workspace_root=Path("."))

    def test_fingerprint_deterministic(self):
        """Проверка детерминированности и устойчивости хэша к CRLF/LF."""
        diff_lf = "diff --git a/test.py b/test.py\n+def hello(): pass\n"
        diff_crlf = "diff --git a/test.py b/test.py\r\n+def hello(): pass\r\n"
        hash_lf = self.gate.calculate_fingerprint(diff_lf)
        hash_crlf = self.gate.calculate_fingerprint(diff_crlf)
        self.assertEqual(hash_lf, hash_crlf)

    def test_re_fingerprint_mismatch_blocks_merge(self):
        """Проверка блокировки слияния при изменении диффа после кворума."""
        original_diff = "+ def original(): return 1\n"
        mutated_diff = "+ def mutated_malicious(): return 2\n"
        
        preflight_hash = self.gate.calculate_fingerprint(original_diff)
        res = self.gate.verify_and_merge(mutated_diff, preflight_hash, "Attempted merge with mutated diff")
        
        self.assertEqual(res["status"], "FINGERPRINT_MISMATCH")
        self.assertFalse(res["merged"])

    def test_valid_merge_flow(self):
        """Проверка успешного слияния при совпадении отпечатков."""
        diff = "+ def valid(): return 1\n"
        preflight_hash = self.gate.calculate_fingerprint(diff)
        res = self.gate.verify_and_merge(diff, preflight_hash, "Clean verified merge")
        self.assertEqual(res["status"], "MERGED_SUCCESSFULLY")


if __name__ == "__main__":
    unittest.main()
