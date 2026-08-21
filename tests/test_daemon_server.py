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
        """Проверка получения Swarm Task-Tree от /api/swarm/tasks."""
        conn = http.client.HTTPConnection("127.0.0.1", TEST_PORT, timeout=3)
        conn.request("GET", "/api/swarm/tasks")
        resp = conn.getresponse()
        self.assertEqual(resp.status, 200)
        data = json.loads(resp.read().decode("utf-8"))
        self.assertEqual(data["swarm_state"], "ACTIVE / ARMED")
        self.assertIn("subagents", data)
        self.assertGreaterEqual(len(data["subagents"]), 3)
        conn.close()

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
