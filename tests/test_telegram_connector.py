#!/usr/bin/env python3
"""
Модуль: tests/test_telegram_connector.py
Назначение: Фальсифицирующие тесты фазы 1 Telegram-интеграции (TASK-TG-01..06).
Архитектурный слой: Tests (Зона T).
Инвариант: Ни один тест не должен проходить против заглушки, возвращающей константу.

Каждый тест здесь наблюдался падающим до появления реализации (Принцип 7 BIBLE,
Proof of Falsification). Сетевой доступ не используется: транспорт инъецируется,
а путь по умолчанию проверяется подменой urllib.request.urlopen.
"""

import contextlib
import inspect
import io
import json
import logging
import os
import re
import socket
import sys
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from unittest import mock

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
if str(ROOT_DIR / "Tool") not in sys.path:
    sys.path.insert(0, str(ROOT_DIR / "Tool"))

from Tool.connectors import telegram_connector as tg
from Tool.connectors.telegram_connector import TelegramConnector, escape_markdown_v2

TOKEN_ENV = "TELEGRAM_BOT_TOKEN"
OPERATORS_ENV = "WHY_AI_TELEGRAM_OPERATORS"

# Заведомо фиктивное значение. Намеренно НЕ повторяет формат '<digits>:<base64>'
# настоящего токена Bot API, чтобы не порождать ложных срабатываний сканеров
# секретов в публичном репозитории.
FAKE_TOKEN = "TEST-ONLY-NOT-A-REAL-TELEGRAM-BOT-TOKEN"


@contextlib.contextmanager
def env_vars(**overrides: Optional[str]):
    """Временная подмена переменных окружения. None означает 'удалить переменную'."""
    saved: Dict[str, Optional[str]] = {}
    try:
        for key, value in overrides.items():
            saved[key] = os.environ.get(key)
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        yield
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


class RecordingTransport:
    """
    Тестовый транспорт с контрактом (url, data: bytes, timeout: float) -> (status, body: bytes).
    Записывает всё, что коннектор фактически пытался отправить.
    """

    def __init__(
        self,
        status: int = 200,
        body: Optional[Dict[str, Any]] = None,
        raw_body: Optional[bytes] = None,
        raises: Optional[BaseException] = None,
    ) -> None:
        self.calls: List[Dict[str, Any]] = []
        self.status = status
        self.raw_body = raw_body
        self.body = body if body is not None else {"ok": True, "result": {"message_id": 4242}}
        self.raises = raises

    def __call__(self, url: str, data: bytes, timeout: float) -> Tuple[int, bytes]:
        payload: Any
        try:
            payload = json.loads(data.decode("utf-8"))
        except Exception:  # pragma: no cover - защита от нечитаемого тела
            payload = None
        self.calls.append({"url": url, "data": data, "timeout": timeout, "payload": payload})
        if self.raises is not None:
            raise self.raises
        if self.raw_body is not None:
            return self.status, self.raw_body
        return self.status, json.dumps(self.body).encode("utf-8")

    @property
    def last_payload(self) -> Dict[str, Any]:
        return self.calls[-1]["payload"]


def make_connector(transport: Any = None, timeout: float = 3.0) -> TelegramConnector:
    return TelegramConnector(transport=transport, timeout=timeout)


# ======================================================================
# TASK-TG-04 — экранирование MarkdownV2 (проверяется РЕЗУЛЬТАТ)
# ======================================================================
class TestMarkdownV2Escaping(unittest.TestCase):

    def test_escapes_every_reserved_character(self):
        raw = "_*[]()~`>#+-=|{}.!"
        # Ожидаемая строка выписана литералом, а не вычислена тем же алгоритмом,
        # что и реализация — иначе тест был бы тавтологией.
        expected = r"\_\*\[\]\(\)\~\`\>\#\+\-\=\|\{\}\.\!"
        self.assertEqual(escape_markdown_v2(raw), expected)

    def test_escapes_backslash(self):
        self.assertEqual(escape_markdown_v2("C:\\path"), r"C:\\path")

    def test_realistic_message_escaped_exactly(self):
        raw = "Build failed: v1.2.3-rc1 (see report [here])"
        expected = r"Build failed: v1\.2\.3\-rc1 \(see report \[here\]\)"
        self.assertEqual(escape_markdown_v2(raw), expected)

    def test_plain_text_is_not_modified(self):
        self.assertEqual(escape_markdown_v2("Vse horosho 123"), "Vse horosho 123")

    def test_escaped_text_is_what_reaches_the_wire(self):
        transport = RecordingTransport()
        connector = make_connector(transport)
        with env_vars(**{TOKEN_ENV: FAKE_TOKEN}):
            connector.send_alert(chat_id="12345", message="Build failed: v1.2.3-rc1 (see report [here])")
        self.assertEqual(len(transport.calls), 1)
        self.assertEqual(
            transport.last_payload["text"],
            r"Build failed: v1\.2\.3\-rc1 \(see report \[here\]\)",
        )
        self.assertEqual(transport.last_payload["parse_mode"], "MarkdownV2")


# ======================================================================
# TASK-TG-01 — реальный транспорт и успешная доставка
# ======================================================================
class TestSendAlertSuccess(unittest.TestCase):

    def test_successful_delivery_uses_message_id_from_api(self):
        transport = RecordingTransport(status=200, body={"ok": True, "result": {"message_id": 987654}})
        connector = make_connector(transport)
        with env_vars(**{TOKEN_ENV: FAKE_TOKEN}):
            result = connector.send_alert(chat_id="12345", message="ok", priority="info")
        self.assertTrue(result["delivered"])
        self.assertEqual(result["status"], "SENT")
        self.assertEqual(result["message_id"], 987654)
        self.assertEqual(result["http_status"], 200)
        self.assertEqual(result["priority"], "INFO")
        self.assertEqual(result["chat_id"], "12345")

    def test_posts_to_sendmessage_endpoint_with_payload(self):
        transport = RecordingTransport()
        connector = make_connector(transport)
        with env_vars(**{TOKEN_ENV: FAKE_TOKEN}):
            connector.send_alert(chat_id=" @why_ai_ops ", message="hello")
        call = transport.calls[0]
        self.assertTrue(call["url"].endswith("/sendMessage"), call["url"])
        self.assertIn("/bot", call["url"])
        self.assertEqual(call["payload"]["chat_id"], "@why_ai_ops")
        self.assertEqual(call["payload"]["text"], "hello")
        self.assertGreater(call["timeout"], 0)

    def test_default_transport_actually_calls_urllib_urlopen(self):
        """
        Ключевой тест против заглушки: коннектор БЕЗ инъекции транспорта обязан
        выполнить реальный HTTP-вызов через stdlib urllib.request.
        """
        captured: Dict[str, Any] = {}

        class FakeResponse(io.BytesIO):
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                self.close()
                return False

        def fake_urlopen(request, timeout=None, **kwargs):
            captured["request"] = request
            captured["timeout"] = timeout
            return FakeResponse(json.dumps({"ok": True, "result": {"message_id": 7}}).encode("utf-8"))

        connector = TelegramConnector(timeout=4.5)  # транспорт по умолчанию
        with env_vars(**{TOKEN_ENV: FAKE_TOKEN}):
            with mock.patch.object(urllib.request, "urlopen", fake_urlopen):
                result = connector.send_alert(chat_id="12345", message="ping")

        self.assertIn("request", captured, "urllib.request.urlopen не был вызван вообще")
        request = captured["request"]
        self.assertIsInstance(request, urllib.request.Request)
        self.assertEqual(request.get_method(), "POST")
        self.assertTrue(request.full_url.endswith("/sendMessage"), request.full_url)
        self.assertTrue(request.full_url.startswith("https://api.telegram.org/bot"), request.full_url)
        self.assertIsNotNone(request.data)
        self.assertEqual(json.loads(request.data.decode("utf-8"))["chat_id"], "12345")
        self.assertIn("json", (request.get_header("Content-type") or "").lower())
        # TASK-TG-01: таймаут задан явно и передан в urlopen.
        self.assertEqual(captured["timeout"], 4.5)
        self.assertTrue(result["delivered"])
        self.assertEqual(result["message_id"], 7)

    def test_module_does_not_import_third_party_http_clients(self):
        source = Path(tg.__file__).read_text(encoding="utf-8")
        for forbidden in ("httpx", "requests"):
            self.assertIsNone(
                re.search(r"^\s*(?:import|from)\s+%s\b" % forbidden, source, re.MULTILINE),
                f"Обнаружен сторонний импорт {forbidden}: проект stdlib-only",
            )


# ======================================================================
# TASK-TG-01 / TASK-TG-02 — отказы транспорта и отсутствие токена
# ======================================================================
class TestSendAlertFailures(unittest.TestCase):

    def _assert_failed(self, result: Dict[str, Any], error_code: str) -> None:
        self.assertFalse(result["delivered"], f"delivered=True при отказе: {result}")
        self.assertNotEqual(result["status"], "SENT")
        self.assertEqual(result["error"], error_code)
        self.assertTrue(str(result.get("error_detail") or "").strip(), "причина отказа не указана")

    def test_missing_token_fails_closed_and_never_touches_transport(self):
        transport = RecordingTransport()
        connector = make_connector(transport)
        with env_vars(**{TOKEN_ENV: None}):
            with self.assertLogs("TelegramConnector", level="ERROR") as logs:
                result = connector.send_alert(chat_id="12345", message="hello")
        self._assert_failed(result, "MISSING_TOKEN")
        self.assertEqual(transport.calls, [], "Попытка отправки без токена")
        self.assertTrue(any(TOKEN_ENV in line for line in logs.output), logs.output)

    def test_empty_token_is_treated_as_missing(self):
        transport = RecordingTransport()
        connector = make_connector(transport)
        with env_vars(**{TOKEN_ENV: "   "}):
            with self.assertLogs("TelegramConnector", level="ERROR"):
                result = connector.send_alert(chat_id="12345", message="hello")
        self._assert_failed(result, "MISSING_TOKEN")
        self.assertEqual(transport.calls, [])

    def test_api_level_error_is_not_reported_as_delivered(self):
        """Принцип 15 BIBLE: успех — только по фактически проверенному ответу."""
        transport = RecordingTransport(status=200, body={"ok": False, "description": "Bad Request: chat not found"})
        connector = make_connector(transport)
        with env_vars(**{TOKEN_ENV: FAKE_TOKEN}):
            with self.assertLogs("TelegramConnector", level="ERROR"):
                result = connector.send_alert(chat_id="12345", message="hello")
        self._assert_failed(result, "API_ERROR")
        self.assertIn("chat not found", result["error_detail"])

    def test_non_2xx_http_status_is_not_reported_as_delivered(self):
        transport = RecordingTransport(status=403, raw_body=b'{"ok":false,"description":"Forbidden: bot was blocked"}')
        connector = make_connector(transport)
        with env_vars(**{TOKEN_ENV: FAKE_TOKEN}):
            with self.assertLogs("TelegramConnector", level="ERROR"):
                result = connector.send_alert(chat_id="12345", message="hello")
        self._assert_failed(result, "HTTP_ERROR")
        self.assertEqual(result["http_status"], 403)

    def test_unparseable_body_is_not_reported_as_delivered(self):
        transport = RecordingTransport(status=200, raw_body=b"<html>502 Bad Gateway</html>")
        connector = make_connector(transport)
        with env_vars(**{TOKEN_ENV: FAKE_TOKEN}):
            with self.assertLogs("TelegramConnector", level="ERROR"):
                result = connector.send_alert(chat_id="12345", message="hello")
        self._assert_failed(result, "BAD_RESPONSE")

    def test_timeout_does_not_crash_process(self):
        transport = RecordingTransport(raises=socket.timeout("timed out"))
        connector = make_connector(transport)
        with env_vars(**{TOKEN_ENV: FAKE_TOKEN}):
            with self.assertLogs("TelegramConnector", level="ERROR"):
                result = connector.send_alert(chat_id="12345", message="hello")
        self._assert_failed(result, "TIMEOUT")

    def test_urlerror_timeout_is_classified_as_timeout(self):
        transport = RecordingTransport(raises=urllib.error.URLError(socket.timeout("timed out")))
        connector = make_connector(transport)
        with env_vars(**{TOKEN_ENV: FAKE_TOKEN}):
            with self.assertLogs("TelegramConnector", level="ERROR"):
                result = connector.send_alert(chat_id="12345", message="hello")
        self._assert_failed(result, "TIMEOUT")

    def test_transport_exception_does_not_crash_process(self):
        transport = RecordingTransport(raises=urllib.error.URLError("[Errno 11001] getaddrinfo failed"))
        connector = make_connector(transport)
        with env_vars(**{TOKEN_ENV: FAKE_TOKEN}):
            with self.assertLogs("TelegramConnector", level="ERROR"):
                result = connector.send_alert(chat_id="12345", message="hello")
        self._assert_failed(result, "TRANSPORT_ERROR")

    def test_panic_notification_reports_failure_when_transport_fails(self):
        transport = RecordingTransport(status=500, raw_body=b'{"ok":false,"description":"Internal Server Error"}')
        connector = make_connector(transport)
        with env_vars(**{TOKEN_ENV: FAKE_TOKEN}):
            with self.assertLogs("TelegramConnector", level="ERROR"):
                result = connector.send_panic_notification(exit_code=10, reason="Out-of-band operator signal")
        self.assertFalse(result["delivered"])
        self.assertEqual(result["priority"], "CRITICAL")


# ======================================================================
# TASK-TG-02 — гигиена секретов (Принцип 14 BIBLE)
# ======================================================================
class TestSecretHygiene(unittest.TestCase):

    def _capture_logs(self) -> Tuple[logging.Handler, io.StringIO]:
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setLevel(logging.DEBUG)
        return handler, stream

    def test_token_absent_from_result_and_logs_on_success(self):
        transport = RecordingTransport()
        connector = make_connector(transport)
        handler, stream = self._capture_logs()
        tg.logger.addHandler(handler)
        old_level = tg.logger.level
        tg.logger.setLevel(logging.DEBUG)
        try:
            with env_vars(**{TOKEN_ENV: FAKE_TOKEN}):
                result = connector.send_alert(chat_id="12345", message="hello")
        finally:
            tg.logger.removeHandler(handler)
            tg.logger.setLevel(old_level)

        self.assertTrue(result["delivered"])
        self.assertNotIn(FAKE_TOKEN, json.dumps(result, ensure_ascii=False))
        self.assertNotIn(FAKE_TOKEN, stream.getvalue())
        # Токен обязан быть в URL (этого требует Bot API), но не в результате.
        self.assertIn(FAKE_TOKEN, transport.calls[0]["url"])

    def test_token_is_redacted_when_transport_error_leaks_the_url(self):
        """
        urllib умеет включать URL в текст исключения; URL содержит токен.
        Причина отказа не должна протаскивать секрет наружу.
        """
        leaky = urllib.error.URLError(
            f"<urlopen error connecting to https://api.telegram.org/bot{FAKE_TOKEN}/sendMessage>"
        )
        transport = RecordingTransport(raises=leaky)
        connector = make_connector(transport)
        handler, stream = self._capture_logs()
        tg.logger.addHandler(handler)
        old_level = tg.logger.level
        tg.logger.setLevel(logging.DEBUG)
        try:
            with env_vars(**{TOKEN_ENV: FAKE_TOKEN}):
                result = connector.send_alert(chat_id="12345", message="hello")
        finally:
            tg.logger.removeHandler(handler)
            tg.logger.setLevel(old_level)

        self.assertFalse(result["delivered"])
        self.assertNotIn(FAKE_TOKEN, json.dumps(result, ensure_ascii=False))
        self.assertNotIn(FAKE_TOKEN, stream.getvalue())

    def test_token_is_not_injected_into_message_text(self):
        transport = RecordingTransport()
        connector = make_connector(transport)
        with env_vars(**{TOKEN_ENV: FAKE_TOKEN}):
            connector.send_alert(chat_id="12345", message="hello")
        self.assertNotIn(FAKE_TOKEN, transport.last_payload["text"])

    def test_no_operator_id_or_token_literal_in_source(self):
        source = Path(tg.__file__).read_text(encoding="utf-8")
        self.assertNotIn(FAKE_TOKEN, source)
        self.assertIsNone(
            re.search(r"[\"']\d{6,}:[A-Za-z0-9_\-]{20,}[\"']", source),
            "В исходнике найден литерал, похожий на токен Bot API",
        )


# ======================================================================
# TASK-TG-03 — авторизация операторов, fail-closed
# ======================================================================
class TestOperatorAuthorization(unittest.TestCase):

    def setUp(self):
        self.connector = make_connector(RecordingTransport())

    def test_handle_incoming_command_has_user_id_parameter(self):
        params = inspect.signature(TelegramConnector.handle_incoming_command).parameters
        self.assertIn("user_id", params, "TASK-TG-03: параметр user_id отсутствует")

    def test_command_cannot_be_dispatched_without_user_id(self):
        with env_vars(**{OPERATORS_ENV: "111"}):
            with self.assertRaises(TypeError):
                self.connector.handle_incoming_command("/panic")  # type: ignore[call-arg]

    def test_unset_operators_env_denies_panic(self):
        with env_vars(**{OPERATORS_ENV: None}):
            with self.assertLogs("TelegramConnector", level="WARNING"):
                result = self.connector.handle_incoming_command("/panic", user_id="111")
        self.assertFalse(result["authorized"])
        self.assertEqual(result["action"], "DENIED")
        self.assertNotEqual(result.get("exit_code"), 10)
        self.assertEqual(result["reason"], "NO_OPERATORS_CONFIGURED")

    def test_empty_operators_env_denies_everything(self):
        for raw in ("", "   ", " , ,, "):
            for command in ("/panic", "/status", "/evolve off", "/mode prod_evo"):
                with self.subTest(raw=raw, command=command):
                    with env_vars(**{OPERATORS_ENV: raw}):
                        with self.assertLogs("TelegramConnector", level="WARNING"):
                            result = self.connector.handle_incoming_command(command, user_id="111")
                    self.assertFalse(result["authorized"])
                    self.assertEqual(result["action"], "DENIED")

    def test_unknown_user_is_denied_and_logged_with_user_id(self):
        with env_vars(**{OPERATORS_ENV: "111,222"}):
            with self.assertLogs("TelegramConnector", level="WARNING") as logs:
                result = self.connector.handle_incoming_command("/panic", user_id="999")
        self.assertFalse(result["authorized"])
        self.assertEqual(result["reason"], "USER_NOT_AUTHORIZED")
        self.assertTrue(any("999" in line for line in logs.output), logs.output)

    def test_missing_user_id_is_denied(self):
        with env_vars(**{OPERATORS_ENV: "111,222"}):
            with self.assertLogs("TelegramConnector", level="WARNING"):
                result = self.connector.handle_incoming_command("/panic", user_id=None)
        self.assertFalse(result["authorized"])
        self.assertEqual(result["reason"], "MISSING_USER_ID")

    def test_authorized_operator_triggers_panic(self):
        with env_vars(**{OPERATORS_ENV: " 111 , 222 "}):
            result = self.connector.handle_incoming_command("/panic", user_id="222")
        self.assertTrue(result["authorized"])
        self.assertEqual(result["action"], "TRIGGER_PANIC")
        self.assertEqual(result["exit_code"], 10)

    def test_numeric_user_id_is_accepted(self):
        with env_vars(**{OPERATORS_ENV: "111"}):
            result = self.connector.handle_incoming_command("/status", user_id=111)
        self.assertTrue(result["authorized"])
        self.assertEqual(result["action"], "GET_STATUS")

    def test_partial_id_match_is_rejected(self):
        with env_vars(**{OPERATORS_ENV: "1112223"}):
            with self.assertLogs("TelegramConnector", level="WARNING"):
                result = self.connector.handle_incoming_command("/panic", user_id="111")
        self.assertFalse(result["authorized"])

    def test_denied_reply_does_not_claim_execution(self):
        with env_vars(**{OPERATORS_ENV: None}):
            with self.assertLogs("TelegramConnector", level="WARNING"):
                result = self.connector.handle_incoming_command("/panic", user_id="111")
        reply = result["reply"]
        self.assertNotIn("Exit Code 10", reply)
        self.assertNotIn("Supervisor завершает", reply)

    def test_is_authorized_is_fail_closed_by_itself(self):
        with env_vars(**{OPERATORS_ENV: None}):
            allowed, reason = self.connector.is_authorized("111")
        self.assertFalse(allowed)
        self.assertEqual(reason, "NO_OPERATORS_CONFIGURED")


# ======================================================================
# TASK-TG-05 — устранение протухших счётчиков
# ======================================================================
class TestStaleCountersRemoved(unittest.TestCase):

    def setUp(self):
        self.connector = make_connector(RecordingTransport())

    def _status_reply(self) -> str:
        with env_vars(**{OPERATORS_ENV: "111"}):
            return self.connector.handle_incoming_command("/status", user_id="111")["reply"]

    def test_hardcoded_counters_are_gone_from_source(self):
        source = Path(tg.__file__).read_text(encoding="utf-8")
        self.assertNotIn("52/52", source)
        self.assertNotIn("13/13", source)

    def test_status_reply_has_no_stale_constants(self):
        reply = self._status_reply()
        self.assertNotIn("52/52", reply)
        self.assertNotIn("13/13", reply)

    def test_status_reply_reports_actual_test_count(self):
        # Независимый пересчёт: реализация обязана дать то же число.
        pattern = re.compile(r"^[ \t]*def " + r"test_[A-Za-z0-9_]*\s*\(", re.MULTILINE)
        actual = sum(
            len(pattern.findall(path.read_text(encoding="utf-8")))
            for path in sorted((ROOT_DIR / "tests").glob("test_*.py"))
        )
        self.assertGreater(actual, 52, "тестов в репозитории должно быть больше протухшей константы")
        self.assertIn(str(actual), self._status_reply())

    def test_status_reply_reports_actual_bible_principle_count(self):
        bible = ROOT_DIR / "Supervisor" / "Constitution" / "BIBLE.md"
        actual = len(re.findall(r"^#{2,4}\s*Принцип\s+\d+", bible.read_text(encoding="utf-8"), re.MULTILINE))
        self.assertGreaterEqual(actual, 15)
        self.assertIn(str(actual), self._status_reply())


# ======================================================================
# Сохранённые контракты вышестоящих вызовов (Tool/mcp_server.py)
# ======================================================================
class TestPublicSignaturesPreserved(unittest.TestCase):

    def test_send_alert_keeps_mcp_call_signature(self):
        params = inspect.signature(TelegramConnector.send_alert).parameters
        for name in ("chat_id", "message", "priority"):
            self.assertIn(name, params)

    def test_connector_constructs_without_arguments(self):
        connector = TelegramConnector()
        self.assertEqual(connector.bot_token_env, "TELEGRAM_BOT_TOKEN")
        self.assertEqual(connector.operators_env, OPERATORS_ENV)
        self.assertGreater(connector.timeout, 0)

    def test_empty_chat_id_still_raises_value_error(self):
        connector = make_connector(RecordingTransport())
        with env_vars(**{TOKEN_ENV: FAKE_TOKEN}):
            with self.assertRaises(ValueError):
                connector.send_alert(chat_id="  ", message="hello")


if __name__ == "__main__":
    unittest.main(verbosity=2)
