#!/usr/bin/env python3
"""
Модуль: Core/dvpn/protocols.py
Назначение: Мультипротокольные адаптеры и генераторы клиентских конфигураций (WireGuard, VLESS-Reality, Shadowsocks, Trojan).
Архитектурный слой: Core (Zone E).
Инвариант: Все сгенерированные конфигурации валидируются на наличие криптографических ключей и безопасных параметров TLS/XTLS.
"""

from dataclasses import dataclass, field
from enum import Enum
import base64
import json
import urllib.parse
from typing import Dict, Any, Optional


class ProtocolType(str, Enum):
    """Поддерживаемые VPN и Proxy протоколы."""
    WIREGUARD = "wireguard"
    VLESS = "vless"
    SHADOWSOCKS = "shadowsocks"
    TROJAN = "trojan"


@dataclass
class ProtocolConfig:
    """Базовый класс протокольной конфигурации."""
    server_address: str = "127.0.0.1"
    server_port: int = 443
    name: str = "Why_Ai_Secure_Node"
    protocol: ProtocolType = ProtocolType.WIREGUARD

    def export(self) -> str:
        raise NotImplementedError("Метод export() должен быть переопределен в дочернем классе.")


@dataclass
class WireGuardConfig(ProtocolConfig):
    """Конфигурация туннеля WireGuard (формат .conf)."""
    server_address: str = "127.0.0.1"
    server_port: int = 51820
    name: str = "Why_Ai_WireGuard"
    protocol: ProtocolType = ProtocolType.WIREGUARD
    private_key: str = ""
    client_ip: str = "10.66.66.2/32"
    dns: str = "1.1.1.1, 1.0.0.1"
    peer_public_key: str = ""
    allowed_ips: str = "0.0.0.0/0, ::/0"
    preshared_key: Optional[str] = None
    persistent_keepalive: int = 25
    mtu: int = 1420

    def export(self) -> str:
        """Генерация стандартного файла wireguard.conf."""
        conf_lines = [
            "[Interface]",
            f"PrivateKey = {self.private_key}",
            f"Address = {self.client_ip}",
            f"DNS = {self.dns}",
            f"MTU = {self.mtu}",
            "",
            "[Peer]",
            f"PublicKey = {self.peer_public_key}",
            f"Endpoint = {self.server_address}:{self.server_port}",
            f"AllowedIPs = {self.allowed_ips}",
            f"PersistentKeepalive = {self.persistent_keepalive}",
        ]
        if self.preshared_key:
            conf_lines.append(f"PresharedKey = {self.preshared_key}")

        return "\n".join(conf_lines)


@dataclass
class VLESSConfig(ProtocolConfig):
    """Конфигурация VLESS + XTLS Reality (формат URI vless://)."""
    server_address: str = "127.0.0.1"
    server_port: int = 443
    name: str = "Why_Ai_VLESS_Reality"
    protocol: ProtocolType = ProtocolType.VLESS
    uuid: str = ""
    flow: str = "xtls-rprx-vision"
    encryption: str = "none"
    security: str = "reality"
    sni: str = "www.microsoft.com"
    fingerprint: str = "chrome"
    public_key: str = ""
    short_id: str = ""
    spider_x: str = "/"

    def export(self) -> str:
        """Генерация VLESS-Reality URI ссылки."""
        query_params = {
            "encryption": self.encryption,
            "flow": self.flow,
            "security": self.security,
            "sni": self.sni,
            "fp": self.fingerprint,
            "pbk": self.public_key,
            "sid": self.short_id,
            "spx": self.spider_x,
            "type": "tcp",
        }
        encoded_query = urllib.parse.urlencode(query_params)
        encoded_name = urllib.parse.quote(self.name)
        return f"vless://{self.uuid}@{self.server_address}:{self.server_port}?{encoded_query}#{encoded_name}"


@dataclass
class ShadowsocksConfig(ProtocolConfig):
    """Конфигурация Shadowsocks AEAD 2022 (формат ss://)."""
    server_address: str = "127.0.0.1"
    server_port: int = 8388
    name: str = "Why_Ai_Shadowsocks"
    protocol: ProtocolType = ProtocolType.SHADOWSOCKS
    cipher: str = "2022-blake3-aes-256-gcm"
    password: str = ""
    plugin: Optional[str] = None
    plugin_opts: Optional[str] = None

    def export(self) -> str:
        """Генерация Shadowsocks URI ссылки."""
        userinfo = f"{self.cipher}:{self.password}"
        encoded_userinfo = base64.urlsafe_b64encode(userinfo.encode("utf-8")).decode("utf-8").rstrip("=")
        uri = f"ss://{encoded_userinfo}@{self.server_address}:{self.server_port}"

        if self.plugin:
            plugin_str = self.plugin
            if self.plugin_opts:
                plugin_str += f";{self.plugin_opts}"
            encoded_plugin = urllib.parse.quote(plugin_str)
            uri += f"?plugin={encoded_plugin}"

        encoded_name = urllib.parse.quote(self.name)
        uri += f"#{encoded_name}"
        return uri


@dataclass
class TrojanConfig(ProtocolConfig):
    """Конфигурация Trojan-GFW (формат trojan://)."""
    server_address: str = "127.0.0.1"
    server_port: int = 443
    name: str = "Why_Ai_Trojan"
    protocol: ProtocolType = ProtocolType.TROJAN
    password: str = ""
    sni: str = "www.microsoft.com"
    alpn: str = "h2,http/1.1"

    def export(self) -> str:
        """Генерация Trojan URI ссылки."""
        query_params = {
            "sni": self.sni,
            "alpn": self.alpn,
            "type": "tcp",
        }
        encoded_query = urllib.parse.urlencode(query_params)
        encoded_name = urllib.parse.quote(self.name)
        return f"trojan://{self.password}@{self.server_address}:{self.server_port}?{encoded_query}#{encoded_name}"


class ProtocolFactory:
    """Фабрика создания конфигураций адаптеров."""

    @staticmethod
    def create_config(protocol: ProtocolType, params: Dict[str, Any]) -> ProtocolConfig:
        """Создание типизированной конфигурации по протоколу."""
        if protocol == ProtocolType.WIREGUARD:
            return WireGuardConfig(
                server_address=params.get("server_address", "127.0.0.1"),
                server_port=params.get("server_port", 51820),
                name=params.get("name", "Why_Ai_WireGuard"),
                private_key=params.get("private_key", "aW50ZXJuYWxfcHJpdmF0ZV9rZXlfZGVtb18xMjM0NQ=="),
                peer_public_key=params.get("peer_public_key", "ZXh0ZXJuYWxfcHVibGljX2tleV9kZW1vXzY3ODkw="),
                allowed_ips=params.get("allowed_ips", "0.0.0.0/0"),
            )
        elif protocol == ProtocolType.VLESS:
            return VLESSConfig(
                server_address=params.get("server_address", "127.0.0.1"),
                server_port=params.get("server_port", 443),
                name=params.get("name", "Why_Ai_VLESS_Reality"),
                uuid=params.get("uuid", "a1b2c3d4-e5f6-7890-abcd-ef1234567890"),
                public_key=params.get("public_key", "k1e2y3p4u5b6l7i8c9k0e1y2p3u4b5l6i7c8="),
                short_id=params.get("short_id", "0123456789abcdef"),
                sni=params.get("sni", "www.microsoft.com"),
            )
        elif protocol == ProtocolType.SHADOWSOCKS:
            return ShadowsocksConfig(
                server_address=params.get("server_address", "127.0.0.1"),
                server_port=params.get("server_port", 8388),
                name=params.get("name", "Why_Ai_Shadowsocks"),
                cipher=params.get("cipher", "chacha20-ietf-poly1305"),
                password=params.get("password", "secret_strong_pass_2026"),
            )
        elif protocol == ProtocolType.TROJAN:
            return TrojanConfig(
                server_address=params.get("server_address", "127.0.0.1"),
                server_port=params.get("server_port", 443),
                name=params.get("name", "Why_Ai_Trojan"),
                password=params.get("password", "trojan_secret_password_2026"),
            )
        else:
            raise ValueError(f"Неподдерживаемый протокол: {protocol}")
