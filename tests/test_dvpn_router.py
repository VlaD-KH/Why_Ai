#!/usr/bin/env python3
"""
Unit tests for Core/dvpn/health_prober.py, Core/dvpn/engine.py, and Tool/connectors/dvpn_connector.py.
Verifies QoS scoring, EMA latency, Adaptive routing, Fail-Safe Fallback (<150ms), Kill-Switch, and FastMCP integration.
"""

import time
import unittest
from Core.dvpn.profiles import UserTier
from Core.dvpn.protocols import ProtocolType
from Core.dvpn.health_prober import HealthProber, DVPNNode, NodeStatus
from Core.dvpn.engine import AdaptiveDVPNRouter
from Tool.connectors.dvpn_connector import DVPNConnector


class TestDVPNRouterAndHealth(unittest.TestCase):

    def setUp(self):
        self.prober = HealthProber()
        self.router = AdaptiveDVPNRouter(health_prober=self.prober)
        self.connector = DVPNConnector(router=self.router)

    # --- Health Prober Tests ---
    def test_health_prober_initialization_and_filtering(self):
        """Проверка инициализации эталонных узлов и фильтрации."""
        all_nodes = self.prober.list_nodes()
        self.assertGreaterEqual(len(all_nodes), 5)

        free_nodes = self.prober.list_nodes(tier="free")
        self.assertTrue(all(n.tier_requirement == "free" for n in free_nodes))

        de_nodes = self.prober.list_nodes(country="DE")
        self.assertEqual(len(de_nodes), 1)
        self.assertEqual(de_nodes[0].country_code, "DE")

    def test_health_prober_ema_and_status_transitions(self):
        """Проверка сглаживания задержки EMA и переходов статусов узлов."""
        node = self.prober.get_node("node-nl-01")
        initial_ema = node.ema_latency_ms

        # Обновление метрик с повышенной задержкой
        updated = self.prober.update_probe_metrics(
            node_id="node-nl-01",
            latency_ms=100.0,
            packet_loss_pct=5.0,
        )
        self.assertGreater(updated.ema_latency_ms, initial_ema)
        self.assertEqual(updated.status, NodeStatus.ONLINE)

        # Симуляция сильной деградации (>30% потерь)
        degraded = self.prober.update_probe_metrics(
            node_id="node-nl-01",
            latency_ms=250.0,
            packet_loss_pct=40.0,
        )
        self.assertEqual(degraded.status, NodeStatus.DEGRADED)

        # Симуляция 3 таймаутов подряд -> OFFLINE
        for _ in range(3):
            self.prober.update_probe_metrics("node-nl-01", latency_ms=0, is_timeout=True)
        self.assertEqual(node.status, NodeStatus.OFFLINE)
        self.assertEqual(node.quality_score, 99999.0)

    def test_health_prober_offline_via_packet_loss_reachable(self):
        """OFFLINE должен достигаться через потерю пакетов (>80%), а не только через таймауты.

        Регрессия: условие `elif packet_loss_pct > 80.0` стояло после
        `if packet_loss_pct > 30.0 or ...`, которое перехватывает любое
        значение >30, включая всё, что >80 — ветка была недостижима.
        """
        offline_by_loss = self.prober.update_probe_metrics(
            node_id="node-de-01",
            latency_ms=20.0,
            packet_loss_pct=85.0,
        )
        self.assertEqual(offline_by_loss.status, NodeStatus.OFFLINE)

        # Промежуточное значение (>30, но <=80) обязано остаться DEGRADED,
        # а не тоже перескакивать в OFFLINE.
        degraded_only = self.prober.update_probe_metrics(
            node_id="node-de-01",
            latency_ms=20.0,
            packet_loss_pct=50.0,
        )
        self.assertEqual(degraded_only.status, NodeStatus.DEGRADED)

    # --- Adaptive Router Engine Tests ---
    def test_router_connect_free_and_premium_tiers(self):
        """Проверка маршрутизации для тарифов Free и Premium."""
        # Free подключение
        free_conn = self.router.connect(user_id="alice", tier=UserTier.FREE)
        self.assertEqual(free_conn.tier, UserTier.FREE)
        self.assertEqual(free_conn.active_node.tier_requirement, "free")
        self.assertFalse(free_conn.is_kill_switch_engaged)

        # Premium подключение
        prem_conn = self.router.connect(user_id="bob", tier=UserTier.PREMIUM)
        self.assertEqual(prem_conn.tier, UserTier.PREMIUM)
        self.assertTrue(prem_conn.is_kill_switch_engaged)
        self.assertEqual(prem_conn.active_node.tier_requirement, "premium")

    def test_router_fail_safe_fallback_performance(self):
        """
        Проверка мгновенного Fail-Safe Fallback переключения:
        - Время переключения обязано быть < 150ms
        - Сессия переводится на резервный узел без потери состояния
        """
        conn = self.router.connect(user_id="test_fallback_user", tier=UserTier.PREMIUM)
        initial_node_id = conn.active_node.node_id

        start_time = time.time()
        fallback_conn = self.router.trigger_fallback(
            user_id="test_fallback_user",
            reason="Simulated packet drop spike",
        )
        elapsed_ms = (time.time() - start_time) * 1000.0

        # Валидация инвариантов Fallback
        self.assertLess(elapsed_ms, 150.0, "Время переключения Fallback превышает лимит 150ms!")
        self.assertNotEqual(fallback_conn.active_node.node_id, initial_node_id)
        self.assertEqual(fallback_conn.fallback_count, 1)
        self.assertTrue(fallback_conn.is_kill_switch_engaged)
        self.assertEqual(len(self.router.fallback_history), 1)

    def test_router_profile_switch(self):
        """Проверка смены тарифного профиля пользователя с авто-переподключением."""
        conn = self.router.connect(user_id="charlie", tier=UserTier.FREE)
        self.assertEqual(conn.tier, UserTier.FREE)

        upgraded = self.router.switch_profile(user_id="charlie", new_tier=UserTier.PREMIUM)
        self.assertEqual(upgraded.tier, UserTier.PREMIUM)
        self.assertEqual(upgraded.active_node.tier_requirement, "premium")

    def test_router_status_telemetry(self):
        """Проверка формата телеметрии dVPN."""
        self.router.connect(user_id="dave", tier=UserTier.FREE)
        status = self.router.get_status(user_id="dave")
        self.assertEqual(status["status"], "CONNECTED")
        self.assertIn("active_node", status)
        self.assertIn("latency_ms", status["active_node"])
        self.assertIn("ema_latency_ms", status["active_node"])

    # --- FastMCP Connector Integration Tests ---
    def test_dvpn_mcp_connector_api(self):
        """Проверка вызовов методов через FastMCP коннектор."""
        status_before = self.connector.get_status("mcp_user")
        self.assertEqual(status_before["status"], "DISCONNECTED")

        nodes = self.connector.list_nodes(tier="free")
        self.assertGreater(len(nodes), 0)

        conn_res = self.connector.connect_node(user_id="mcp_user", tier="premium")
        self.assertEqual(conn_res["status"], "CONNECTED")
        self.assertEqual(conn_res["tier"], "premium")

        fallback_res = self.connector.trigger_fallback(user_id="mcp_user")
        self.assertEqual(fallback_res["status"], "FALLBACK_SUCCESS")

        cfg_res = self.connector.get_client_config(user_id="mcp_user")
        self.assertIn("config_content", cfg_res)


if __name__ == "__main__":
    unittest.main()
