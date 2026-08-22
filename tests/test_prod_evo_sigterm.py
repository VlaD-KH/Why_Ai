#!/usr/bin/env python3
"""
Тест: tests/test_prod_evo_sigterm.py
Назначение: верификация требования оператора 5.1.1 — в режиме [prod_evo] фоновый
демон обязан отправляться в SIGTERM (отключаться), высвобождая вычислительные
ресурсы и исключая неконтролируемую фоновую генерацию.

Три независимых утверждения проверяются раздельно, потому что «зелёный» ответ
одного из них ничего не говорит о двух других:
  1. Режим читается из ЖИВОГО источника и разрешается fail-closed.
  2. Останов — настоящий: подопытный процесс действительно умирает.
  3. Гейт стоит перед созданием песочницы, а не после.
"""

import json
import os
import signal
import subprocess
import sys
import time
import unittest
from pathlib import Path

from tests._git_workspace import TempWorkspaceMixin, write_config, write_state

from Supervisor.EvolutionDaemon import AutonomousEvolutionDaemon
from Supervisor.WorkspaceOrchestrator import (
    MODE_PROD_EVO,
    MODE_SELF_EVO,
    WorkspaceOrchestrator,
)
from Supervisor.launcher import SupervisorLauncher

ROOT_DIR = Path(__file__).resolve().parent.parent


class TestModeResolution(TempWorkspaceMixin):
    """Какой источник считать истиной о текущем режиме.

    ПЕРЕПИСАНО 2026-08-22. Первая версия этого класса (написанная до решения
    оператора по Вопросу 8) исходила из «state.json побеждает config» —
    ровно то, что решение отвергло: агент может дописать .ai_workspace_state.json
    через switch_mode()/POST /api/mode, но не может отредактировать
    why_ai_config.yaml (зона R). Если бы состояние побеждало, агент получил
    бы способ самовольно переключиться в self_evo и включить фоновую
    генерацию. Явный аргумент оператора: "state.json — простой read-only
    кэш... система просто исполняет волю оператора [из YAML]". Тесты ниже
    проверяют именно этот, а не прежний, контракт.
    """

    def _resolve(self, root: Path) -> dict:
        return WorkspaceOrchestrator(workspace_root=root).resolve_active_mode()

    def test_config_is_the_sole_source_of_truth(self):
        """YAML решает, даже когда state.json прямо противоречит ему."""
        root = self.make_workspace()
        write_config(root, active_mode="self_evo")
        write_state(root, "project")  # état, который старый код счёл бы prod_evo
        res = self._resolve(root)
        self.assertEqual(res["mode"], MODE_SELF_EVO)
        self.assertTrue(res["source"].startswith("why_ai_config.yaml"), res["source"])

    def test_state_file_content_is_never_consulted(self):
        """Обратный случай: state.json говорит self_evo, YAML — prod_evo. Побеждает YAML."""
        root = self.make_workspace()
        write_config(root, active_mode="prod_evo")
        write_state(root, "agent")  # état, который старый код счёл бы self_evo
        res = self._resolve(root)
        self.assertEqual(res["mode"], MODE_PROD_EVO)

    def test_config_used_when_state_missing(self):
        root = self.make_workspace()
        write_config(root, active_mode="self_evo")
        res = self._resolve(root)
        self.assertEqual(res["mode"], MODE_SELF_EVO)
        self.assertTrue(res["source"].startswith("why_ai_config.yaml"), res["source"])

    def test_corrupt_state_file_does_not_affect_resolution(self):
        """Состояние не читается вообще — его битость не может ни на что повлиять."""
        root = self.make_workspace()
        write_config(root, active_mode="self_evo")
        (root / ".ai_workspace_state.json").write_text("{ not json", encoding="utf-8")
        res = self._resolve(root)
        self.assertEqual(res["mode"], MODE_SELF_EVO)
        self.assertTrue(res["source"].startswith("why_ai_config.yaml"), res["source"])

    def test_unknown_mode_string_is_not_silently_accepted(self):
        """'manual_override' задокументирован в why_ai_config.yaml, но не реализован — не self_evo."""
        root = self.make_workspace()
        write_config(root, active_mode="manual_override")
        res = self._resolve(root)
        self.assertEqual(res["mode"], MODE_PROD_EVO)
        self.assertEqual(res["source"], "default")

    def test_no_sources_at_all_fails_closed_to_prod_evo(self):
        """Отсутствие данных = фоновая генерация выключена, а не включена."""
        root = self.make_workspace()
        res = self._resolve(root)
        self.assertEqual(res["mode"], MODE_PROD_EVO)
        self.assertEqual(res["source"], "default")

    def test_resolution_does_not_create_state_file(self):
        """Чтение режима обязано быть без побочных эффектов.

        get_current_topology() при отсутствии файла ВЫЗЫВАЕТ switch_mode() и
        записывает состояние. Резолвер режима так делать не должен: телеметрия
        не имеет права менять то, что измеряет — и по новому контракту она
        state.json вообще не касается, ни на чтение, ни на запись.
        """
        root = self.make_workspace()
        write_config(root, active_mode="prod_evo")
        self._resolve(root)
        self.assertFalse((root / ".ai_workspace_state.json").exists())


class TestGracefulTermination(TempWorkspaceMixin):
    """Останов должен быть настоящим, а не полем в JSON."""

    def _spawn_victim(self) -> subprocess.Popen:
        proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
        self.addCleanup(self._ensure_dead, proc)
        # Дать интерпретатору стартовать, иначе PID может быть ещё не активен.
        for _ in range(50):
            if proc.poll() is None:
                break
            time.sleep(0.02)
        return proc

    @staticmethod
    def _ensure_dead(proc: subprocess.Popen) -> None:
        if proc.poll() is None:
            try:
                proc.kill()
                proc.wait(timeout=10)
            except Exception:
                pass

    def test_pid_registry_is_resolved_against_workspace_root(self):
        """SupervisorLauncher(workspace_root=X) обязан читать реестр PID из X.

        Раньше PID_STATE_FILE резолвился относительно cwd, поэтому
        SupervisorLauncher(workspace_root=ROOT_DIR) в Core/server.py читал не тот
        реестр, если демон запущен из другого каталога. Тест выполняется из
        корня репозитория, а реестр лежит во временном каталоге — если путь
        берётся из cwd, список PID окажется пустым.
        """
        root = self.make_workspace()
        (root / ".supervisor_pids.json").write_text(
            json.dumps({"pids": [424242]}), encoding="utf-8"
        )
        launcher = SupervisorLauncher(workspace_root=root)
        self.assertEqual(launcher.active_pids, [424242])

    def test_terminate_background_kills_registered_process(self):
        """Зарегистрированный процесс обязан перестать существовать."""
        root = self.make_workspace()
        victim = self._spawn_victim()
        (root / ".supervisor_pids.json").write_text(
            json.dumps({"pids": [victim.pid]}), encoding="utf-8"
        )

        report = SupervisorLauncher(workspace_root=root).terminate_background(
            reason="unit test"
        )

        self.assertEqual(report["signal"], "SIGTERM")
        self.assertEqual(report["registered_pids"], [victim.pid])
        self.assertEqual(report["terminated_count"], 1)
        # Главное утверждение: процесса больше нет.
        victim.wait(timeout=20)
        self.assertIsNotNone(victim.poll())

    def test_terminate_background_clears_registry(self):
        root = self.make_workspace()
        (root / ".supervisor_pids.json").write_text(
            json.dumps({"pids": []}), encoding="utf-8"
        )
        launcher = SupervisorLauncher(workspace_root=root)
        report = launcher.terminate_background(reason="empty registry")
        self.assertEqual(report["terminated_count"], 0)
        self.assertEqual(report["registered_pids"], [])
        saved = json.loads((root / ".supervisor_pids.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["pids"], [])

    def test_panic_stop_still_returns_10_and_uses_forced_path(self):
        """Рефакторинг общего цикла не имеет права изменить поведение /panic."""
        root = self.make_workspace()
        (root / ".supervisor_pids.json").write_text(
            json.dumps({"pids": []}), encoding="utf-8"
        )
        self.assertEqual(SupervisorLauncher(workspace_root=root).panic_stop("test"), 10)


class TestDaemonProdEvoGate(TempWorkspaceMixin):
    """Гейт режима внутри AutonomousEvolutionDaemon."""

    def _daemon(self, root: Path) -> AutonomousEvolutionDaemon:
        return AutonomousEvolutionDaemon(workspace_root=root)

    def test_prod_evo_blocks_cycle_even_when_feature_flag_is_on(self):
        """Режим сильнее флага: background_consciousness.enabled=true не спасает."""
        root = self.make_workspace(git=True)
        write_config(root, active_mode="prod_evo", background_enabled=True)
        write_state(root, "project")

        result = self._daemon(root).run_evolution_cycle(task_name="blocked", force=True)

        self.assertEqual(result["status"], "PROD_EVO_SIGTERM")
        self.assertFalse(result["background_allowed"])
        self.assertEqual(result["mode_resolution"]["mode"], MODE_PROD_EVO)
        self.assertIsNotNone(result["sigterm"])

    def test_prod_evo_gate_runs_before_sandbox_creation(self):
        """Ни одного git worktree не должно быть создано: ресурсы не тратятся."""
        root = self.make_workspace(git=True)
        write_config(root, active_mode="prod_evo", background_enabled=True)
        write_state(root, "project")

        self._daemon(root).run_evolution_cycle(task_name="no-sandbox", force=True)

        created = [p for p in (root / "worktrees").iterdir() if p.is_dir()]
        self.assertEqual(created, [], f"песочница создана вопреки [prod_evo]: {created}")

    def test_prod_evo_actually_sigterms_registered_daemon_process(self):
        """Требование дословно: демон ОТПРАВЛЯЕТСЯ В SIGTERM, а не «помечается»."""
        root = self.make_workspace(git=True)
        write_config(root, active_mode="prod_evo", background_enabled=True)
        write_state(root, "project")

        victim = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
        self.addCleanup(TestGracefulTermination._ensure_dead, victim)
        (root / ".supervisor_pids.json").write_text(
            json.dumps({"pids": [victim.pid]}), encoding="utf-8"
        )

        result = self._daemon(root).run_evolution_cycle(task_name="sigterm", force=True)

        self.assertEqual(result["sigterm"]["terminated_count"], 1)
        victim.wait(timeout=20)
        self.assertIsNotNone(victim.poll())

    def test_self_evo_does_not_trigger_sigterm(self):
        """Обратная сторона: гейт обязан быть управляемым режимом, а не константой."""
        root = self.make_workspace(git=True)
        write_config(root, active_mode="self_evo", background_enabled=False)
        write_state(root, "agent")

        result = self._daemon(root).run_evolution_cycle(task_name="allowed", force=True)

        self.assertNotEqual(result["status"], "PROD_EVO_SIGTERM")
        self.assertEqual(result["status"], "MODULE_DISABLED")

    def test_enforce_mode_policy_is_reusable_out_of_band(self):
        root = self.make_workspace(git=True)
        write_config(root, active_mode="self_evo", background_enabled=True)
        write_state(root, "agent")
        report = self._daemon(root).enforce_mode_policy()
        self.assertTrue(report["background_allowed"])
        self.assertIsNone(report["sigterm"])


class TestEvolutionDaemonCLI(TempWorkspaceMixin):
    """Классовый API, покрытый тестами, не доказывает работоспособность CLI."""

    def _run_cli(self, root: Path, *args) -> subprocess.CompletedProcess:
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        return subprocess.run(
            [sys.executable, str(ROOT_DIR / "Supervisor" / "EvolutionDaemon.py"), *args],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            cwd=str(root), timeout=90, env=env,
        )

    def test_cli_enforce_mode_reports_prod_evo(self):
        root = self.make_workspace(git=True)
        write_config(root, active_mode="prod_evo", background_enabled=True)
        write_state(root, "project")

        res = self._run_cli(root, "--enforce-mode")

        self.assertEqual(res.returncode, 0, res.stderr)
        payload = json.loads(res.stdout)
        self.assertFalse(payload["background_allowed"])
        self.assertEqual(payload["mode_resolution"]["mode"], MODE_PROD_EVO)

    def test_cli_status_exposes_resolved_mode(self):
        root = self.make_workspace(git=True)
        write_config(root, active_mode="self_evo", background_enabled=True)
        write_state(root, "agent")

        res = self._run_cli(root, "--status")

        self.assertEqual(res.returncode, 0, res.stderr)
        payload = json.loads(res.stdout)
        self.assertEqual(payload["active_mode"], MODE_SELF_EVO)
        self.assertTrue(payload["background_allowed"])

    def test_cli_status_does_not_terminate_anything(self):
        """--status обязан быть чтением: диагностика не глушит процессы."""
        root = self.make_workspace(git=True)
        write_config(root, active_mode="prod_evo", background_enabled=True)
        write_state(root, "project")

        victim = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        self.addCleanup(TestGracefulTermination._ensure_dead, victim)
        (root / ".supervisor_pids.json").write_text(
            json.dumps({"pids": [victim.pid]}), encoding="utf-8"
        )

        res = self._run_cli(root, "--status")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIsNone(victim.poll(), "--status убил зарегистрированный процесс")


if __name__ == "__main__":
    unittest.main()
