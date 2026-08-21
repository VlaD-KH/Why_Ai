#!/usr/bin/env python3
"""
Unit tests for Core/dvpn/profiles.py
Verifies UserTier models, TierPolicy constraints, TierManager session handling, and bandwidth quota enforcement.
"""

import unittest
from Core.dvpn.profiles import UserTier, TierPolicy, TierManager, TIER_POLICIES


class TestDVPNProfiles(unittest.TestCase):

    def setUp(self):
        self.manager = TierManager()

    def test_tier_policies_constraints(self):
        """Проверка ограничений и привилегий для различных тарифов."""
        free_policy = self.manager.get_policy(UserTier.FREE)
        prem_policy = self.manager.get_policy(UserTier.PREMIUM)
        ent_policy = self.manager.get_policy(UserTier.ENTERPRISE)

        # Free tier checks
        self.assertEqual(free_policy.max_bandwidth_mbps, 25)
        self.assertFalse(free_policy.allow_dedicated_relays)
        self.assertFalse(free_policy.kill_switch_mandatory)
        self.assertIn("wireguard", free_policy.allowed_protocols)
        self.assertNotIn("vless", free_policy.allowed_protocols)

        # Premium tier checks
        self.assertEqual(prem_policy.max_bandwidth_mbps, 500)
        self.assertTrue(prem_policy.allow_dedicated_relays)
        self.assertTrue(prem_policy.kill_switch_mandatory)
        self.assertIn("vless", prem_policy.allowed_protocols)
        self.assertIn("trojan", prem_policy.allowed_protocols)

        # Enterprise tier checks
        self.assertEqual(ent_policy.max_bandwidth_mbps, 2000)
        self.assertIn("multihop", ent_policy.allowed_protocols)

    def test_session_creation_and_tier_switch(self):
        """Проверка создания пользовательской сессии и динамической смены тарифа."""
        session = self.manager.create_session("user_test_01", UserTier.FREE)
        self.assertEqual(session.user_id, "user_test_01")
        self.assertEqual(session.tier, UserTier.FREE)
        self.assertFalse(session.kill_switch_active)

        # Смена тарифа на Premium
        updated_session = self.manager.switch_tier("user_test_01", UserTier.PREMIUM)
        self.assertEqual(updated_session.tier, UserTier.PREMIUM)
        self.assertTrue(updated_session.kill_switch_active)

    def test_protocol_and_node_access_control(self):
        """Проверка разграничения прав доступа к протоколам и узлам."""
        # Free user
        self.assertTrue(self.manager.is_protocol_allowed(UserTier.FREE, "wireguard"))
        self.assertFalse(self.manager.is_protocol_allowed(UserTier.FREE, "vless"))
        self.assertTrue(self.manager.is_node_accessible(UserTier.FREE, "free"))
        self.assertFalse(self.manager.is_node_accessible(UserTier.FREE, "premium"))

        # Premium user
        self.assertTrue(self.manager.is_protocol_allowed(UserTier.PREMIUM, "vless"))
        self.assertTrue(self.manager.is_node_accessible(UserTier.PREMIUM, "free"))
        self.assertTrue(self.manager.is_node_accessible(UserTier.PREMIUM, "premium"))
        self.assertFalse(self.manager.is_node_accessible(UserTier.PREMIUM, "enterprise"))

    def test_bandwidth_quota_accounting(self):
        """Проверка учета переданного трафика и блокировки при превышении квоты Free."""
        session = self.manager.create_session("user_quota_test", UserTier.FREE)

        # Передача 5 GB (норма)
        ok = self.manager.record_traffic("user_quota_test", 2 * 1024**3, 3 * 1024**3)
        self.assertTrue(ok)

        # Передача еще 6 GB (превышение лимита 10 GB для Free)
        ok_exceeded = self.manager.record_traffic("user_quota_test", 3 * 1024**3, 3 * 1024**3)
        self.assertFalse(ok_exceeded)


if __name__ == "__main__":
    unittest.main()
