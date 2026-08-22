#!/usr/bin/env python3
"""
Модуль: Tool/connectors/telegram_bridge.py
Назначение: Мост между демоном Why_Ai (SSE-поток событий, long polling
входящих команд) и Telegram-оператором. Читает уже существующие сигналы
Core/server.py и не требует ни одной правки Supervisor/.
Архитектурный слой: Tool (коннекторы с внешними эффектами), зона R.
Обоснование архитектуры: docs/final_vision/02-architecture.md.

Ограничения контура:
  * stdlib-only — транспорт только `urllib.request`, никаких `httpx`/`requests`.
  * Не полагаемся на автопереподключение библиотек для SSE — цикл
    переподключения ведём сами, с явным экспоненциальным backoff (тот же
    принцип, что уже применён для EventSource в Eye/telegram_mini_app.html).
"""

import json
import logging
import time
import urllib.request
from typing import Any, Callable, Dict, FrozenSet, Iterator, List, Optional, Tuple

try:
    from miniyaml import load_path as _load_yaml_path
except ImportError:
    from Supervisor.miniyaml import load_path as _load_yaml_path

logger = logging.getLogger("TelegramBridge")

DEFAULT_READ_TIMEOUT_SECONDS = 5.0
DEFAULT_INITIAL_BACKOFF_SECONDS = 1.0
DEFAULT_MAX_BACKOFF_SECONDS = 30.0

# Соответствие типов SSE-событий, реально вещаемых Core/server.py:broadcast_event(),
# уровню серьёзности. Совпадает с EVENT_META в Eye/telegram_mini_app.html — одна
# классификация, не две расходящиеся. Старая спецификация постулировала 4 уровня
# (PANIC/CRITICAL/CONSENSUS/SIZE_WARN), из которых через SSE реально идёт только
# PANIC (panic_stop); CRITICAL/CONSENSUS/SIZE_WARN — файловые источники
# (Core/failures.jsonl, QuorumReviewer.review_diff(), antigravity_debug.log),
# не подключённые мостом в этом цикле (см. docs/final_vision/02-architecture.md).
EVENT_SEVERITY: Dict[str, str] = {
    "connected": "ok",
    "panic_stop": "crit",
    "worktrees_pruned": "info",
    "evolution_cycle": "info",
    "mode_changed": "warn",
    "db_synced": "info",
    "dvpn_connected": "ok",
    "dvpn_tier_switched": "info",
    "dvpn_fallback": "warn",
}
DEFAULT_MONITORED_SEVERITIES: FrozenSet[str] = frozenset({"crit", "warn"})


def event_severity(event_type: str) -> str:
    """Серьёзность типа события. Неизвестный тип — "info", не отбрасывается молча."""
    return EVENT_SEVERITY.get(event_type, "info")


def should_forward(event_type: str, monitored_severities: Any) -> bool:
    """Пересылать ли событие оператору при данном наборе отслеживаемых уровней."""
    return event_severity(event_type) in monitored_severities


def load_monitored_severities(config_path: Any) -> FrozenSet[str]:
    """
    Читает tools.telegram_bridge.monitored_severities из why_ai_config.yaml.

    Отсутствие файла, секции или ключа — не ошибка: конфигурация опциональна,
    fallback на DEFAULT_MONITORED_SEVERITIES.
    """
    try:
        conf = _load_yaml_path(str(config_path))
    except (OSError, ValueError):
        return DEFAULT_MONITORED_SEVERITIES

    if not isinstance(conf, dict):
        return DEFAULT_MONITORED_SEVERITIES

    tools = conf.get("tools")
    if not isinstance(tools, dict):
        return DEFAULT_MONITORED_SEVERITIES

    bridge_conf = tools.get("telegram_bridge")
    if not isinstance(bridge_conf, dict):
        return DEFAULT_MONITORED_SEVERITIES

    severities = bridge_conf.get("monitored_severities")
    if not isinstance(severities, list) or not severities:
        return DEFAULT_MONITORED_SEVERITIES

    return frozenset(str(s) for s in severities)

# Тип функции, открывающей поток: (url, timeout) -> объект, итерируемый по
# строкам байт (совместим с http.client.HTTPResponse и с фейками в тестах).
StreamOpener = Callable[[str, float], Any]


def _default_opener(url: str, timeout: float) -> Any:
    request = urllib.request.Request(url, headers={"Accept": "text/event-stream"})
    return urllib.request.urlopen(request, timeout=timeout)


def iter_sse_events(response: Any) -> Iterator[Tuple[str, str]]:
    """
    Разбор потока Server-Sent Events построчно в пары (event_type, raw_data).

    Формат соответствует Core/server.py:broadcast_event() — блок из строк
    `event:`/`data:`, завершающийся пустой строкой; строки-комментарии
    (`: ping`, keep-alive) пропускаются.
    """
    buffer: List[str] = []
    event_type = "message"
    for raw_line in response:
        line = raw_line.decode("utf-8", errors="replace") if isinstance(raw_line, bytes) else str(raw_line)
        line = line.rstrip("\r\n")
        if line == "":
            if buffer:
                yield event_type, "\n".join(buffer)
            buffer = []
            event_type = "message"
            continue
        if line.startswith(":"):
            continue
        if line.startswith("event:"):
            event_type = line[len("event:"):].strip()
        elif line.startswith("data:"):
            buffer.append(line[len("data:"):].strip())
    if buffer:
        yield event_type, "\n".join(buffer)


class SSESubscriber:
    """
    Подписчик на GET /api/events/stream с явным циклом переподключения.

    TASK-TG-07: мост обязан пережить рестарт Core/server.py — демон может
    падать/перезапускаться независимо от моста. Экспоненциальный backoff
    сбрасывается на исходное значение при каждом успешном подключении.
    """

    def __init__(
        self,
        url: str,
        on_event: Callable[[str, Dict[str, Any]], None],
        opener: Optional[StreamOpener] = None,
        read_timeout: float = DEFAULT_READ_TIMEOUT_SECONDS,
        initial_backoff: float = DEFAULT_INITIAL_BACKOFF_SECONDS,
        max_backoff: float = DEFAULT_MAX_BACKOFF_SECONDS,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        self.url = url
        self._on_event = on_event
        self._opener = opener or _default_opener
        self.read_timeout = read_timeout
        self.initial_backoff = initial_backoff
        self.max_backoff = max_backoff
        self._sleep = sleep_fn
        self._stop_requested = False

    def stop(self) -> None:
        """Останавливает run_forever() при следующей проверке (между событиями/переподключениями)."""
        self._stop_requested = True

    def _dispatch(self, event_type: str, raw_data: str) -> None:
        try:
            payload = json.loads(raw_data) if raw_data else {}
        except (json.JSONDecodeError, ValueError):
            payload = {"raw": raw_data}

        # broadcast_event() оборачивает полезную нагрузку в {type,timestamp,data};
        # стартовое сообщение "connected" приходит без обёртки (Core/server.py:243).
        if isinstance(payload, dict) and isinstance(payload.get("data"), dict):
            data: Dict[str, Any] = payload["data"]
        elif isinstance(payload, dict):
            data = payload
        else:
            data = {"raw": payload}

        self._on_event(event_type, data)

    def run_forever(self) -> None:
        """Блокирующий цикл: подключиться, читать события, переподключиться при обрыве."""
        backoff = self.initial_backoff
        while not self._stop_requested:
            try:
                response = self._opener(self.url, self.read_timeout)
                try:
                    backoff = self.initial_backoff
                    for event_type, raw_data in iter_sse_events(response):
                        if self._stop_requested:
                            return
                        self._dispatch(event_type, raw_data)
                finally:
                    close = getattr(response, "close", None)
                    if callable(close):
                        close()
            except Exception as exc:  # noqa: BLE001 - сбой транспорта не должен ронять поток
                if self._stop_requested:
                    return
                logger.warning(
                    "SSE-подписка разорвана (%s: %s), переподключение через %.1f c.",
                    exc.__class__.__name__, exc, backoff,
                )

            if self._stop_requested:
                return
            self._sleep(backoff)
            backoff = min(backoff * 2, self.max_backoff)
