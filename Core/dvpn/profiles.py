#!/usr/bin/env python3
"""
Модуль: Core/dvpn/profiles.py
Назначение: Управление тарифными профилями пользователей (Free, Premium, Enterprise), квотами трафика и политиками безопасности.
Архитектурный слой: Core (Zone E).
Инвариант: Пользователи тарифа Free ограничены базовыми узлами и имеют лимиты скорости; Premium имеет приоритетную маршрутизацию и Kill-Switch.
"""

from dataclasses import dataclass, field
from enum import Enum
import logging
import time
from typing import Dict, Any, List, Optional, Set

logger = logging.getLogger("DVPNProfiles")


class UserTier(str, Enum):
    """Градации пользовательских тарифов dVPN платформы."""
    FREE = "free"
    PREMIUM = "premium"
    ENTERPRISE = "enterprise"


@dataclass
class TierPolicy:
    """Конфигурация прав и ограничений тарифного профиля."""
    tier: UserTier
    max_bandwidth_mbps: int
    allowed_protocols: List[str]
    allow_dedicated_relays: bool
    kill_switch_mandatory: bool
    max_active_connections: int
    priority_weight: float
    obfuscation_supported: bool
    quota_bytes_monthly: int  # 0 означает безлимит


TIER_POLICIES: Dict[UserTier, TierPolicy] = {
    UserTier.FREE: TierPolicy(
        tier=UserTier.FREE,
        max_bandwidth_mbps=25,
        allowed_protocols=["wireguard", "shadowsocks"],
        allow_dedicated_relays=False,
        kill_switch_mandatory=False,
        max_active_connections=1,
        priority_weight=1.0,
        obfuscation_supported=False,
        quota_bytes_monthly=10 * 1024 * 1024 * 1024,  # 10 GB
    ),
    UserTier.PREMIUM: TierPolicy(
        tier=UserTier.PREMIUM,
        max_bandwidth_mbps=500,
        allowed_protocols=["wireguard", "vless", "shadowsocks", "trojan"],
        allow_dedicated_relays=True,
        kill_switch_mandatory=True,
        max_active_connections=5,
        priority_weight=5.0,
        obfuscation_supported=True,
        quota_bytes_monthly=0,  # Безлимитный трафик
    ),
    UserTier.ENTERPRISE: TierPolicy(
        tier=UserTier.ENTERPRISE,
        max_bandwidth_mbps=2000,
        allowed_protocols=["wireguard", "vless", "shadowsocks", "trojan", "multihop"],
        allow_dedicated_relays=True,
        kill_switch_mandatory=True,
        max_active_connections=50,
        priority_weight=10.0,
        obfuscation_supported=True,
        quota_bytes_monthly=0,  # Безлимитный трафик
    ),
}


@dataclass
class UserSession:
    """Активная сессия пользователя."""
    user_id: str
    tier: UserTier
    bytes_uploaded: int = 0
    bytes_downloaded: int = 0
    connected_at: float = field(default_factory=time.time)
    active_node_id: Optional[str] = None
    kill_switch_active: bool = False


class TierManager:
    """
    Менеджер тарифных профилей: контроль прав доступа к протоколам и узлам, учет трафика и проверка лимитов.
    """

    def __init__(self) -> None:
        self.sessions: Dict[str, UserSession] = {}
        self.policies = TIER_POLICIES

    def get_policy(self, tier: UserTier) -> TierPolicy:
        """Получение политики тарифа."""
        return self.policies.get(tier, self.policies[UserTier.FREE])

    def create_session(self, user_id: str, tier: UserTier = UserTier.FREE) -> UserSession:
        """Создание или обновление сессии пользователя."""
        policy = self.get_policy(tier)
        session = UserSession(
            user_id=user_id,
            tier=tier,
            kill_switch_active=policy.kill_switch_mandatory,
        )
        self.sessions[user_id] = session
        logger.info(f"Создана сессия для пользователя {user_id} [Тариф: {tier.value}]")
        return session

    def get_session(self, user_id: str) -> Optional[UserSession]:
        """Получение сессии по ID пользователя."""
        return self.sessions.get(user_id)

    def is_protocol_allowed(self, tier: UserTier, protocol: str) -> bool:
        """Проверка, разрешен ли протокол для данного тарифа."""
        policy = self.get_policy(tier)
        return protocol.lower() in policy.allowed_protocols

    def is_node_accessible(self, tier: UserTier, node_tier_requirement: str) -> bool:
        """Проверка доступа к узлу в зависимости от ранга тарифа."""
        req = node_tier_requirement.lower()
        if req == "free":
            return True
        if req == "premium":
            return tier in (UserTier.PREMIUM, UserTier.ENTERPRISE)
        if req == "enterprise":
            return tier == UserTier.ENTERPRISE
        return False

    def record_traffic(self, user_id: str, bytes_up: int, bytes_down: int) -> bool:
        """
        Учет переданного трафика. Возвращает False, если месячная квота превышена (для тарифа Free).
        """
        session = self.sessions.get(user_id)
        if not session:
            session = self.create_session(user_id)

        session.bytes_uploaded += bytes_up
        session.bytes_downloaded += bytes_down

        policy = self.get_policy(session.tier)
        if policy.quota_bytes_monthly > 0:
            total_used = session.bytes_uploaded + session.bytes_downloaded
            if total_used > policy.quota_bytes_monthly:
                logger.warning(f"Пользователь {user_id} превысил месячную квоту {policy.quota_bytes_monthly} байт!")
                return False

        return True

    def switch_tier(self, user_id: str, new_tier: UserTier) -> UserSession:
        """Динамическое переключение тарифа пользователя."""
        session = self.sessions.get(user_id)
        if not session:
            session = self.create_session(user_id, new_tier)
        else:
            session.tier = new_tier
            policy = self.get_policy(new_tier)
            session.kill_switch_active = policy.kill_switch_mandatory

        logger.info(f"Тариф пользователя {user_id} изменен на: {new_tier.value}")
        return session
