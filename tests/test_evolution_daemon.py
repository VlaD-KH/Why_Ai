#!/usr/bin/env python3
"""
Unit tests for Supervisor/EvolutionDaemon.py
Verifies autonomous self-evo cycle execution, Idempotency Gate and state tracking.
"""

import unittest
from pathlib import Path
from Supervisor.EvolutionDaemon import AutonomousEvolutionDaemon, IdempotencyGate


class TestEvolutionDaemon(unittest.TestCase):

    def setUp(self):
        self.daemon = AutonomousEvolutionDaemon(workspace_root=Path("."))

    def test_idempotency_gate_prevents_unbound_changes(self):
        """Проверка защиты от бессмысленной активности (Action Bias)."""
        gate = IdempotencyGate(workspace_root=Path("."), require_failure_binding=True)
        empty_plan = {"patterns": [], "total_failures": 0}
        valid, reason = gate.validate_proposal(empty_plan, ["Core/sample.py"])
        self.assertFalse(valid)
        self.assertIn("IDEMPOTENCY_REJECTED", reason)

    def test_idempotency_gate_blocks_supervisor_tampering(self):
        """Проверка запрета на модификацию Zone P/R."""
        gate = IdempotencyGate(workspace_root=Path("."), require_failure_binding=False)
        plan = {"patterns": [{"cluster": "Test"}], "total_failures": 1}
        valid, reason = gate.validate_proposal(plan, ["Supervisor/launcher.py"])
        self.assertFalse(valid)
        self.assertIn("POLICY_REJECTED", reason)

    def test_run_evolution_cycle_forced_and_idempotent(self):
        """Проверка выполнения эволюционного цикла (с форсированием и с проверкой статуса)."""
        result_forced = self.daemon.run_evolution_cycle(task_name="test-forced-cycle", force=True)
        self.assertIn("cycle_id", result_forced)
        self.assertIn("status", result_forced)
        self.assertIn(result_forced["status"], ("EVOLUTION_CYCLE_SUCCESS", "REJECTED_BY_QUORUM", "MODULE_DISABLED"))

        result_auto = self.daemon.run_evolution_cycle(task_name="test-auto-cycle", force=False)
        self.assertIn(result_auto["status"], ("EVOLUTION_CYCLE_SUCCESS", "IDEMPOTENT_SKIPPED", "REJECTED_BY_QUORUM", "MODULE_DISABLED"))


if __name__ == "__main__":
    unittest.main()
