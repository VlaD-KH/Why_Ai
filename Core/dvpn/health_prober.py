#!/usr/bin/env python3
"""
Модуль: Core/dvpn/health_prober.py
Назначение: Мониторинг доступности узлов dVPN, расчет EMA-задержки, потерь пакетов и оценка скоринга качества (QoS).
Архитектурный слой: Core (Zone E).
Инвариант: Недоступные или деградировавшие узлы автоматически исключаются из основного пула маршрутизации.
"""

from dataclasses import dataclass, field
from enum import Enum
import logging
import time
from typing import Dict, Any, List, Optional

logger = logging.getLogger("DVPNHealthProber")


class NodeStatus(str, Enum):
    """Статус жизнеспособности узла dVPN."""
    ONLINE = "online"
    DEGRADED = "degraded"
    OFFLINE = "offline"


@dataclass
class DVPNNode:
    """Модель узла децентрализованной сети."""
    node_id: str
    name: str
    country_code: str
    ip_address: str
    port: int
    protocol: str
    tier_requirement: str = "free"  # "free", "premium", "enterprise"
    latency_ms: float = 25.0
    ema_latency_ms: float = 25.0
    packet_loss_pct: float = 0.0
    load_pct: float = 10.0
    uptime_pct: float = 99.9
    status: NodeStatus = NodeStatus.ONLINE
    last_probe_time: float = field(default_factory=time.time)
    consecutive_failures: int = 0

    @property
    def quality_score(self) -> float:
        """
        Расчет интегрального скора качества узла (чем меньше, тем лучше).
        Score = EMA_Latency * 1.0 + PacketLoss% * 15.0 + Load% * 0.5
        """
        if self.status == NodeStatus.OFFLINE:
            return 99999.0
        degradation_penalty = 50.0 if self.status == NodeStatus.DEGRADED else 0.0
        return (self.ema_latency_ms * 1.0) + (self.packet_loss_pct * 15.0) + (self.load_pct * 0.5) + degradation_penalty


class HealthProber:
    """
    Пробер состояния узлов: проводит телеметрические замеры, сглаживает метрики по формуле EMA
    и ранжирует узлы по качеству связи.
    """

    def __init__(self, ema_alpha: float = 0.3) -> None:
        self.ema_alpha = ema_alpha
        self.nodes: Dict[str, DVPNNode] = {}
        self._init_default_nodes()

    def _init_default_nodes(self) -> None:
        """Инициализация эталонных узлов для Free и Premium пулов."""
        defaults = [
            DVPNNode(
                node_id="node-nl-01",
                name="Amsterdam Relay #1",
                country_code="NL",
                ip_address="185.100.85.12",
                port=51820,
                protocol="wireguard",
                tier_requirement="free",
                latency_ms=18.5,
                ema_latency_ms=18.5,
            ),
            DVPNNode(
                node_id="node-de-01",
                name="Frankfurt Dedicated #1",
                country_code="DE",
                ip_address="194.26.29.44",
                port=443,
                protocol="vless",
                tier_requirement="premium",
                latency_ms=14.2,
                ema_latency_ms=14.2,
            ),
            DVPNNode(
                node_id="node-fi-01",
                name="Helsinki High-Speed #1",
                country_code="FI",
                ip_address="95.217.16.88",
                port=443,
                protocol="vless",
                tier_requirement="premium",
                latency_ms=22.1,
                ema_latency_ms=22.1,
            ),
            DVPNNode(
                node_id="node-us-01",
                name="New York Community #1",
                country_code="US",
                ip_address="104.244.72.115",
                port=8388,
                protocol="shadowsocks",
                tier_requirement="free",
                latency_ms=88.4,
                ema_latency_ms=88.4,
            ),
            DVPNNode(
                node_id="node-sg-01",
                name="Singapore Enterprise Relay",
                country_code="SG",
                ip_address="139.180.200.5",
                port=443,
                protocol="trojan",
                tier_requirement="enterprise",
                latency_ms=145.0,
                ema_latency_ms=145.0,
            ),
        ]
        for n in defaults:
            self.nodes[n.node_id] = n

    def register_node(self, node: DVPNNode) -> None:
        """Регистрация нового узла в реестре."""
        self.nodes[node.node_id] = node
        logger.info(f"Зарегистрирован узел dVPN: {node.node_id} ({node.name}, {node.country_code})")

    def remove_node(self, node_id: str) -> bool:
        """Удаление узла из реестра."""
        if node_id in self.nodes:
            del self.nodes[node_id]
            logger.info(f"Узел {node_id} удален из реестра.")
            return True
        return False

    def get_node(self, node_id: str) -> Optional[DVPNNode]:
        """Получение узла по ID."""
        return self.nodes.get(node_id)

    def list_nodes(self, tier: Optional[str] = None, country: Optional[str] = None) -> List[DVPNNode]:
        """Фильтрация узлов по тарифу и стране."""
        result = list(self.nodes.values())
        if tier:
            result = [n for n in result if n.tier_requirement.lower() == tier.lower() or n.tier_requirement == "free"]
        if country:
            result = [n for n in result if n.country_code.upper() == country.upper()]
        return result

    def update_probe_metrics(
        self,
        node_id: str,
        latency_ms: float,
        packet_loss_pct: float = 0.0,
        load_pct: Optional[float] = None,
        is_timeout: bool = False,
    ) -> Optional[DVPNNode]:
        """
        Обновление замеров узла с вычислением EMA и автоматическим обновлением статуса.
        """
        node = self.nodes.get(node_id)
        if not node:
            return None

        node.last_probe_time = time.time()

        if is_timeout:
            node.consecutive_failures += 1
            node.packet_loss_pct = 100.0
            if node.consecutive_failures >= 3:
                node.status = NodeStatus.OFFLINE
            else:
                node.status = NodeStatus.DEGRADED
            logger.warning(f"Таймаут пробинга узла {node_id} (Сбоев подряд: {node.consecutive_failures})")
            return node

        node.consecutive_failures = 0
        node.latency_ms = latency_ms
        # Вычисление EMA: EMA_t = alpha * Y_t + (1 - alpha) * EMA_{t-1}
        node.ema_latency_ms = (self.ema_alpha * latency_ms) + ((1.0 - self.ema_alpha) * node.ema_latency_ms)
        node.packet_loss_pct = packet_loss_pct
        if load_pct is not None:
            node.load_pct = load_pct

        # Определение статуса. Порог OFFLINE проверяется ПЕРВЫМ: диапазон
        # packet_loss_pct > 80.0 является подмножеством > 30.0, поэтому при
        # обратном порядке (DEGRADED-условие первым) ветка OFFLINE была
        # недостижима ни при каком значении.
        if packet_loss_pct > 80.0:
            node.status = NodeStatus.OFFLINE
        elif packet_loss_pct > 30.0 or node.ema_latency_ms > 500.0:
            node.status = NodeStatus.DEGRADED
        else:
            node.status = NodeStatus.ONLINE

        return node

    def get_optimal_nodes(
        self,
        user_tier: str = "free",
        country_preference: Optional[str] = None,
        limit: int = 3,
    ) -> List[DVPNNode]:
        """
        Возвращает топ-N лучших доступных узлов, отсортированных по качеству (Quality Score).
        """
        allowed = []
        for n in self.nodes.values():
            if n.status == NodeStatus.OFFLINE:
                continue

            # Проверка доступности по тарифу
            if user_tier.lower() == "free" and n.tier_requirement != "free":
                continue
            if user_tier.lower() == "premium" and n.tier_requirement == "enterprise":
                continue

            if country_preference and n.country_code.upper() != country_preference.upper():
                continue

            allowed.append(n)

        # Сортировка по минимальному quality_score (лучшие в начале)
        allowed.sort(key=lambda node: node.quality_score)
        return allowed[:limit]
