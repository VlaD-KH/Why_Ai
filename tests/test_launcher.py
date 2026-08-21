#!/usr/bin/env python3
"""
Unit tests for Supervisor/launcher.py
Verifies lifecycle status, panic handling, and safety guards.
"""

import json
import subprocess
import sys
import unittest
from pathlib import Path
from Supervisor.launcher import SupervisorLauncher

ROOT_DIR = Path(__file__).resolve().parent.parent


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


class TestSupervisorLauncherCLI(unittest.TestCase):
    """Тесты уровня CLI.

    Существовавшие тесты проверяли только классовый API, поэтому дефект
    `type="str"` вместо `type=str` в add_argument (строки 121, 123) оставался
    незамеченным: argparse падал с `ValueError: 'str' is not callable` ещё до
    разбора аргументов, то есть внеполосный рубильник `--panic-stop` из
    командной строки не запускался вообще.
    """

    def _run_cli(self, *args):
        return subprocess.run(
            [sys.executable, str(ROOT_DIR / "Supervisor" / "launcher.py"), *args],
            capture_output=True, text=True, cwd=str(ROOT_DIR), timeout=30,
        )

    def test_cli_parser_constructs(self):
        """--help обязан отрабатывать: он доказывает, что парсер вообще строится."""
        res = self._run_cli("--help")
        self.assertEqual(res.returncode, 0, f"CLI не строится: {res.stderr}")
        self.assertNotIn("is not callable", res.stderr)

    def test_cli_status_returns_valid_json(self):
        """--status обязан отдавать разбираемый JSON, а не падать в argparse."""
        res = self._run_cli("--status")
        self.assertEqual(res.returncode, 0, f"--status упал: {res.stderr}")
        payload = json.loads(res.stdout)
        self.assertEqual(payload["status"], "RUNNING")
        self.assertTrue(payload["constitution_present"])

    def test_cli_panic_stop_exits_with_code_10(self):
        """Внеполосный рубильник обязан завершаться кодом 10 именно из CLI."""
        res = self._run_cli("--panic-stop", "--reason", "CLI regression test")
        self.assertNotIn("is not callable", res.stderr)
        self.assertEqual(res.returncode, 10, f"ожидался exit 10, получен {res.returncode}: {res.stderr}")


if __name__ == "__main__":
    unittest.main()
