#!/usr/bin/env python3
"""
Модуль: Tool/connectors/llm_connector.py
Назначение: Клиент Anthropic Messages API для актора синтеза (предложителя)
            в контуре самоэволюции.
Архитектурный слой: Tool/connectors (Зона R — реальные внешние эффекты).

Почему именно здесь, а не в Core/ или Supervisor/:
  BIBLE.md Принцип 15 («Изоляция исходящего сетевого доступа») запрещает
  сетевые вызовы ИЗ ЯДРА. `protected_paths.yaml` описывает Tool/connectors/
  как слой, который «executes real side effects against external systems» —
  граница уже проведена политикой, и этот файл кладётся ровно по ней.
  Supervisor/ и Core/ сетевых вызовов не делают: EvolutionDaemon получает
  коннектор инъекцией и не знает, что за ним сеть.

Ограничения контура (те же, что у telegram_connector.py):
  * stdlib-only — транспорт только `urllib.request`, никаких
    `anthropic`/`httpx`/`requests`. В репозитории нет ни одного манифеста
    зависимостей, и вводить первый ради одного вызова — сменить инвариант
    проекта, а не добавить фичу.
  * Ключ строго из окружения (Принцип 14 — ноль учётных данных в
    репозитории). Никогда не логируется и не попадает в возвращаемый словарь.
  * Fail-closed: отсутствие ключа — это отказ, а не «проверка отключена».
"""

import json
import logging
import os
import time
import urllib.error
import urllib.request
from typing import Any, Callable, Dict, List, Optional, Tuple

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] [LLM-CONNECTOR] %(message)s")
logger = logging.getLogger("LLMConnector")

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"
DEFAULT_MODEL = "claude-opus-5"
DEFAULT_MAX_TOKENS = 16000
DEFAULT_EFFORT = "xhigh"          # лучший режим для кодовых задач
DEFAULT_TIMEOUT = 120.0
API_KEY_ENV = "ANTHROPIC_API_KEY"
REDACTED = "***REDACTED***"
MAX_ERROR_DETAIL = 600

# Ретраить имеет смысл только перегрузку и сбои на стороне сервиса.
# 400/401/403/404 — это дефект запроса или доступа: повтор даст тот же ответ,
# только позже, поэтому fail-closed без ретрая.
RETRYABLE_STATUSES = frozenset({408, 409, 429, 500, 502, 503, 504})

# (status_code, body_bytes)
Transport = Callable[[str, bytes, Dict[str, str], float], Tuple[int, bytes]]


def _urllib_transport(url: str, data: bytes, headers: Dict[str, str], timeout: float) -> Tuple[int, bytes]:
    """Транспорт по умолчанию: POST через stdlib urllib с явным таймаутом."""
    request = urllib.request.Request(url, data=data, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = int(getattr(response, "status", None) or getattr(response, "code", None) or 0)
            return status, response.read()
    except urllib.error.HTTPError as http_error:
        # Тело ошибки несёт машинночитаемую причину (type/message) — читаем.
        try:
            body = http_error.read()
        except Exception:
            body = b""
        return int(http_error.code), body


class LLMConnector:
    """Клиент Anthropic Messages API для предложителя самоэволюции."""

    def __init__(
        self,
        api_key_env: str = API_KEY_ENV,
        model: str = DEFAULT_MODEL,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        effort: str = DEFAULT_EFFORT,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = 3,
        transport: Optional[Transport] = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.api_key_env = api_key_env
        self.model = model
        self.max_tokens = int(max_tokens)
        self.effort = effort
        self.timeout = float(timeout)
        self.max_retries = int(max_retries)
        self._transport: Transport = transport or _urllib_transport
        self._sleep = sleep

    # ------------------------------------------------------------------
    # Секреты (Принцип 14)
    # ------------------------------------------------------------------
    def _resolve_key(self) -> Optional[str]:
        """Ключ строго из окружения; пустая строка равнозначна отсутствию."""
        key = (os.getenv(self.api_key_env) or "").strip()
        return key or None

    def _redact(self, value: Any, key: Optional[str]) -> str:
        """Вычистить ключ из произвольного текста перед логом или возвратом."""
        text = str(value)
        if key:
            text = text.replace(key, REDACTED)
        if len(text) > MAX_ERROR_DETAIL:
            text = text[:MAX_ERROR_DETAIL] + "…"
        return text

    @staticmethod
    def _failure(error: str, detail: str, http_status: Optional[int] = None) -> Dict[str, Any]:
        """Единая форма отказа — как в telegram_connector._failure."""
        return {
            "proposed": False,
            "text": None,
            "model": None,
            "stop_reason": None,
            "http_status": http_status,
            "error": error,
            "error_detail": detail,
            "timestamp": time.time(),
        }

    # ------------------------------------------------------------------
    # Запрос
    # ------------------------------------------------------------------
    def _build_payload(self, prompt: str, system: Optional[str]) -> Dict[str, Any]:
        """Тело запроса Messages API.

        Осознанно НЕ передаются:
          * `budget_tokens` — на Opus 5 удалён, вернёт 400. Расширенное
            мышление включено по умолчанию, глубина задаётся `effort`.
          * assistant-prefill (последнее assistant-сообщение) — на Opus 5
            вернёт 400.
        """
        payload: Dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "output_config": {"effort": self.effort},
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            payload["system"] = system
        return payload

    def propose(self, prompt: str, system: Optional[str] = None) -> Dict[str, Any]:
        """Запросить у модели предложение изменения.

        Возвращает единообразный словарь. `proposed: True` выставляется ТОЛЬКО
        когда HTTP 2xx, ответ распарсен, `stop_reason` не отказной и в
        `content` есть непустой текстовый блок — то есть по факту полученного
        текста, а не по факту отправки запроса.
        """
        key = self._resolve_key()
        if not key:
            # Fail-closed и, что важно, БЕЗ сетевого вызова: отсутствие ключа
            # — конфигурационный отказ, а не сбой связи.
            logger.error(f"Ключ не задан в ${self.api_key_env} — предложение невозможно.")
            return self._failure("NO_API_KEY", f"Переменная окружения {self.api_key_env} не задана или пуста.")

        headers = {
            "x-api-key": key,
            "anthropic-version": API_VERSION,
            "content-type": "application/json",
            "accept": "application/json",
            "user-agent": "Why_Ai-LLMConnector/1.0",
        }
        body = json.dumps(self._build_payload(prompt, system), ensure_ascii=False).encode("utf-8")

        last: Dict[str, Any] = self._failure("NOT_ATTEMPTED", "Ни одной попытки не выполнено.")
        for attempt in range(1, self.max_retries + 1):
            try:
                status, raw = self._transport(API_URL, body, headers, self.timeout)
            except Exception as exc:  # таймаут и сетевые сбои не роняют процесс
                detail = self._redact(exc, key)
                is_timeout = "timed out" in detail.lower() or "timeout" in type(exc).__name__.lower()
                last = self._failure("TIMEOUT" if is_timeout else "TRANSPORT_ERROR", detail)
                if attempt < self.max_retries:
                    self._sleep(min(2 ** attempt, 30))
                    continue
                return last

            if status in RETRYABLE_STATUSES and attempt < self.max_retries:
                logger.warning(f"HTTP {status} от Anthropic API, попытка {attempt}/{self.max_retries}.")
                self._sleep(min(2 ** attempt, 30))
                continue

            return self._interpret(status, raw, key)

        return last

    def _interpret(self, status: int, raw: bytes, key: Optional[str]) -> Dict[str, Any]:
        """Разбор ответа. Успех — только по фактически полученному тексту."""
        if status < 200 or status >= 300:
            return self._failure("HTTP_ERROR", self._redact(raw.decode("utf-8", "replace"), key), status)

        try:
            data = json.loads(raw.decode("utf-8", "replace"))
        except Exception as exc:
            return self._failure("BAD_RESPONSE", self._redact(exc, key), status)

        stop_reason = data.get("stop_reason")
        # stop_reason проверяется ДО чтения content: при отказе по политике
        # ответ приходит с HTTP 200, и наивное чтение content выдало бы
        # пустоту за успех.
        if stop_reason == "refusal":
            details = data.get("stop_details") or {}
            return {
                **self._failure("REFUSAL", self._redact(json.dumps(details, ensure_ascii=False), key), status),
                "stop_reason": stop_reason,
                "model": data.get("model"),
            }

        text = "".join(
            block.get("text", "")
            for block in (data.get("content") or [])
            if isinstance(block, dict) and block.get("type") == "text"
        ).strip()

        if not text:
            return {
                **self._failure("EMPTY_CONTENT", f"stop_reason={stop_reason}, текстовых блоков нет.", status),
                "stop_reason": stop_reason,
                "model": data.get("model"),
            }

        usage = data.get("usage") or {}
        return {
            "proposed": True,
            "text": text,
            "model": data.get("model"),
            "stop_reason": stop_reason,
            "http_status": status,
            "error": None,
            "error_detail": None,
            "usage": {
                "input_tokens": usage.get("input_tokens"),
                "output_tokens": usage.get("output_tokens"),
            },
            "timestamp": time.time(),
        }
