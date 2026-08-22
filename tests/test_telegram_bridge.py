#!/usr/bin/env python3
"""
Unit tests for Tool/connectors/telegram_bridge.py (TASK-TG-07/08).
Verifies SSE reconnect-with-backoff and event parsing, hermetically (fake
opener) for the reconnect logic itself, and against a real local
Core/server.py instance for wire-format compatibility.
"""

import http.server
import json
import threading
import time
import unittest

from Core.server import ControlApiHandler, broadcast_event
from Tool.connectors.telegram_bridge import SSESubscriber

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

        def fake_sleep(seconds):
            sleeps.append(seconds)
            if len(sleeps) >= 1:
                sub.stop()

        sub = SSESubscriber(
            url="http://fake/api/events/stream",
            on_event=lambda event_type, data: received.append((event_type, data)),
            opener=fake_opener,
            initial_backoff=0.1,
            max_backoff=1.0,
            sleep_fn=fake_sleep,
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


if __name__ == "__main__":
    unittest.main()
