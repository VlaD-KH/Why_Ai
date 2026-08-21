#!/usr/bin/env python3
"""
Модуль: Tool/connectors/dvpn_connector.py
Назначение: Модульный FastMCP коннектор к ядру dVPN / Proxy-роутера для управления туннелями, выбора узлов и генерации конфигураций.
Архитектурный слой: Tool (Инфраструктурные коннекторы).
Инвариант: Предоставляет безопасный типизированный RPC интерфейс к ядру dVPN без прямого доступа LLM к сырым сокетам.
"""

import json
import logging
from typing import Dict, Any, List, Optional

try:
    from Core.dvpn.engine import AdaptiveDVPNRouter
    from Core.dvpn.profiles import UserTier
    from Core.dvpn.protocols import ProtocolType
except ImportError:
    from dvpn.engine import AdaptiveDVPNRouter  # type: ignore
    from dvpn.profiles import UserTier  # type: ignore
    from dvpn.protocols import ProtocolType  # type: ignore

logger = logging.getLogger("DVPNConnector")


class DVPNConnector:
    """
    Инфраструктурный коннектор FastMCP для управления dVPN / Proxy ядром.
    """

    def __init__(self, router: Optional[AdaptiveDVPNRouter] = None) -> None:
        self.router = router or AdaptiveDVPNRouter()

    def get_status(self, user_id: str = "default_user") -> Dict[str, Any]:
        """Получение текущего статуса dVPN соединения и метрик узла."""
        return self.router.get_status(user_id=user_id)

    def list_nodes(self, tier: Optional[str] = None, country: Optional[str] = None) -> List[Dict[str, Any]]:
        """Получение списка доступных узлов dVPN с фильтрацией."""
        nodes = self.router.health_prober.list_nodes(tier=tier, country=country)
        return [
            {
                "node_id": n.node_id,
                "name": n.name,
                "country": n.country_code,
                "ip": n.ip_address,
                "protocol": n.protocol,
                "tier_requirement": n.tier_requirement,
                "latency_ms": round(n.ema_latency_ms, 1),
                "status": n.status.value,
                "quality_score": round(n.quality_score, 1),
            }
            for n in nodes
        ]

    def connect_node(
        self,
        user_id: str = "default_user",
        tier: str = "free",
        country: Optional[str] = None,
        protocol: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Установление соединения через выбранный тариф и локацию."""
        tier_enum = UserTier(tier.lower())
        protocol_enum = ProtocolType(protocol.lower()) if protocol else None

        state = self.router.connect(
            user_id=user_id,
            tier=tier_enum,
            country_preference=country,
            preferred_protocol=protocol_enum,
        )

        return {
            "status": "CONNECTED",
            "user_id": user_id,
            "tier": state.tier.value,
            "protocol": state.protocol.value,
            "connected_node": {
                "node_id": state.active_node.node_id,
                "country": state.active_node.country_code,
                "ip": state.active_node.ip_address,
                "latency_ms": state.active_node.latency_ms,
            },
            "kill_switch_active": state.is_kill_switch_engaged,
            "config_preview": state.client_config[:80] + "..." if len(state.client_config) > 80 else state.client_config,
        }

    def switch_tier_profile(self, user_id: str, new_tier: str) -> Dict[str, Any]:
        """Динамическая смена тарифного профиля (Free <-> Premium)."""
        tier_enum = UserTier(new_tier.lower())
        state = self.router.switch_profile(user_id=user_id, new_tier=tier_enum)
        return {
            "status": "TIER_SWITCHED",
            "user_id": user_id,
            "new_tier": state.tier.value,
            "new_node": state.active_node.node_id,
            "protocol": state.protocol.value,
            "kill_switch_active": state.is_kill_switch_engaged,
        }

    def trigger_fallback(self, user_id: str, reason: str = "Manual test fallback") -> Dict[str, Any]:
        """Принудительный запуск Fail-Safe Fallback переключения."""
        state = self.router.trigger_fallback(user_id=user_id, reason=reason)
        return {
            "status": "FALLBACK_SUCCESS",
            "user_id": user_id,
            "active_node": state.active_node.node_id,
            "fallback_count": state.fallback_count,
            "switch_timestamp": state.last_fallback_time,
        }

    def get_client_config(self, user_id: str = "default_user") -> Dict[str, Any]:
        """Экспорт полной конфигурации клиента для активного туннеля."""
        state = self.router.active_connections.get(user_id)
        if not state:
            raise ValueError(f"Пользователь {user_id} не подключен.")

        return {
            "user_id": user_id,
            "protocol": state.protocol.value,
            "node_id": state.active_node.node_id,
            "config_content": state.client_config,
        }
