#!/usr/bin/env python3
"""
Unit tests for Why_Ai/Core/server.py
Verifies HTTP REST API status, Swarm Task-Tree, Living Identity, config, mode switching, and DB sync endpoints.
"""

import http.client
import http.server
import json
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from Core.server import ControlApiHandler

TEST_PORT = 18765


class TestDaemonServer(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", TEST_PORT), ControlApiHandler)
        cls.server_thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.server_thread.start()
        time.sleep(0.3)

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def test_api_status_endpoint(self):
        """Проверка получения JSON статуса от /api/status."""
        conn = http.client.HTTPConnection("127.0.0.1", TEST_PORT, timeout=3)
        conn.request("GET", "/api/status")
        resp = conn.getresponse()
        self.assertEqual(resp.status, 200)
        data = json.loads(resp.read().decode("utf-8"))
        self.assertEqual(data["status"], "RUNNING")
        self.assertIn("verified_tests", data)
        conn.close()

    @unittest.expectedFailure
    def test_api_status_no_hardcoded_test_count(self):
        """verified_tests обязан быть фактическим подсчётом, не литералом.

        @expectedFailure: Core/server.py:118 сейчас жёстко возвращает
        "32/32 PASS" при 160 реальных тестах (Батч 0.3, Волна 0, зона R —
        ждёт оператора, см. docs/session_archive/2026-08-23/
        implementation_plan.md). Тест наблюдался красным против текущей
        реализации до коммита — это и есть Proof of Falsification, не
        просто предсказание. Как только Батч 0.3 закроет литерал, unittest
        отрапортует "unexpected success" (сам по себе провал прогона) —
        сигнал снять декоратор, а не тихо оставить тест недействующим.
        """
        conn = http.client.HTTPConnection("127.0.0.1", TEST_PORT, timeout=3)
        conn.request("GET", "/api/status")
        resp = conn.getresponse()
        data = json.loads(resp.read().decode("utf-8"))
        conn.close()
        self.assertNotIn("32/32", data["verified_tests"])

    def test_api_swarm_tasks_endpoint(self):
        """Дерево роя обязано отражать реальные git worktree-песочницы, а не литерал.

        Регрессия: subagents был захардкожен (scout-01/child-01/arbitrator-01),
        никак не связан с Supervisor.WorktreeSandbox.list_sandboxes() — см.
        docs/session_archive/2026-08-22-gate-wiring-and-telegram-audit/state.md,
        пункт 5.1.2 в docs/final_vision/03-roadmap.md.
        """
        from Supervisor.WorktreeSandbox import WorktreeSandboxManager
        from Supervisor.WorkspaceOrchestrator import WorkspaceOrchestrator

        root = Path(__file__).resolve().parent.parent
        manager = WorktreeSandboxManager(workspace_root=root)
        self.addCleanup(lambda: manager.remove_sandbox("swarmtest-verify"))
        sandbox = manager.create_sandbox(task_id="swarmtest-verify")

        conn = http.client.HTTPConnection("127.0.0.1", TEST_PORT, timeout=3)
        conn.request("GET", "/api/swarm/tasks")
        resp = conn.getresponse()
        self.assertEqual(resp.status, 200)
        data = json.loads(resp.read().decode("utf-8"))
        conn.close()

        self.assertIn("subagents", data)
        real_ids = {a["id"] for a in data["subagents"]}

        # Никаких выдуманных агентов, которых на самом деле нет.
        fake_ids = {"scout-01", "child-01", "arbitrator-01"}
        self.assertFalse(fake_ids & real_ids, "Дерево роя всё ещё содержит выдуманных агентов")

        # Реально созданная песочница обязана появиться в дереве.
        self.assertIn(sandbox["task_id"], real_ids)

        # mode обязан приходить из единственного источника истины
        # (WorkspaceOrchestrator.resolve_active_mode), а не из литерала "self_evo".
        expected_mode = WorkspaceOrchestrator(workspace_root=root).resolve_active_mode()["mode"]
        self.assertEqual(data["root_orchestrator"]["mode"], expected_mode)

    def test_api_identity_endpoint(self):
        """Проверка получения Living Identity от /api/identity."""
        conn = http.client.HTTPConnection("127.0.0.1", TEST_PORT, timeout=3)
        conn.request("GET", "/api/identity")
        resp = conn.getresponse()
        self.assertEqual(resp.status, 200)
        data = json.loads(resp.read().decode("utf-8"))
        self.assertTrue(data["identity_present"])
        self.assertTrue(data["identity_pinned"])
        conn.close()

    def test_api_config_endpoint(self):
        """Проверка получения why_ai_config.yaml через /api/config."""
        conn = http.client.HTTPConnection("127.0.0.1", TEST_PORT, timeout=3)
        conn.request("GET", "/api/config")
        resp = conn.getresponse()
        self.assertEqual(resp.status, 200)
        data = json.loads(resp.read().decode("utf-8"))
        self.assertEqual(data["system"]["project_name"], "Why_Ai")
        conn.close()

    def test_api_mode_switching(self):
        """Проверка переключения топологического режима через POST /api/mode."""
        conn = http.client.HTTPConnection("127.0.0.1", TEST_PORT, timeout=3)
        payload = json.dumps({"mode": "prod_evo"}).encode("utf-8")
        conn.request("POST", "/api/mode", body=payload, headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        self.assertEqual(resp.status, 200)
        data = json.loads(resp.read().decode("utf-8"))
        self.assertEqual(data["status"], "MODE_CHANGED")
        self.assertEqual(data["mode"], "prod_evo")
        conn.close()

    def _post_mode(self, payload: dict) -> tuple:
        conn = http.client.HTTPConnection("127.0.0.1", TEST_PORT, timeout=3)
        conn.request("POST", "/api/mode", body=json.dumps(payload).encode("utf-8"),
                     headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        status = resp.status
        data = json.loads(resp.read().decode("utf-8"))
        conn.close()
        return status, data

    def test_api_mode_switching_preserves_project_name(self):
        """/api/mode не должен молча сбрасывать project_name на 'default_project'.

        Регрессия: сервер вызывал orch.switch_mode(target_str) без второго
        аргумента, из-за чего использовался жёсткий дефолт "default_project" и
        любое переключение режима с дашборда переписывало реально
        сконфигурированное имя проекта (например "vanguard").
        """
        state_file = Path(__file__).resolve().parent.parent / ".ai_workspace_state.json"
        backup = state_file.read_text(encoding="utf-8") if state_file.exists() else None
        self.addCleanup(lambda: state_file.write_text(backup, encoding="utf-8") if backup else None)

        status, data = self._post_mode({"mode": "prod_evo", "project_name": "acme"})
        self.assertEqual(status, 200)
        self.assertEqual(data["result"]["project_name"], "acme")

        # Повторное переключение БЕЗ project_name обязано сохранить "acme",
        # а не тихо перезаписать его дефолтом.
        status2, data2 = self._post_mode({"mode": "self_evo"})
        self.assertEqual(status2, 200)
        status3, data3 = self._post_mode({"mode": "prod_evo"})
        self.assertEqual(status3, 200)
        self.assertEqual(data3["result"]["project_name"], "acme")

    def test_api_mode_switching_rejects_unknown_mode(self):
        """Неизвестное значение mode должно отклоняться, а не тихо трактоваться как 'project'.

        Регрессия: `"agent" if "self" in raw_mode.lower() or "agent" in raw_mode.lower()
        else "project"` резолвило ЛЮБУЮ нераспознанную строку (в т.ч. опечатки и
        заявленный в документации 'manual_override') в 'project' без предупреждения.
        """
        status, data = self._post_mode({"mode": "manual_override"})
        self.assertEqual(status, 400)
        self.assertIn("error", data)

    def test_api_sync_db(self):
        """Проверка синхронизации логов failures/ledger через POST /api/sync_db."""
        conn = http.client.HTTPConnection("127.0.0.1", TEST_PORT, timeout=3)
        conn.request("POST", "/api/sync_db")
        resp = conn.getresponse()
        self.assertEqual(resp.status, 200)
        data = json.loads(resp.read().decode("utf-8"))
        self.assertEqual(data["status"], "DB_SYNCED")
        conn.close()

    def test_api_sync_db_reads_the_real_failures_file(self):
        """/api/sync_db обязан читать Core/failures.jsonl, а не корень репозитория.

        Регрессия: Core/server.py собирал путь как ROOT_DIR / "failures.jsonl"
        (корень), а фактический файл лежит в Core/failures.jsonl — этот же путь
        использует Core/MetaOverPatch.py. При расхождении sync_db всегда видел
        0 записей, даже если сбои реально зафиксированы.
        """
        root = Path(__file__).resolve().parent.parent
        real_path = root / "Core" / "failures.jsonl"
        wrong_path = root / "failures.jsonl"

        real_backup = real_path.read_text(encoding="utf-8") if real_path.exists() else None
        wrong_existed = wrong_path.exists()

        def restore():
            if real_backup is None:
                real_path.unlink(missing_ok=True)
            else:
                real_path.write_text(real_backup, encoding="utf-8")
            if not wrong_existed:
                wrong_path.unlink(missing_ok=True)

        self.addCleanup(restore)

        # Гарантированно разные счётчики в правильном и неправильном месте,
        # чтобы тест не мог случайно пройти при перепутанном пути.
        real_path.write_text(
            '{"run_id": "sync-check-1"}\n{"run_id": "sync-check-2"}\n{"run_id": "sync-check-3"}\n',
            encoding="utf-8",
        )
        wrong_path.write_text('{"run_id": "should-not-be-read"}\n', encoding="utf-8")

        conn = http.client.HTTPConnection("127.0.0.1", TEST_PORT, timeout=3)
        conn.request("POST", "/api/sync_db")
        resp = conn.getresponse()
        self.assertEqual(resp.status, 200)
        data = json.loads(resp.read().decode("utf-8"))
        conn.close()

        failures_result = data.get("failures", {})
        self.assertEqual(failures_result.get("synced_records"), 3)
        self.assertIn("Core", str(failures_result.get("source_file", "")))

    def test_api_dvpn_endpoints(self):
        """Проверка REST эндпоинтов dVPN /api/dvpn/*."""
        # 1. GET /api/dvpn/status
        conn = http.client.HTTPConnection("127.0.0.1", TEST_PORT, timeout=3)
        conn.request("GET", "/api/dvpn/status")
        resp = conn.getresponse()
        self.assertEqual(resp.status, 200)
        status_data = json.loads(resp.read().decode("utf-8"))
        self.assertIn("status", status_data)
        conn.close()

        # 2. GET /api/dvpn/nodes
        conn = http.client.HTTPConnection("127.0.0.1", TEST_PORT, timeout=3)
        conn.request("GET", "/api/dvpn/nodes")
        resp = conn.getresponse()
        self.assertEqual(resp.status, 200)
        nodes_data = json.loads(resp.read().decode("utf-8"))
        self.assertIn("nodes", nodes_data)
        self.assertGreater(len(nodes_data["nodes"]), 0)
        conn.close()

        # 3. POST /api/dvpn/connect
        conn = http.client.HTTPConnection("127.0.0.1", TEST_PORT, timeout=3)
        payload = json.dumps({"user_id": "test_api_user", "tier": "premium"}).encode("utf-8")
        conn.request("POST", "/api/dvpn/connect", body=payload, headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        self.assertEqual(resp.status, 200)
        conn_data = json.loads(resp.read().decode("utf-8"))
        self.assertEqual(conn_data["status"], "CONNECTED")
        conn.close()

        # 4. POST /api/dvpn/switch_profile
        conn = http.client.HTTPConnection("127.0.0.1", TEST_PORT, timeout=3)
        payload = json.dumps({"user_id": "test_api_user", "tier": "free"}).encode("utf-8")
        conn.request("POST", "/api/dvpn/switch_profile", body=payload, headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        self.assertEqual(resp.status, 200)
        switch_data = json.loads(resp.read().decode("utf-8"))
        self.assertEqual(switch_data["status"], "TIER_SWITCHED")
        conn.close()

        # 5. POST /api/dvpn/fallback
        conn = http.client.HTTPConnection("127.0.0.1", TEST_PORT, timeout=3)
        payload = json.dumps({"user_id": "test_api_user", "reason": "API test fallback"}).encode("utf-8")
        conn.request("POST", "/api/dvpn/fallback", body=payload, headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        self.assertEqual(resp.status, 200)
        fb_data = json.loads(resp.read().decode("utf-8"))
        self.assertEqual(fb_data["status"], "FALLBACK_SUCCESS")
        conn.close()

    def test_dashboard_html_served(self):
        """Проверка отдачи dashboard.html по корневому URL."""
        conn = http.client.HTTPConnection("127.0.0.1", TEST_PORT, timeout=3)
        conn.request("GET", "/")
        resp = conn.getresponse()
        self.assertEqual(resp.status, 200)
        self.assertIn("text/html", resp.getheader("Content-Type", ""))
        conn.close()


# /api/tests запускает subprocess.run([..., "-m", "unittest", "discover",
# "-s", "tests", ...]) — то есть заново находит и запускает ВЕСЬ каталог
# tests/, включая файл, откуда пришёл HTTP-запрос. Пойман вживую реальный
# инфраструктурный дефект: тест внутри tests/, бьющий по живому /api/tests
# через HTTP, рекурсивно пересоздаёт сам себя на каждом уровне вложенности
# (discover находит этот же тестовый метод, тот снова шлёт HTTP-запрос,
# который снова спавнит discover...) — цепочка блокирующих subprocess.run
# длиной в несколько уровней, ~60+ секунд до таймаута вместо честной ошибки.
# Подтверждено минимальным репро вне unittest-раннера (тот же эффект без
# самого фреймворка тестов) — это свойство Core/server.py:223-234, не
# особенность гарнеса. Не тестируется отдельно здесь: правка — зона R, вне
# Батча 0.2. Вместо живого HTTP-удара по self-referencing tests/ проверяем
# сам факт, ради которого была правка дашборда: unittest.TextTestRunner
# пишет итоговую строку в stderr, не в stdout — против изолированной
# временной директории, без риска самозапуска.
class TestUnittestSummaryStream(unittest.TestCase):

    def test_unittest_writes_summary_to_stderr_not_stdout(self):
        """Регрессия, пойманная не при написании, а при живой проверке в
        браузере (Eye/dashboard.html, Батч 0.1): дашборд искал "Ran N tests"
        в stdout ответа /api/tests и всегда получал "?/?", потому что
        unittest.TextTestRunner печатает итоговую строку в stderr. Тест
        воспроизводит тот же факт против настоящего `python -m unittest
        discover`, изолированной временной директорией — без обращения к
        /api/tests и без риска самозапуска (см. комментарий выше класса).
        """
        tmp_dir = tempfile.mkdtemp(prefix="unittest-stream-check-")
        try:
            (Path(tmp_dir) / "test_trivial.py").write_text(
                "import unittest\n"
                "class T(unittest.TestCase):\n"
                "    def test_ok(self):\n"
                "        self.assertTrue(True)\n",
                encoding="utf-8",
            )
            res = subprocess.run(
                [sys.executable, "-m", "unittest", "discover", "-s", tmp_dir, "-p", "test_*.py"],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
            )
            self.assertEqual(res.returncode, 0)
            self.assertNotRegex(res.stdout, r"Ran \d+ tests?",
                                 "unittest сменил поведение и теперь пишет итог в stdout — обновить дашборд")
            self.assertRegex(res.stderr, r"Ran 1 tests?")
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
