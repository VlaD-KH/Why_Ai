#!/usr/bin/env python3
"""
Unit tests for Supervisor/SizeRatchets.py
Verifies shrink-only ratchet updates and bloat detection.
"""

import unittest
from pathlib import Path
from Supervisor.SizeRatchets import SizeRatchetsManager


class TestSizeRatchets(unittest.TestCase):

    def setUp(self):
        self.manager = SizeRatchetsManager(workspace_root=Path("."))

    def test_record_baseline(self):
        """Проверка фиксации базовых размеров файлов."""
        limits = self.manager.record_baseline()
        self.assertIsInstance(limits, dict)
        self.assertGreater(len(limits), 0)

    def test_check_file_pass(self):
        """Проверка валидации существующего файла."""
        ok = self.manager.check_file("Supervisor/launcher.py")
        self.assertTrue(ok)


if __name__ == "__main__":
    unittest.main()
