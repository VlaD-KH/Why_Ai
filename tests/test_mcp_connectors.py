#!/usr/bin/env python3
"""
Unit tests for Tool/connectors (GitHub, PostgreSQL/Prisma, Telegram) and FastMCP server integration.
"""

import unittest
from pathlib import Path
import sys
import os

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "Tool"))

from Tool.connectors.github_connector import GitHubConnector
from Tool.connectors.postgres_connector import PostgresConnector
from Tool.connectors.telegram_connector import TelegramConnector
from Tool.mcp_server import mcp


class TestMCPConnectors(unittest.TestCase):

    def setUp(self):
        self.github = GitHubConnector()
        self.postgres = PostgresConnector()
        self.telegram = TelegramConnector()

    # --- GitHub Connector Tests ---
    def test_github_get_repo_info(self):
        info = self.github.get_repo_info("VlaD-KH/_Ai")
        self.assertEqual(info["repository"], "VlaD-KH/_Ai")
        self.assertEqual(info["default_branch"], "main")
        self.assertTrue(info["branch_protection_active"])

    def test_github_create_draft_pr_enforces_human_approval(self):
        pr = self.github.create_draft_pr(
            repo="VlaD-KH/_Ai",
            title="feat: add adaptive dVPN routing engine",
            body="Autonomous candidate diff approved by Why_Ai Multi-Harness Quorum.",
            head_branch="sandbox/dvpn-engine",
            base_branch="main",
        )
        self.assertEqual(pr["status"], "DRAFT_PR_CREATED")
        self.assertTrue(pr["is_draft"])
        self.assertFalse(pr["mergeable_by_agent"])
        self.assertTrue(pr["requires_human_approval"])

    def test_github_list_commits(self):
        commits = self.github.list_commits("VlaD-KH/_Ai", branch="main", limit=5)
        self.assertEqual(len(commits), 5)
        self.assertTrue(all(len(c["sha"]) == 40 for c in commits))

    # --- PostgreSQL Connector Tests ---
    def test_postgres_execute_query_safe(self):
        res = self.postgres.execute_query("SELECT * FROM nodes WHERE tier = 'premium';", read_only=True)
        self.assertEqual(res["status"], "SUCCESS")
        self.assertTrue(res["read_only"])
        self.assertGreater(len(res["results"]), 0)

    def test_postgres_blocks_destructive_ddl(self):
        with self.assertRaises(PermissionError):
            self.postgres.execute_query("DROP TABLE users;", read_only=False)

    def test_postgres_inspect_schema(self):
        schema = self.postgres.inspect_schema("nodes")
        self.assertEqual(schema["status"], "SCHEMA_INSPECTED")
        self.assertGreaterEqual(schema["columns_count"], 5)
        col_names = [c["name"] for c in schema["columns"]]
        self.assertIn("ip_address", col_names)
        self.assertIn("tier", col_names)

    def test_postgres_pool_health(self):
        health = self.postgres.pool_health()
        self.assertEqual(health["status"], "HEALTHY")
        self.assertGreater(health["pool_capacity"], 0)

    def test_prisma_schema_diff_safe(self):
        curr = "model Node { id String @id }\n"
        target = "model Node { id String @id }\nmodel User { id String @id }\n"
        diff = self.postgres.prisma_schema_diff(curr, target)
        self.assertEqual(diff["diff_status"], "COMPUTED")
        self.assertTrue(diff["safe_migration"])
        self.assertFalse(diff["is_destructive"])

    # --- Telegram Connector Tests ---
    def test_telegram_send_alert(self):
        res = self.telegram.send_alert(chat_id="@why_ai_ops", message="System health: 100%", priority="INFO")
        self.assertEqual(res["status"], "SENT")
        self.assertTrue(res["delivered"])

    def test_telegram_send_panic_notification(self):
        res = self.telegram.send_panic_notification(exit_code=10, reason="Out-of-band operator signal")
        self.assertEqual(res["status"], "SENT")
        self.assertEqual(res["priority"], "CRITICAL")

    def test_telegram_send_quorum_verdict(self):
        res = self.telegram.send_quorum_verdict(diff_sha="sha256:abcd1234ef56", verdict="APPROVED")
        self.assertEqual(res["status"], "SENT")

    # --- FastMCP Server Integration Tests ---
    def test_fastmcp_tools_registered_and_callable(self):
        tools = mcp.list_tools()
        tool_names = [t["name"] for t in tools]
        
        self.assertIn("github_get_repo_info", tool_names)
        self.assertIn("github_create_draft_pr", tool_names)
        self.assertIn("postgres_execute_query", tool_names)
        self.assertIn("postgres_inspect_schema", tool_names)
        self.assertIn("telegram_send_alert", tool_names)
        self.assertIn("telegram_send_panic_notification", tool_names)
        self.assertIn("dvpn_get_status", tool_names)
        self.assertIn("dvpn_list_nodes", tool_names)
        self.assertIn("dvpn_connect_node", tool_names)
        self.assertIn("dvpn_trigger_fallback", tool_names)

        # Call via MCP call_tool
        call_res = mcp.call_tool("github_get_repo_info", {"repo": "VlaD-KH/_Ai"})
        self.assertFalse(call_res["isError"])
        self.assertIn("VlaD-KH/_Ai", call_res["content"][0]["text"])

        # Call dVPN tool via MCP
        dvpn_res = mcp.call_tool("dvpn_connect_node", {"user_id": "fastmcp_user", "tier": "premium"})
        self.assertFalse(dvpn_res["isError"])
        self.assertIn("CONNECTED", dvpn_res["content"][0]["text"])


if __name__ == "__main__":
    unittest.main()
