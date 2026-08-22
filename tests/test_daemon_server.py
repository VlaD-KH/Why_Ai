#!/usr/bin/env python3
"""
Unit tests for Why_Ai/Core/server.py
Verifies HTTP REST API status, Swarm Task-Tree, Living Identity, config, mode switching, and DB sync endpoints.
"""

import http.client
import http.server
import json
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


if __name__ == "__main__":
    unittest.main()
