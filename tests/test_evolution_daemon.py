#!/usr/bin/env python3
"""
Unit tests for Supervisor/EvolutionDaemon.py

Гейты проверяются на том словаре, который реально производит
Core/MetaOverPatch.generate_refactor_plan(), а не на выдуманной форме.
Полный цикл гоняется в одноразовом git-репозитории, чтобы не оставлять
песочниц и веток в рабочем дереве.
"""

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from Core.MetaOverPatch import MetaOverPatchEngine
from Supervisor.EvolutionDaemon import AutonomousEvolutionDaemon, IdempotencyGate

CONFIG = """system:
  project_name: "EvoFixture"
  active_mode: "self_evo"  # без этого фикстура попадает в fail-closed default (prod_evo)
                            # и цикл блокируется гейтом режима раньше, чем эти тесты
                            # успевают дойти до idempotency/ratchet — см. test_prod_evo_sigterm.py

modules:
  background_consciousness:
    enabled: true
    idempotency_gate:
      enabled: true
      require_failure_binding: true
      shrink_only_ratchet: true
"""


def _make_workspace(with_failures: int = 0) -> Path:
    root = Path(tempfile.mkdtemp(prefix="evo-")).resolve()
    (root / "Core").mkdir(parents=True, exist_ok=True)
    (root / "tests").mkdir(parents=True, exist_ok=True)
    (root / "why_ai_config.yaml").write_text(CONFIG, encoding="utf-8")
    (root / ".size_ratchets.json").write_text(
        json.dumps({"schema": "ai-loop/size-ratchets/v1", "principle": "shrink-only", "limits": {}}),
        encoding="utf-8",
    )
    engine = MetaOverPatchEngine(workspace_root=root)
    for i in range(with_failures):
        engine.record_failure(
            failure_type=f"FIXTURE_FAILURE_{i}",
            root_cause="deliberately recorded by the test fixture",
            principle_violated=12,
            resolution="covered by this test",
        )
    return root


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True,
                   capture_output=True, text=True, encoding="utf-8", errors="replace")


def _make_git_workspace(with_failures: int = 0) -> Path:
    root = _make_workspace(with_failures=with_failures)
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "fixture@why-ai.test")
    _git(root, "config", "user.name", "Evo Fixture")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "fixture baseline")
    return root


class TestIdempotencyGateContract(unittest.TestCase):
    """Гейт и план обязаны говорить на одном языке (Принцип 12)."""

    def test_real_plan_without_failures_is_rejected(self):
        root = _make_workspace(with_failures=0)
        try:
            plan = MetaOverPatchEngine(workspace_root=root).generate_refactor_plan()
            gate = IdempotencyGate(workspace_root=root, require_failure_binding=True)
            valid, reason = gate.validate_proposal(plan, ["Core/sample.py"])
            self.assertFalse(valid)
            self.assertIn("IDEMPOTENCY_REJECTED", reason)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_real_plan_bound_to_recorded_failures_is_accepted(self):
        """Сигнал Meta-over-Patch вычисляется — гейт обязан его увидеть, а не ноль."""
        root = _make_workspace(with_failures=3)
        try:
            plan = MetaOverPatchEngine(workspace_root=root).generate_refactor_plan()
            gate = IdempotencyGate(workspace_root=root, require_failure_binding=True)
            valid, reason = gate.validate_proposal(plan, ["Core/sample.py"])
            self.assertTrue(valid, f"план {sorted(plan)} отклонён: {reason}")
            self.assertEqual(reason, "IDEMPOTENCY_PASSED")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_zone_pr_paths_are_rejected_even_with_a_valid_plan(self):
        root = _make_workspace(with_failures=2)
        try:
            plan = MetaOverPatchEngine(workspace_root=root).generate_refactor_plan()
            gate = IdempotencyGate(workspace_root=root, require_failure_binding=True)
            valid, reason = gate.validate_proposal(plan, ["Supervisor/launcher.py"])
            self.assertFalse(valid)
            self.assertIn("POLICY_REJECTED", reason)
        finally:
            shutil.rmtree(root, ignore_errors=True)


class TestEvolutionCycle(unittest.TestCase):

    def setUp(self):
        self.root = _make_git_workspace(with_failures=3)
        self.daemon = AutonomousEvolutionDaemon(workspace_root=self.root)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_evolve_without_force_is_not_a_noop(self):
        """Кнопка «Evolve» зовёт цикл без force — он обязан дойти до конца."""
        res = self.daemon.run_evolution_cycle(task_name="no-force", force=False)
        self.assertEqual(res["status"], "EVOLUTION_CYCLE_SUCCESS", res)

    def test_cycle_audits_the_files_named_by_its_own_diff(self):
        """changed_files выводится из кандидатного диффа, а не из литерала."""
        res = self.daemon.run_evolution_cycle(task_name="diff-derived", force=False)
        self.assertEqual(res["changed_files"], ["Core/evolution_log.txt"])
        self.assertNotIn("tests/test_meta_over_patch.py", res["changed_files"])

    def test_cycle_reports_a_verified_ratchet_result_not_a_bare_call(self):
        """Принцип 15: успех — только по проверенному результату храповиков."""
        res = self.daemon.run_evolution_cycle(task_name="ratchet-verified", force=False)
        self.assertTrue(res["ratchet_verification"]["ok"], res)
        self.assertEqual(res["ratchet_verification"]["checked"], ["Core/evolution_log.txt"])

    def test_cycle_leaves_no_sandbox_behind(self):
        self.daemon.run_evolution_cycle(task_name="cleanup", force=False)
        leftovers = [p.name for p in (self.root / "worktrees").iterdir()] if (self.root / "worktrees").exists() else []
        self.assertEqual(leftovers, [])

    def test_disabled_module_short_circuits(self):
        self.daemon.enabled = False
        res = self.daemon.run_evolution_cycle(task_name="disabled", force=False)
        self.assertEqual(res["status"], "MODULE_DISABLED")


if __name__ == "__main__":
    unittest.main()
