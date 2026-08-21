#!/usr/bin/env python3
"""
Unit tests for Supervisor/launcher.py
Verifies lifecycle status, panic handling, and safety guards.
"""

import unittest
from pathlib import Path
from Supervisor.launcher import SupervisorLauncher


class TestSupervisorLauncher(unittest.TestCase):

    def setUp(self):
        self.launcher = SupervisorLauncher(workspace_root=Path("."))

    def test_status_output(self):
        """Проверка получения статуса супервизора."""
        status = self.launcher.get_status()
        self.assertEqual(status["status"], "RUNNING")
        self.assertTrue(status["constitution_present"])

    def test_panic_stop(self):
        """Проверка выполнения аварийной остановки с кодом 10."""
        exit_code = self.launcher.panic_stop(reason="Unit test emergency trigger")
        self.assertEqual(exit_code, 10)


if __name__ == "__main__":
    unittest.main()
