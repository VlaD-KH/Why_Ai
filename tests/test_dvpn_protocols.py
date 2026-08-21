#!/usr/bin/env python3
"""
Unit tests for Core/dvpn/protocols.py
Verifies ProtocolFactory, WireGuard config export (.conf), VLESS-Reality URI, and Shadowsocks URI generation.
"""

import unittest
from Core.dvpn.protocols import (
    ProtocolType,
    ProtocolFactory,
    WireGuardConfig,
    VLESSConfig,
    ShadowsocksConfig,
)


class TestDVPNProtocols(unittest.TestCase):

    def test_wireguard_config_export(self):
        """Проверка генерации конфигурационного файла WireGuard."""
        wg = WireGuardConfig(
            server_address="185.100.85.12",
            server_port=51820,
            name="WhyAi_NL_Amsterdam",
            private_key="aW50ZXJuYWxfa2V5",
            peer_public_key="ZXh0ZXJuYWxfa2V5",
            client_ip="10.66.66.2/32",
            allowed_ips="0.0.0.0/0",
            preshared_key="cHJlc2hhcmVkX2tleQ==",
        )
        conf = wg.export()
        self.assertIn("[Interface]", conf)
        self.assertIn("PrivateKey = aW50ZXJuYWxfa2V5", conf)
        self.assertIn("Address = 10.66.66.2/32", conf)
        self.assertIn("[Peer]", conf)
        self.assertIn("PublicKey = ZXh0ZXJuYWxfa2V5", conf)
        self.assertIn("Endpoint = 185.100.85.12:51820", conf)
        self.assertIn("PresharedKey = cHJlc2hhcmVkX2tleQ==", conf)

    def test_vless_reality_uri_export(self):
        """Проверка генерации VLESS-Reality URI ссылки."""
        vless = VLESSConfig(
            server_address="194.26.29.44",
            server_port=443,
            name="WhyAi_DE_Frankfurt",
            uuid="a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            public_key="k1e2y3p4u5b6l7i8c9k0e1y2p3u4b5l6i7c8=",
            short_id="0123456789abcdef",
            sni="www.microsoft.com",
            flow="xtls-rprx-vision",
        )
        uri = vless.export()
        self.assertTrue(uri.startswith("vless://a1b2c3d4-e5f6-7890-abcd-ef1234567890@194.26.29.44:443?"))
        self.assertIn("security=reality", uri)
        self.assertIn("flow=xtls-rprx-vision", uri)
        self.assertIn("sni=www.microsoft.com", uri)
        self.assertIn("#WhyAi_DE_Frankfurt", uri)

    def test_shadowsocks_uri_export(self):
        """Проверка генерации Shadowsocks AEAD URI ссылки."""
        ss = ShadowsocksConfig(
            server_address="104.244.72.115",
            server_port=8388,
            name="WhyAi_US_NY",
            cipher="chacha20-ietf-poly1305",
            password="secret_pass_2026",
        )
        uri = ss.export()
        self.assertTrue(uri.startswith("ss://"))
        self.assertIn("@104.244.72.115:8388#WhyAi_US_NY", uri)

    def test_protocol_factory_dispatch(self):
        """Проверка фабричного создания конфигураций."""
        wg_cfg = ProtocolFactory.create_config(ProtocolType.WIREGUARD, {"server_address": "1.2.3.4"})
        self.assertIsInstance(wg_cfg, WireGuardConfig)

        vless_cfg = ProtocolFactory.create_config(ProtocolType.VLESS, {"server_address": "5.6.7.8"})
        self.assertIsInstance(vless_cfg, VLESSConfig)

        ss_cfg = ProtocolFactory.create_config(ProtocolType.SHADOWSOCKS, {"server_address": "9.10.11.12"})
        self.assertIsInstance(ss_cfg, ShadowsocksConfig)


if __name__ == "__main__":
    unittest.main()
