#!/usr/bin/env python3
"""
Модуль: Tool/connectors/telegram_connector.py
Назначение: Модульный коннектор Telegram Bot для внеполосных оповещений операторов, уведомлений о /panic, кворуме и диспетчеризации команд.
Архитектурный слой: Tool (Инфраструктурные коннекторы).
Инвариант: Внеполосная доставка критических сигналов безопасности дежурным администраторам в обход LLM-контекста.

Ограничения контура:
  * stdlib-only — транспорт только `urllib.request`, никаких `httpx`/`requests`.
  * Принцип 14 BIBLE — токен читается из окружения и никогда не попадает в лог,
    в возвращаемый словарь или в текст сообщения.
  * Принцип 15 BIBLE — `delivered: True` выставляется ТОЛЬКО после фактической
    проверки HTTP-статуса и поля `ok` в ответе Bot API.
  * Fail-closed — пустой или незаданный список операторов отклоняет любую
    входящую команду, включая `/panic`.
"""

import json
import logging
import os
import re
import socket
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("TelegramConnector")

DEFAULT_API_BASE = "https://api.telegram.org"
DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_TOKEN_ENV = "TELEGRAM_BOT_TOKEN"
OPERATORS_ENV_VAR = "WHY_AI_TELEGRAM_OPERATORS"

# Символы, которые Bot API требует экранировать в режиме MarkdownV2.
# Обратный слэш включён дополнительно: без него текст, содержащий '\',
# порождает ошибку разбора сущностей на стороне Telegram.
MARKDOWN_V2_SPECIALS = frozenset("_*[]()~`>#+-=|{}.!\\")

REDACTED = "***REDACTED***"
MAX_ERROR_DETAIL = 300

# Транспорт: (url, тело запроса, таймаут) -> (HTTP-статус, тело ответа)
Transport = Callable[[str, bytes, float], Tuple[int, bytes]]

_ROOT_DIR = Path(__file__).resolve().parents[2]
_TESTS_DIR = _ROOT_DIR / "tests"
_BIBLE_FILE = _ROOT_DIR / "Supervisor" / "Constitution" / "BIBLE.md"
_TEST_DEF_RE = re.compile(r"^[ \t]*def " + r"test_[A-Za-z0-9_]*\s*\(", re.MULTILINE)
_BIBLE_PRINCIPLE_RE = re.compile(r"^#{2,4}\s*Принцип\s+\d+", re.MULTILINE)

DENIED_REPLY = (
    "⛔ Доступ запрещён. Команда НЕ выполнена: отправитель не входит в список "
    "операторов Why_Ai. Обратитесь к владельцу контура."
)


def escape_markdown_v2(text: Any) -> str:
    """
    Экранирование текста для parse_mode=MarkdownV2 (TASK-TG-04).

    Проход посимвольный, поэтому порядок обработки спецсимволов не важен и
    обратный слэш не удваивается повторно.
    """
    chunks: List[str] = []
    for char in str(text):
        if char in MARKDOWN_V2_SPECIALS:
            chunks.append("\\")
        chunks.append(char)
    return "".join(chunks)


def _urllib_transport(url: str, data: bytes, timeout: float) -> Tuple[int, bytes]:
    """
    Транспорт по умолчанию: POST через stdlib `urllib.request` с явным таймаутом.

    Не-2xx ответы возвращаются как обычный результат, а не как исключение, чтобы
    вызывающий код обязан был проверить статус (Принцип 15 BIBLE).
    URL содержит токен и поэтому НИКОГДА не логируется здесь.
    """
    request = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json",
            "User-Agent": "Why_Ai-TelegramConnector/1.0",
        },
    )
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


class TelegramConnector:
    """
    Инфраструктурный коннектор к Telegram Bot API для внеполосной диспетчеризации алертов и ручного управления.
    """

    def __init__(
        self,
        bot_token_env: str = DEFAULT_TOKEN_ENV,
        operators_env: str = OPERATORS_ENV_VAR,
        api_base: str = DEFAULT_API_BASE,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        transport: Optional[Transport] = None,
    ) -> None:
        self.bot_token_env = bot_token_env
        self.operators_env = operators_env
        self.api_base = api_base.rstrip("/")
        self.timeout = float(timeout)
        self._transport: Transport = transport or _urllib_transport

    # ------------------------------------------------------------------
    # Секреты (TASK-TG-02, Принцип 14 BIBLE)
    # ------------------------------------------------------------------
    def _resolve_token(self) -> Optional[str]:
        """Токен строго из окружения; пустая строка равнозначна отсутствию."""
        token = (os.getenv(self.bot_token_env) or "").strip()
        return token or None

    @staticmethod
    def _redact(value: Any, token: Optional[str]) -> str:
        """Вычистить токен из произвольного текста перед логом или возвратом."""
        text = str(value)
        if token:
            text = text.replace(token, REDACTED)
        if len(text) > MAX_ERROR_DETAIL:
            text = text[:MAX_ERROR_DETAIL] + "…"
        return text

    # ------------------------------------------------------------------
    # Авторизация операторов (TASK-TG-03) — fail-closed
    # ------------------------------------------------------------------
    def load_operators(self) -> List[str]:
        """Список операторов из ENV. Никогда не читается из репозитория."""
        raw = os.getenv(self.operators_env) or ""
        return [part.strip() for part in raw.split(",") if part.strip()]

    def is_authorized(self, user_id: Optional[Any]) -> Tuple[bool, str]:
        """
        Проверка права отправителя на управляющие команды.

        Отказ по умолчанию: если переменная окружения не задана или список пуст,
        отклоняется ВСЁ, включая `/panic`.
        """
        operators = self.load_operators()
        if not operators:
            return False, "NO_OPERATORS_CONFIGURED"
        if user_id is None:
            return False, "MISSING_USER_ID"
        normalized = str(user_id).strip()
        if not normalized:
            return False, "MISSING_USER_ID"
        if normalized not in operators:
            return False, "USER_NOT_AUTHORIZED"
        return True, "AUTHORIZED"

    # ------------------------------------------------------------------
    # Доставка (TASK-TG-01)
    # ------------------------------------------------------------------
    def _failure(
        self,
        chat_id: str,
        priority: str,
        parse_mode: str,
        error: str,
        detail: str,
        http_status: Optional[int],
    ) -> Dict[str, Any]:
        return {
            "status": "FAILED",
            "message_id": None,
            "chat_id": chat_id,
            "priority": priority,
            "parse_mode": parse_mode,
            "delivered": False,
            "http_status": http_status,
            "error": error,
            "error_detail": detail,
            "timestamp": time.time(),
        }

    def send_alert(
        self,
        chat_id: str,
        message: str,
        priority: str = "INFO",
        parse_mode: str = "MarkdownV2",
        escape: bool = True,
    ) -> Dict[str, Any]:
        """
        Отправка структурированного оповещения в Telegram через POST /sendMessage.

        Возвращает `delivered: True` только если HTTP-статус 2xx И Bot API ответил
        `ok: true`. Любой другой исход — `delivered: False` с указанием причины.
        """
        clean_chat = str(chat_id).strip()
        if not clean_chat or not message:
            raise ValueError("Параметры 'chat_id' и 'message' обязательны для отправки алерта.")

        priority_up = str(priority).upper()
        text = escape_markdown_v2(message) if (escape and parse_mode == "MarkdownV2") else str(message)

        token = self._resolve_token()
        if token is None:
            logger.error(
                "Telegram alert НЕ отправлен [priority=%s, chat=%s]: переменная окружения %s "
                "не задана или пуста. Учётные данные отсутствуют — доставка отклонена.",
                priority_up, clean_chat, self.bot_token_env,
            )
            return self._failure(
                clean_chat, priority_up, parse_mode, "MISSING_TOKEN",
                f"Переменная окружения {self.bot_token_env} не задана или пуста.", None,
            )

        url = f"{self.api_base}/bot{token}/sendMessage"
        payload = {
            "chat_id": clean_chat,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

        try:
            http_status, raw_body = self._transport(url, data, self.timeout)
        except Exception as exc:  # noqa: BLE001 - сбой транспорта не должен ронять процесс
            error_code = "TIMEOUT" if self._is_timeout(exc) else "TRANSPORT_ERROR"
            detail = self._redact(exc, token) or exc.__class__.__name__
            logger.error(
                "Telegram alert НЕ доставлен [priority=%s, chat=%s]: %s (%s), таймаут=%.1f c.",
                priority_up, clean_chat, error_code, detail, self.timeout,
            )
            return self._failure(clean_chat, priority_up, parse_mode, error_code, detail, None)

        if not 200 <= int(http_status) < 300:
            detail = self._redact(self._decode_description(raw_body) or raw_body[:MAX_ERROR_DETAIL], token)
            logger.error(
                "Telegram alert НЕ доставлен [priority=%s, chat=%s]: HTTP %s — %s",
                priority_up, clean_chat, http_status, detail,
            )
            return self._failure(
                clean_chat, priority_up, parse_mode, "HTTP_ERROR", detail or f"HTTP {http_status}", int(http_status),
            )

        try:
            body = json.loads(raw_body.decode("utf-8"))
        except Exception as exc:  # noqa: BLE001 - ответ не является JSON
            detail = self._redact(f"Ответ Bot API не разобран как JSON: {exc}", token)
            logger.error(
                "Telegram alert НЕ доставлен [priority=%s, chat=%s]: %s", priority_up, clean_chat, detail,
            )
            return self._failure(
                clean_chat, priority_up, parse_mode, "BAD_RESPONSE", detail, int(http_status),
            )

        if not isinstance(body, dict) or body.get("ok") is not True:
            detail = self._redact(
                (isinstance(body, dict) and body.get("description")) or f"Bot API вернул ok={body!r}", token,
            )
            logger.error(
                "Telegram alert НЕ доставлен [priority=%s, chat=%s]: отказ Bot API — %s",
                priority_up, clean_chat, detail,
            )
            return self._failure(
                clean_chat, priority_up, parse_mode, "API_ERROR", detail, int(http_status),
            )

        result = body.get("result") if isinstance(body.get("result"), dict) else {}
        message_id = result.get("message_id")
        logger.info(
            "Telegram alert доставлен [priority=%s, chat=%s, message_id=%s, http=%s]",
            priority_up, clean_chat, message_id, http_status,
        )
        return {
            "status": "SENT",
            "message_id": message_id,
            "chat_id": clean_chat,
            "priority": priority_up,
            "parse_mode": parse_mode,
            "delivered": True,
            "http_status": int(http_status),
            "timestamp": time.time(),
        }

    @staticmethod
    def _is_timeout(exc: BaseException) -> bool:
        if isinstance(exc, (socket.timeout, TimeoutError)):
            return True
        reason = getattr(exc, "reason", None)
        return isinstance(reason, (socket.timeout, TimeoutError))

    @staticmethod
    def _decode_description(raw_body: bytes) -> str:
        try:
            parsed = json.loads(raw_body.decode("utf-8"))
        except Exception:  # noqa: BLE001 - тело не JSON
            return ""
        if isinstance(parsed, dict) and parsed.get("description"):
            return str(parsed["description"])
        return ""

    def send_panic_notification(self, exit_code: int = 10, reason: str = "Emergency /panic triggered") -> Dict[str, Any]:
        """
        Срочное оповещение о внеполосном останове системы /panic.
        Разметка статична, динамические поля экранируются точечно.
        """
        alert_body = (
            "🚨 *CRITICAL OUT\\-OF\\-BAND PANIC STOP*\n"
            f"• *Exit Code:* `{escape_markdown_v2(exit_code)}` \\(REQUIRE\\_HUMAN\\)\n"
            f"• *Reason:* {escape_markdown_v2(reason)}\n"
            "• *Action:* Все дочерние процессы агента немедленно остановлены Supervisor\\."
        )
        return self.send_alert(
            chat_id="@why_ai_secops", message=alert_body, priority="CRITICAL", escape=False,
        )

    def send_quorum_verdict(self, diff_sha: str, verdict: str, veto_reasons: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Оповещение о результатах мультимодельного кворума Why_Ai Multi-Harness Engine.
        """
        vetoes = veto_reasons or []
        icon = "✅" if verdict == "APPROVED" else "❌"
        msg = (
            f"{icon} *Why\\_Ai Quorum Verdict: {escape_markdown_v2(verdict)}*\n"
            f"• *Diff SHA\\-256:* `{escape_markdown_v2(str(diff_sha)[:16])}`\n"
            f"• *Angle Diversity Vetoes:* {len(vetoes)}\n"
        )
        if vetoes:
            msg += f"• *Veto Reason:* {escape_markdown_v2(vetoes[0])}\n"

        return self.send_alert(
            chat_id="@why_ai_dev",
            message=msg,
            priority="WARNING" if vetoes else "INFO",
            escape=False,
        )

    # ------------------------------------------------------------------
    # Фактические счётчики вместо констант (TASK-TG-05)
    # ------------------------------------------------------------------
    @staticmethod
    def count_repository_tests() -> int:
        """Фактическое число тестовых методов в tests/ (статический подсчёт, без импорта)."""
        total = 0
        try:
            for path in sorted(_TESTS_DIR.glob("test_*.py")):
                total += len(_TEST_DEF_RE.findall(path.read_text(encoding="utf-8", errors="replace")))
        except Exception as exc:  # noqa: BLE001 - /status не должен падать из-за файлов
            logger.warning("Не удалось пересчитать тесты в %s: %s", _TESTS_DIR, exc)
        return total

    @staticmethod
    def count_bible_principles() -> int:
        """Фактическое число принципов Конституции в BIBLE.md."""
        try:
            return len(_BIBLE_PRINCIPLE_RE.findall(_BIBLE_FILE.read_text(encoding="utf-8", errors="replace")))
        except Exception as exc:  # noqa: BLE001 - /status не должен падать из-за файлов
            logger.warning("Не удалось прочитать %s: %s", _BIBLE_FILE, exc)
            return 0

    def _status_reply(self) -> str:
        """
        Ответ на /status. Числа считаются фактически: захардкоженные счётчики
        тестов и инвариантов лгали и удалены (TASK-TG-05). Слово PASS не
        используется — тесты здесь не запускаются, а только перечисляются.
        """
        return (
            "⚡ Why_Ai Control Plane: RUNNING"
            f" • Тестов в репозитории: {self.count_repository_tests()}"
            f" • Принципов BIBLE.md: {self.count_bible_principles()}"
        )

    # ------------------------------------------------------------------
    # Входящие команды (TASK-TG-03)
    # ------------------------------------------------------------------
    def handle_incoming_command(self, command: str, user_id: Optional[Any]) -> Dict[str, Any]:
        """
        Обработка операторских команд ручного управления с телефона через Telegram.
        Поддерживаемые команды: /bg status, /evolve off, /evolve on, /panic, /mode [self_evo|prod_evo].

        `user_id` обязателен позиционно: забыть его нельзя, а значение None
        трактуется как отсутствие отправителя и отклоняется.
        """
        clean_cmd = str(command).strip().lower()

        authorized, reason = self.is_authorized(user_id)
        if not authorized:
            shown_id = "<none>" if user_id is None else (str(user_id).strip() or "<empty>")
            logger.warning(
                "ОТКАЗ Telegram-команде '%s': user_id=%s, причина=%s, операторов в %s: %d",
                clean_cmd, shown_id, reason, self.operators_env, len(self.load_operators()),
            )
            return {
                "command": clean_cmd,
                "action": "DENIED",
                "authorized": False,
                "reason": reason,
                "user_id": shown_id,
                "reply": DENIED_REPLY,
            }

        if clean_cmd == "/panic":
            return {
                "command": "/panic",
                "action": "TRIGGER_PANIC",
                "authorized": True,
                "exit_code": 10,
                "reply": "🚨 Внеполосный сигнал /panic принят. Supervisor завершает процессы.",
            }
        elif clean_cmd in ("/bg status", "/status"):
            return {
                "command": "/status",
                "action": "GET_STATUS",
                "authorized": True,
                "reply": self._status_reply(),
            }
        elif clean_cmd == "/evolve off":
            return {
                "command": "/evolve off",
                "action": "DISABLE_BACKGROUND_EVO",
                "authorized": True,
                "reply": "⏸️ Фоновое самосознание временно приостановлено.",
            }
        elif clean_cmd == "/evolve on":
            return {
                "command": "/evolve on",
                "action": "ENABLE_BACKGROUND_EVO",
                "authorized": True,
                "reply": "▶️ Фоновое самосознание активировано (Tick: 300s, Idempotency Gate: Active).",
            }
        elif clean_cmd.startswith("/mode"):
            parts = clean_cmd.split()
            if len(parts) >= 2:
                mode = parts[1]
                return {
                    "command": clean_cmd,
                    "action": "SWITCH_MODE",
                    "authorized": True,
                    "target_mode": mode,
                    "reply": f"🔄 Топология переключена на режим [{mode}].",
                }

        return {
            "command": clean_cmd,
            "action": "UNKNOWN",
            "authorized": True,
            "reply": f"❓ Неизвестная команда '{command}'. Доступно: /status, /panic, /evolve [on|off], /mode [self_evo|prod_evo]",
        }
