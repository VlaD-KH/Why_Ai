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
    # Живой проходящий тест обязателен, а не декоративный каталог: с R-4
    # verify_and_merge реально запускает `unittest discover` ВНУТРИ песочницы.
    # Пустой tests/ не попал бы в worktree вообще (git не хранит пустые
    # каталоги), и цикл честно отказал бы с TESTS_DIR_MISSING.
    # __init__.py обязателен: реальный tests/ этого репозитория — пакет, и
    # прогон идёт с -t <корень>, чтобы тесты могли импортировать Core/… .
    # Без него unittest отвечает "Start directory is not importable".
    (root / "tests" / "__init__.py").write_text("", encoding="utf-8")
    (root / "tests" / "test_fixture_smoke.py").write_text(
        "import unittest\n"
        "class FixtureSmoke(unittest.TestCase):\n"
        "    def test_ok(self):\n"
        "        self.assertTrue(True)\n",
        encoding="utf-8",
    )
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

    def _rev_parse(self, ref: str) -> str:
        res = subprocess.run(["git", "-C", str(self.root), "rev-parse", ref],
                             capture_output=True, text=True, encoding="utf-8", errors="replace")
        return res.stdout.strip()

    def test_cycle_publishes_a_real_commit_and_never_moves_main(self):
        """Сквозной тест: цикл обязан произвести НАСТОЯЩИЙ коммит, не словарь.

        Проверяется git, а не форма ответа: возвращённый SHA обязан
        разрешаться `cat-file -e` ПОСЛЕ удаления песочницы (ветка публикации
        держит объект достижимым) и содержать ожидаемое содержимое.

        И главный инвариант: HEAD рабочей области не двигается. Слияние в
        main — исключительное право человека (BIBLE Принцип 13,
        risk_classification.yaml: merge_authority: human), конвейер доводит
        кандидата только до ветки self-evo/<cycle_id>.
        """
        head_before = self._rev_parse("HEAD")
        res = self.daemon.run_evolution_cycle(task_name="real-commit", force=False)

        self.assertEqual(res["status"], "EVOLUTION_CYCLE_SUCCESS", res)
        merge = res["merge_result"]
        self.assertTrue(merge["merged"])
        sha = merge["commit_sha"]

        # Песочница уже удалена (шаг 7) — объект жив только благодаря ветке.
        self.assertFalse((self.root / "worktrees" / res["cycle_id"]).exists())
        self.assertEqual(
            subprocess.run(["git", "-C", str(self.root), "cat-file", "-e", sha],
                           capture_output=True).returncode, 0,
            "возвращённый SHA не разрешается git — коммита нет")
        shown = subprocess.run(["git", "-C", str(self.root), "show", sha],
                               capture_output=True, text=True, encoding="utf-8",
                               errors="replace").stdout
        self.assertIn("Evolution Cycle", shown)
        self.assertEqual(self._rev_parse(merge["publish_branch"]), sha)

        # main не сдвинут ни на коммит.
        self.assertEqual(self._rev_parse("HEAD"), head_before)
        self.assertIn("push", merge["human_action_required"])

    def test_cycle_records_its_trail_in_the_ledger(self):
        """Автономный цикл обязан оставлять аудиторский след.

        До R-4 демон не обращался к ledger вообще, и единственным
        свидетельством прогона был stdout, который никто не хранит.
        """
        res = self.daemon.run_evolution_cycle(task_name="ledger-trail", force=False)
        ledger_file = self.root / ".ai-loop" / "ledger.jsonl"
        self.assertTrue(ledger_file.exists(), "ledger.jsonl не создан циклом")

        records = [json.loads(line) for line in
                   ledger_file.read_text(encoding="utf-8").splitlines() if line.strip()]
        mine = [r for r in records if r.get("run_id") == res["cycle_id"]]
        events = [r["event"] for r in mine]
        self.assertIn("run_start", events)
        self.assertIn("artifact", events)

        published = [r for r in mine if r["event"] == "artifact"][0]
        # В журнале лежит тот же реальный SHA, что вернул конвейер.
        self.assertEqual(published["commit"], res["merge_result"]["commit_sha"])

    def test_disabled_module_short_circuits(self):
        self.daemon.enabled = False
        res = self.daemon.run_evolution_cycle(task_name="disabled", force=False)
        self.assertEqual(res["status"], "MODULE_DISABLED")


if __name__ == "__main__":
    unittest.main()
