#!/usr/bin/env python3
"""
Unit tests for Supervisor/WorktreeSandbox.py
Verifies sandbox lifecycle, naming sanitization, and git invariants.
"""

import unittest
from pathlib import Path
from Supervisor.WorktreeSandbox import WorktreeSandboxManager


class TestWorktreeSandbox(unittest.TestCase):

    def setUp(self):
        self.manager = WorktreeSandboxManager(workspace_root=Path("."))

    def test_list_sandboxes(self):
        """Проверка получения списка рабочих деревьев."""
        sandboxes = self.manager.list_sandboxes()
        self.assertIsInstance(sandboxes, list)
        self.assertGreaterEqual(len(sandboxes), 1)

    def test_invalid_task_id(self):
        """Проверка обработки некорректного task_id."""
        with self.assertRaises(ValueError):
            self.manager.create_sandbox(task_id="   ")


if __name__ == "__main__":
    unittest.main()
