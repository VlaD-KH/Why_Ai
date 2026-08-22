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
import urllib.error
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


# Тип функции для простых GET/POST-вызовов: (url, timeout) -> (http_status, body_bytes).
# Не-2xx возвращается как обычный результат, а не исключение — вызывающий код
# обязан проверить статус (тот же контракт, что _urllib_transport в
# telegram_connector.py, Принцип 15 BIBLE).
HttpCall = Callable[[str, float], Tuple[int, bytes]]

DEFAULT_POLL_TIMEOUT_SECONDS = 25.0


def _urlopen_status_body(request: urllib.request.Request, timeout: float) -> Tuple[int, bytes]:
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = int(getattr(response, "status", None) or getattr(response, "code", None) or 0)
            return status, response.read()
    except urllib.error.HTTPError as http_error:
        try:
            body = http_error.read()
        except Exception:  # pragma: no cover - тело недоступно
            body = b""
        return int(http_error.code), body


def _default_get(url: str, timeout: float) -> Tuple[int, bytes]:
    return _urlopen_status_body(urllib.request.Request(url, method="GET"), timeout)


def _default_post(url: str, timeout: float) -> Tuple[int, bytes]:
    return _urlopen_status_body(urllib.request.Request(url, method="POST", data=b""), timeout)


class TelegramUpdatesPoller:
    """
    TASK-TG-09: входящие команды через long polling `getUpdates`.

    Не `setWebhook` — не требует публичного HTTPS-эндпоинта (решение 3,
    docs/final_vision/02-architecture.md). Логика авторизации и
    диспетчеризации команд не дублируется здесь — она уже есть и покрыта
    тестами в TelegramConnector.handle_incoming_command(); поллер только
    извлекает command/user_id/chat_id из апдейта и передаёт их дальше через
    on_command.
    """

    def __init__(
        self,
        token: str,
        on_command: Callable[[str, Optional[Any], Optional[Any]], None],
        opener: Optional[HttpCall] = None,
        api_base: str = "https://api.telegram.org",
        poll_timeout: float = DEFAULT_POLL_TIMEOUT_SECONDS,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        self._token = token
        self._on_command = on_command
        self._opener = opener or _default_get
        self._api_base = api_base.rstrip("/")
        self._poll_timeout = poll_timeout
        self._sleep = sleep_fn
        self._offset: Optional[int] = None
        self._stop_requested = False

    def stop(self) -> None:
        self._stop_requested = True

    def poll_once(self) -> None:
        """Один цикл getUpdates. Публичный метод — детерминированно тестируется без run_forever()."""
        url = f"{self._api_base}/bot{self._token}/getUpdates?timeout={int(self._poll_timeout)}"
        if self._offset is not None:
            url += f"&offset={self._offset}"

        try:
            status, body = self._opener(url, self._poll_timeout + 5.0)
        except Exception as exc:  # noqa: BLE001 - сбой транспорта не должен ронять цикл
            logger.warning("getUpdates: сбой транспорта (%s)", exc.__class__.__name__)
            return

        if status != 200:
            logger.warning("getUpdates: HTTP %s", status)
            return

        try:
            payload = json.loads(body.decode("utf-8"))
        except (json.JSONDecodeError, ValueError, UnicodeDecodeError):
            logger.warning("getUpdates: ответ не разобран как JSON")
            return

        if not isinstance(payload, dict) or not payload.get("ok"):
            logger.warning("getUpdates: Bot API вернул ok=false")
            return

        for update in payload.get("result", []):
            update_id = update.get("update_id")
            if isinstance(update_id, int):
                self._offset = update_id + 1

            message = update.get("message") or {}
            text = str(message.get("text", "")).strip()
            if not text:
                continue

            from_user = message.get("from") or {}
            chat = message.get("chat") or {}
            self._on_command(text, from_user.get("id"), chat.get("id"))

    def run_forever(self) -> None:
        while not self._stop_requested:
            self.poll_once()
            if self._stop_requested:
                return


def dispatch_action(
    action_result: Dict[str, Any],
    backend_base_url: str,
    opener: Optional[HttpCall] = None,
) -> str:
    """
    TASK-TG-10/TG-11: выполняет реальный вызов бэкенда для действия,
    возвращённого TelegramConnector.handle_incoming_command(), и строит
    ответ оператору на основе ФАКТИЧЕСКОГО результата.

    Анти-критерий (TASK-TG-10, главный): успех НИКОГДА не сообщается по
    факту отправки запроса — только по факту 2xx-ответа бэкенда. При
    отказе транспорта или не-2xx статусе оператор получает явное
    предупреждение, что действие могло не выполниться.
    """
    opener = opener or _default_post
    action = action_result.get("action")
    base = backend_base_url.rstrip("/")

    if action == "TRIGGER_PANIC":
        try:
            status, _body = opener(f"{base}/api/panic", 10.0)
        except Exception as exc:  # noqa: BLE001
            return (
                f"⚠️ /panic НЕ подтверждён: сбой транспорта ({exc.__class__.__name__}). "
                "Система, возможно, НЕ остановлена — проверьте вручную."
            )
        if not (200 <= status < 300):
            return (
                f"⚠️ /panic НЕ подтверждён бэкендом: HTTP {status}. "
                "Система, возможно, НЕ остановлена — проверьте вручную."
            )
        return "🚨 /panic подтверждён бэкендом. Supervisor остановил процессы (Exit Code 10)."

    if action == "GET_STATUS":
        try:
            status, body = opener(f"{base}/api/status", 10.0)
        except Exception as exc:  # noqa: BLE001
            return f"⚠️ Не удалось получить статус: сбой транспорта ({exc.__class__.__name__})."
        if not (200 <= status < 300):
            return f"⚠️ Не удалось получить статус: HTTP {status}."
        try:
            data = json.loads(body.decode("utf-8"))
        except (json.JSONDecodeError, ValueError, UnicodeDecodeError):
            return "⚠️ Бэкенд ответил не-JSON на /api/status."
        return (
            f"⚡ Why_Ai: {data.get('status', '?')} · v{data.get('version', '?')} "
            f"· workspace: {data.get('workspace_root', '?')}"
        )

    # Прочие действия (ENABLE/DISABLE_BACKGROUND_EVO, SWITCH_MODE, DENIED,
    # UNKNOWN) не имеют реального бэкенд-вызова в этой области задач — не
    # подделываем успех, которого не проверяли, просто передаём готовый reply.
    return str(action_result.get("reply", ""))
