#!/usr/bin/env python3
"""
Unit tests for Tool/connectors/llm_connector.py

Транспорт подменяется, поэтому ни один тест не ходит в сеть и не требует
ANTHROPIC_API_KEY. Проверяется то, что можно проверить без ключа: fail-closed
без ключа, форма запроса, разбор всех ветвей ответа, ретраи, нераскрытие
секрета. Живая доставка (реальный вызов модели) НЕ покрыта — это отдельная
проверка, которая станет возможна, когда ключ появится в окружении.
"""

import json
import os
import unittest
from typing import Any, Dict, List, Tuple

from Tool.connectors.llm_connector import LLMConnector, API_URL, API_VERSION


class _Recorder:
    """Подменный транспорт: пишет вызовы, отдаёт заготовленные ответы."""

    def __init__(self, responses: List[Tuple[int, bytes]]):
        self.responses = list(responses)
        self.calls: List[Dict[str, Any]] = []

    def __call__(self, url: str, data: bytes, headers: Dict[str, str], timeout: float):
        self.calls.append({"url": url, "data": data, "headers": headers, "timeout": timeout})
        return self.responses.pop(0)


def _ok_body(text: str = "предложение", stop_reason: str = "end_turn") -> bytes:
    return json.dumps({
        "model": "claude-opus-5",
        "stop_reason": stop_reason,
        "content": [{"type": "text", "text": text}],
        "usage": {"input_tokens": 10, "output_tokens": 20},
    }).encode("utf-8")


class TestApiKeyHandling(unittest.TestCase):

    def setUp(self):
        self._saved = os.environ.get("ANTHROPIC_API_KEY")

    def tearDown(self):
        if self._saved is None:
            os.environ.pop("ANTHROPIC_API_KEY", None)
        else:
            os.environ["ANTHROPIC_API_KEY"] = self._saved

    def test_missing_key_fails_closed_without_any_network_call(self):
        """Нет ключа — отказ, и НИ ОДНОГО обращения к транспорту.

        Главная проверка модуля: молчаливый успех без ключа означал бы, что
        предложитель «работает», ничего не спросив у модели — ровно тот класс
        симуляции, от которого предостерегает CLAUDE.md, правило 2.
        """
        os.environ.pop("ANTHROPIC_API_KEY", None)
        transport = _Recorder([])
        res = LLMConnector(transport=transport).propose("почини это")

        self.assertFalse(res["proposed"])
        self.assertEqual(res["error"], "NO_API_KEY")
        self.assertEqual(transport.calls, [], "при отсутствии ключа сеть трогать нельзя")

    def test_blank_key_is_treated_as_missing(self):
        """Пустая строка в ENV — это отсутствие ключа, а не пустой ключ."""
        os.environ["ANTHROPIC_API_KEY"] = "   "
        transport = _Recorder([])
        res = LLMConnector(transport=transport).propose("почини это")
        self.assertEqual(res["error"], "NO_API_KEY")
        self.assertEqual(transport.calls, [])

    def test_key_never_leaks_into_result_or_error_detail(self):
        """Ключ не должен попасть в возвращаемый словарь ни при каком исходе."""
        secret = "sk-ant-super-secret-value"
        os.environ["ANTHROPIC_API_KEY"] = secret
        # Сервер вернул ошибку, эхом отразив заголовок с ключом.
        transport = _Recorder([(400, f"invalid x-api-key: {secret}".encode("utf-8"))])
        res = LLMConnector(transport=transport, max_retries=1).propose("привет")

        self.assertFalse(res["proposed"])
        self.assertNotIn(secret, json.dumps(res, ensure_ascii=False))
        self.assertIn("REDACTED", res["error_detail"])


class TestRequestShape(unittest.TestCase):

    def setUp(self):
        self._saved = os.environ.get("ANTHROPIC_API_KEY")
        os.environ["ANTHROPIC_API_KEY"] = "sk-ant-test"

    def tearDown(self):
        if self._saved is None:
            os.environ.pop("ANTHROPIC_API_KEY", None)
        else:
            os.environ["ANTHROPIC_API_KEY"] = self._saved

    def test_request_targets_messages_api_with_required_headers(self):
        transport = _Recorder([(200, _ok_body())])
        LLMConnector(transport=transport).propose("почини это")

        call = transport.calls[0]
        self.assertEqual(call["url"], API_URL)
        self.assertEqual(call["headers"]["anthropic-version"], API_VERSION)
        self.assertEqual(call["headers"]["x-api-key"], "sk-ant-test")
        self.assertEqual(call["headers"]["content-type"], "application/json")
        self.assertGreater(call["timeout"], 0, "таймаут обязан быть задан явно")

    def test_payload_omits_parameters_rejected_by_opus_5(self):
        """budget_tokens и assistant-prefill на Opus 5 дают 400.

        Проверяется отсутствие, а не наличие: это тот случай, когда лишний
        параметр ломает запрос целиком, и «забыли убрать» стоит дороже, чем
        «забыли добавить».
        """
        transport = _Recorder([(200, _ok_body())])
        LLMConnector(transport=transport).propose("почини это", system="ты рефакторишь код")

        payload = json.loads(transport.calls[0]["data"].decode("utf-8"))
        self.assertEqual(payload["model"], "claude-opus-5")
        self.assertEqual(payload["output_config"]["effort"], "xhigh")
        self.assertNotIn("budget_tokens", json.dumps(payload))
        self.assertEqual(payload["system"], "ты рефакторишь код")
        # Ровно одно сообщение, и оно пользовательское — никакого prefill.
        self.assertEqual([m["role"] for m in payload["messages"]], ["user"])


class TestResponseInterpretation(unittest.TestCase):

    def setUp(self):
        self._saved = os.environ.get("ANTHROPIC_API_KEY")
        os.environ["ANTHROPIC_API_KEY"] = "sk-ant-test"

    def tearDown(self):
        if self._saved is None:
            os.environ.pop("ANTHROPIC_API_KEY", None)
        else:
            os.environ["ANTHROPIC_API_KEY"] = self._saved

    def test_successful_response_returns_the_text(self):
        transport = _Recorder([(200, _ok_body("diff --git a/x b/x"))])
        res = LLMConnector(transport=transport).propose("почини это")

        self.assertTrue(res["proposed"])
        self.assertEqual(res["text"], "diff --git a/x b/x")
        self.assertEqual(res["stop_reason"], "end_turn")
        self.assertEqual(res["usage"]["output_tokens"], 20)

    def test_refusal_is_a_failure_despite_http_200(self):
        """stop_reason=refusal приходит с HTTP 200 — успехом это не является.

        Наивное чтение content дало бы пустую строку и «успех» без текста.
        Поэтому stop_reason проверяется ДО чтения содержимого.
        """
        body = json.dumps({
            "model": "claude-opus-5", "stop_reason": "refusal",
            "stop_details": {"type": "refusal", "category": "cyber"},
            "content": [],
        }).encode("utf-8")
        res = LLMConnector(transport=_Recorder([(200, body)])).propose("сделай плохое")

        self.assertFalse(res["proposed"])
        self.assertEqual(res["error"], "REFUSAL")
        self.assertEqual(res["stop_reason"], "refusal")
        self.assertEqual(res["http_status"], 200)

    def test_empty_content_is_not_reported_as_success(self):
        body = json.dumps({"model": "claude-opus-5", "stop_reason": "end_turn",
                           "content": []}).encode("utf-8")
        res = LLMConnector(transport=_Recorder([(200, body)])).propose("привет")
        self.assertFalse(res["proposed"])
        self.assertEqual(res["error"], "EMPTY_CONTENT")

    def test_malformed_json_is_reported_not_raised(self):
        res = LLMConnector(transport=_Recorder([(200, b"<html>502</html>")])).propose("привет")
        self.assertFalse(res["proposed"])
        self.assertEqual(res["error"], "BAD_RESPONSE")


class TestRetryPolicy(unittest.TestCase):

    def setUp(self):
        self._saved = os.environ.get("ANTHROPIC_API_KEY")
        os.environ["ANTHROPIC_API_KEY"] = "sk-ant-test"
        self.slept: List[float] = []

    def tearDown(self):
        if self._saved is None:
            os.environ.pop("ANTHROPIC_API_KEY", None)
        else:
            os.environ["ANTHROPIC_API_KEY"] = self._saved

    def test_429_is_retried_then_succeeds(self):
        transport = _Recorder([(429, b"rate limited"), (200, _ok_body("готово"))])
        res = LLMConnector(transport=transport, sleep=self.slept.append).propose("привет")

        self.assertTrue(res["proposed"])
        self.assertEqual(res["text"], "готово")
        self.assertEqual(len(transport.calls), 2)
        self.assertEqual(len(self.slept), 1, "между попытками обязана быть задержка")

    def test_400_is_not_retried(self):
        """Дефект запроса повтором не лечится — fail-closed сразу."""
        transport = _Recorder([(400, b'{"error":{"type":"invalid_request_error"}}')])
        res = LLMConnector(transport=transport, sleep=self.slept.append).propose("привет")

        self.assertFalse(res["proposed"])
        self.assertEqual(res["error"], "HTTP_ERROR")
        self.assertEqual(len(transport.calls), 1, "400 не должен ретраиться")
        self.assertEqual(self.slept, [])

    def test_timeout_does_not_crash_the_process(self):
        class _Boom:
            calls: List[Any] = []

            def __call__(self, *args, **kwargs):
                _Boom.calls.append(1)
                raise TimeoutError("timed out")

        res = LLMConnector(transport=_Boom(), max_retries=2,
                           sleep=self.slept.append).propose("привет")
        self.assertFalse(res["proposed"])
        self.assertEqual(res["error"], "TIMEOUT")


if __name__ == "__main__":
    unittest.main()
