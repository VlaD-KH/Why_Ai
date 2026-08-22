#!/usr/bin/env python3
"""
Unit tests for Tool/connectors/telegram_bridge.py (TASK-TG-07/08).
Verifies SSE reconnect-with-backoff and event parsing, hermetically (fake
opener) for the reconnect logic itself, and against a real local
Core/server.py instance for wire-format compatibility.
"""

import http.server
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path

from Core.server import ControlApiHandler, broadcast_event
from Tool.connectors.telegram_bridge import (
    DEFAULT_MONITORED_SEVERITIES,
    SSESubscriber,
    TelegramUpdatesPoller,
    dispatch_action,
    event_severity,
    load_monitored_severities,
    should_forward,
)

TEST_PORT = 18767


def _sse_lines(event_type, payload):
    return [
        f"event: {event_type}\n".encode("utf-8"),
        f"data: {json.dumps(payload)}\n".encode("utf-8"),
        b"\n",
    ]


class _FakeStream:
    """Итерируемый по строкам байт-поток; может завершиться заданным исключением."""

    def __init__(self, lines, error=None):
        self._lines = list(lines)
        self._error = error
        self.closed = False

    def __iter__(self):
        return self

    def __next__(self):
        if self._lines:
            return self._lines.pop(0)
        if self._error is not None:
            err, self._error = self._error, None
            raise err
        raise StopIteration

    def close(self):
        self.closed = True


class TestSSESubscriberReconnect(unittest.TestCase):
    """Гейт TASK-TG-07: подписчик обязан пережить обрыв потока и переподключиться."""

    def test_reconnects_after_stream_failure_and_keeps_delivering_events(self):
        stream_1 = _FakeStream(
            _sse_lines("connected", {"message": "hi"})
            + _sse_lines("panic_stop", {"type": "panic_stop", "data": {"reason": "first"}}),
            error=ConnectionError("stream dropped"),
        )
        stream_2 = _FakeStream(
            _sse_lines("panic_stop", {"type": "panic_stop", "data": {"reason": "second"}})
        )
        streams = [stream_1, stream_2]

        def fake_opener(url, timeout):
            return streams.pop(0)

        received = []
        sleeps = []

        def on_event(event_type, data):
            received.append((event_type, data))
            if event_type == "panic_stop" and data.get("reason") == "second":
                sub.stop()

        sub = SSESubscriber(
            url="http://fake/api/events/stream",
            on_event=on_event,
            opener=fake_opener,
            initial_backoff=0.1,
            max_backoff=1.0,
            sleep_fn=sleeps.append,
        )
        sub.run_forever()

        self.assertEqual([t for t, _ in received], ["connected", "panic_stop", "panic_stop"])
        self.assertEqual(received[1][1], {"reason": "first"})
        self.assertEqual(received[2][1], {"reason": "second"})
        self.assertEqual(sleeps, [0.1], "должен переподключиться ровно один раз с базовым backoff")
        self.assertTrue(stream_1.closed)

    def test_backoff_grows_exponentially_up_to_the_cap(self):
        def always_failing_opener(url, timeout):
            raise ConnectionError("always down")

        sleeps = []

        def fake_sleep(seconds):
            sleeps.append(seconds)
            if len(sleeps) >= 4:
                sub.stop()

        sub = SSESubscriber(
            url="http://fake/api/events/stream",
            on_event=lambda event_type, data: None,
            opener=always_failing_opener,
            initial_backoff=0.1,
            max_backoff=0.5,
            sleep_fn=fake_sleep,
        )
        sub.run_forever()

        self.assertEqual(sleeps, [0.1, 0.2, 0.4, 0.5])

    def test_stop_between_events_ends_run_forever_promptly(self):
        stream = _FakeStream(
            _sse_lines("connected", {"message": "hi"})
            + _sse_lines("panic_stop", {"type": "panic_stop", "data": {}})
            + _sse_lines("panic_stop", {"type": "panic_stop", "data": {}})
        )

        def fake_opener(url, timeout):
            return stream

        received = []

        def stop_after_first(event_type, data):
            received.append(event_type)
            if len(received) == 1:
                sub.stop()

        sub = SSESubscriber(
            url="http://fake/api/events/stream",
            on_event=stop_after_first,
            opener=fake_opener,
            sleep_fn=lambda seconds: None,
        )
        sub.run_forever()

        self.assertEqual(received, ["connected"])


class TestSSESubscriberAgainstRealServer(unittest.TestCase):
    """Живая проверка: реальный Core/server.py, реальный формат SSE."""

    @classmethod
    def setUpClass(cls):
        cls.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", TEST_PORT), ControlApiHandler)
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        time.sleep(0.3)

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def test_receives_a_real_broadcast_event(self):
        received = []
        sub = SSESubscriber(
            url=f"http://127.0.0.1:{TEST_PORT}/api/events/stream",
            on_event=lambda event_type, data: received.append((event_type, data)),
            read_timeout=2.0,
        )
        thread = threading.Thread(target=sub.run_forever, daemon=True)
        thread.start()
        self.addCleanup(sub.stop)

        self._wait_until(lambda: any(t == "connected" for t, _ in received), timeout=3)

        broadcast_event("panic_stop", {"reason": "integration-check", "exit_code": 10})

        self._wait_until(lambda: any(t == "panic_stop" for t, _ in received), timeout=3)

        panic_events = [d for t, d in received if t == "panic_stop"]
        self.assertTrue(panic_events, "реальное broadcast_event событие не дошло до подписчика")
        self.assertEqual(panic_events[0]["reason"], "integration-check")

    @staticmethod
    def _wait_until(predicate, timeout):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if predicate():
                return
            time.sleep(0.05)
        raise AssertionError("condition not met within timeout")


class TestEventSeverityFilter(unittest.TestCase):
    """TASK-TG-08: фильтр уровней — конфигурируемый, не по выдуманной 4-уровневой схеме."""

    def test_known_event_types_map_to_documented_severities(self):
        # Соответствует Eye/telegram_mini_app.html:EVENT_META (sev).
        self.assertEqual(event_severity("panic_stop"), "crit")
        self.assertEqual(event_severity("mode_changed"), "warn")
        self.assertEqual(event_severity("dvpn_fallback"), "warn")
        self.assertEqual(event_severity("worktrees_pruned"), "info")
        self.assertEqual(event_severity("connected"), "ok")

    def test_unknown_event_type_defaults_to_info_not_silently_dropped(self):
        self.assertEqual(event_severity("some_future_event_type"), "info")

    def test_should_forward_respects_configured_severities(self):
        self.assertTrue(should_forward("panic_stop", {"crit"}))
        self.assertFalse(should_forward("worktrees_pruned", {"crit", "warn"}))
        self.assertTrue(should_forward("mode_changed", {"crit", "warn"}))

    def test_load_monitored_severities_reads_config_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            conf = Path(tmp) / "why_ai_config.yaml"
            conf.write_text(
                'tools:\n  telegram_bridge:\n    monitored_severities:\n      - "crit"\n',
                encoding="utf-8",
            )
            severities = load_monitored_severities(conf)
        self.assertEqual(severities, frozenset({"crit"}))

    def test_load_monitored_severities_falls_back_to_default_when_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            conf = Path(tmp) / "why_ai_config.yaml"
            conf.write_text('system:\n  project_name: "x"\n', encoding="utf-8")
            severities = load_monitored_severities(conf)
        self.assertEqual(severities, DEFAULT_MONITORED_SEVERITIES)

    def test_load_monitored_severities_falls_back_when_file_missing(self):
        severities = load_monitored_severities(Path(tempfile.gettempdir()) / "not-a-real-why-ai-config.yaml")
        self.assertEqual(severities, DEFAULT_MONITORED_SEVERITIES)


class TestTelegramUpdatesPoller(unittest.TestCase):
    """TASK-TG-09: long polling getUpdates — не setWebhook, публичный HTTPS не нужен."""

    def test_poll_once_extracts_command_user_and_chat_then_advances_offset(self):
        response_body = json.dumps({
            "ok": True,
            "result": [
                {
                    "update_id": 555,
                    "message": {
                        "text": "/status",
                        "from": {"id": 111},
                        "chat": {"id": 222},
                    },
                }
            ],
        }).encode("utf-8")

        calls = []

        def fake_opener(url, timeout):
            calls.append(url)
            return 200, response_body

        received = []
        poller = TelegramUpdatesPoller(
            token="fake-token", on_command=lambda cmd, uid, cid: received.append((cmd, uid, cid)),
            opener=fake_opener,
        )
        poller.poll_once()

        self.assertEqual(received, [("/status", 111, 222)])
        self.assertIn("getUpdates", calls[0])
        self.assertNotIn("offset=", calls[0], "первый запрос не должен нести смещение")

        # Второй вызов обязан унести offset = update_id + 1, иначе апдейт придёт снова.
        poller.poll_once()
        self.assertIn("offset=556", calls[1])

    def test_poll_once_ignores_updates_without_text_and_non_ok_responses(self):
        received = []
        poller = TelegramUpdatesPoller(
            token="fake-token", on_command=lambda cmd, uid, cid: received.append(cmd),
            opener=lambda url, timeout: (200, json.dumps({
                "ok": True, "result": [{"update_id": 1, "message": {"from": {"id": 1}, "chat": {"id": 1}}}],
            }).encode()),
        )
        poller.poll_once()
        self.assertEqual(received, [], "сообщение без text не должно вызывать on_command")

        poller_bad_status = TelegramUpdatesPoller(
            token="fake-token", on_command=lambda cmd, uid, cid: received.append(cmd),
            opener=lambda url, timeout: (401, b'{"ok": false, "description": "Unauthorized"}'),
        )
        poller_bad_status.poll_once()  # не должен бросать исключение
        self.assertEqual(received, [])


class TestDispatchAction(unittest.TestCase):
    """TASK-TG-10/TG-11: реальный вызов бэкенда, ответ основан на факте, не на отправке запроса."""

    def test_panic_confirmed_only_on_2xx_from_the_real_endpoint(self):
        calls = []

        def opener_ok(url, timeout):
            calls.append(url)
            return 200, b""

        reply = dispatch_action(
            {"action": "TRIGGER_PANIC"}, backend_base_url="http://127.0.0.1:8765", opener=opener_ok,
        )
        self.assertIn("http://127.0.0.1:8765/api/panic", calls[0])
        self.assertIn("подтверждён", reply)
        self.assertNotIn("НЕ подтверждён", reply)

    def test_panic_reports_failure_on_404_not_success(self):
        # Анти-критерий TASK-TG-10: подмена эндпоинта на несуществующий (404)
        # обязана дать сообщение об ОТКАЗЕ, а не "система остановлена".
        reply = dispatch_action(
            {"action": "TRIGGER_PANIC"}, backend_base_url="http://127.0.0.1:8765",
            opener=lambda url, timeout: (404, b"Not Found"),
        )
        self.assertIn("НЕ подтверждён", reply)
        self.assertIn("404", reply)

    def test_panic_reports_failure_on_transport_error(self):
        def broken_opener(url, timeout):
            raise ConnectionRefusedError("daemon is down")

        reply = dispatch_action(
            {"action": "TRIGGER_PANIC"}, backend_base_url="http://127.0.0.1:8765", opener=broken_opener,
        )
        self.assertIn("НЕ подтверждён", reply)

    def test_status_reports_real_backend_data_not_a_hardcoded_string(self):
        body = json.dumps({"status": "RUNNING", "version": "1.1.0-gold", "workspace_root": "/tmp/x"}).encode()
        reply = dispatch_action(
            {"action": "GET_STATUS"}, backend_base_url="http://127.0.0.1:8765",
            opener=lambda url, timeout: (200, body),
        )
        self.assertIn("RUNNING", reply)
        self.assertIn("1.1.0-gold", reply)

    def test_status_reports_failure_on_non_2xx(self):
        reply = dispatch_action(
            {"action": "GET_STATUS"}, backend_base_url="http://127.0.0.1:8765",
            opener=lambda url, timeout: (503, b"Service Unavailable"),
        )
        self.assertIn("Не удалось", reply)

    def test_other_actions_pass_through_the_existing_reply_unchanged(self):
        # DISABLE_BACKGROUND_EVO и т.п. не имеют реального бэкенд-вызова в
        # этом цикле (TASK-TG-09..12) — dispatch_action не должен подделывать
        # успех, которого не проверял.
        action_result = {"action": "DISABLE_BACKGROUND_EVO", "reply": "⏸️ Фоновое самосознание временно приостановлено."}
        reply = dispatch_action(action_result, backend_base_url="http://127.0.0.1:8765", opener=lambda u, t: (200, b""))
        self.assertEqual(reply, action_result["reply"])


if __name__ == "__main__":
    unittest.main()
