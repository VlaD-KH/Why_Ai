#!/usr/bin/env python3
"""
Unit tests for Supervisor/WorkspaceOrchestrator.py
Verifies Hierarchy v3 mode switching and Git invariant hardening.
"""

import unittest
from pathlib import Path
from Supervisor.WorkspaceOrchestrator import WorkspaceOrchestrator


class TestWorkspaceOrchestrator(unittest.TestCase):

    def setUp(self):
        self.orchestrator = WorkspaceOrchestrator(workspace_root=Path("."))

    def test_switch_project_mode(self):
        """Проверка переключения в Project-режим (Project ⊃ agent)."""
        state = self.orchestrator.switch_mode("project", project_name="vanguard")
        self.assertEqual(state["current_mode"], "project")
        self.assertEqual(state["topology"]["hierarchy"], "Project ⊃ agent")
        self.assertEqual(state["topology"]["rank_map"]["Project_vanguard"], 1)

    def test_switch_agent_mode(self):
        """Проверка переключения в Agent-режим (Agent ⊃ Project)."""
        state = self.orchestrator.switch_mode("agent")
        self.assertEqual(state["current_mode"], "agent")
        self.assertEqual(state["topology"]["hierarchy"], "Agent ⊃ Project")
        self.assertEqual(state["topology"]["rank_map"]["Project"], 3)

    def test_harden_git_invariants(self):
        """Проверка фиксации Git параметров (autocrlf=false, quotepath=false)."""
        results = self.orchestrator.harden_git_invariants()
        self.assertIn("core.autocrlf", results)
        self.assertIn("core.quotepath", results)


if __name__ == "__main__":
    unittest.main()
