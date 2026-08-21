#!/usr/bin/env python3
"""
Unit tests for Tool/mcp_server.py
Verifies FastMCP tool registration, parameter schema generation, and tool invocation.
"""

import unittest
from Tool.mcp_server import FastMCPServer, mcp


class TestFastMCPServer(unittest.TestCase):

    def setUp(self):
        self.server = FastMCPServer(name="Test-FastMCP")

    def test_tool_decorator_and_schema(self):
        """Проверка генерации схемы параметров декоратором @tool."""
        @self.server.tool(name="test_echo", description="Тестовая функция эхо")
        def echo_tool(msg: str, count: int = 1) -> dict:
            return {"echo": msg * count}

        tools = self.server.list_tools()
        self.assertEqual(len(tools), 1)
        self.assertEqual(tools[0]["name"], "test_echo")
        self.assertIn("msg", tools[0]["parameters"]["properties"])
        self.assertIn("count", tools[0]["parameters"]["properties"])

    def test_call_tool_execution(self):
        """Проверка вызова зарегистрированного инструмента."""
        res = mcp.call_tool("github_create_draft_pr", {
            "title": "Test PR",
            "body": "Automated test body",
            "head_branch": "feature/test",
            "base_branch": "main"
        })
        self.assertFalse(res["isError"])
        self.assertIn("DRAFT_PR_CREATED", res["content"][0]["text"])

    def test_nonexistent_tool(self):
        """Проверка обработки вызова неизвестного инструмента."""
        res = self.server.call_tool("unknown_tool", {})
        self.assertTrue(res["isError"])


if __name__ == "__main__":
    unittest.main()
