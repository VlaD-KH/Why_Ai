"""
Пакет: Core/dvpn/
Назначение: Высокопроизводительное адаптивное ядро децентрализованного VPN / Proxy-роутера с поддержкой тарифных профилей и мультипротокольной маршрутизации.
Архитектурный слой: Core (Zone E).
"""

from .profiles import UserTier, TierPolicy, TierManager
from .protocols import ProtocolType, ProtocolConfig, WireGuardConfig, VLESSConfig, ShadowsocksConfig
from .health_prober import DVPNNode, NodeStatus, HealthProber
from .engine import AdaptiveDVPNRouter

__all__ = [
    "UserTier",
    "TierPolicy",
    "TierManager",
    "ProtocolType",
    "ProtocolConfig",
    "WireGuardConfig",
    "VLESSConfig",
    "ShadowsocksConfig",
    "DVPNNode",
    "NodeStatus",
    "HealthProber",
    "AdaptiveDVPNRouter",
]
