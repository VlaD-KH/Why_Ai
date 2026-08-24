# План реализации Фазы 4: Адаптивное ядро dVPN / Proxy-роутера Why_Ai

## Описание задачи и архитектурный контекст
Реализация промышленного мультипротокольного ядра dVPN / Proxy-роутера в рамках проекта Why_Ai. Модуль обеспечивает децентрализованную адаптивную маршрутизацию трафика, разделение на тарифные профили (Free/Premium), проактивный мониторинг качества узлов (Latency & Health Probing) с автоматическим мгновенным переключением при сбоях (Fail-Safe Fallback), а также интеграцию с FastMCP и дашбордом Telemetry Dock.

---

## Архитектура компонентов

```
+─────────────────────────────────────────────────────────────────────────+
|                         Why_Ai Control Plane / Eye                      |
|           (/api/dvpn/status, /api/dvpn/nodes, SSE /api/events/stream)   |
+────────────────────────────────────┬────────────────────────────────────+
                                     │
                                     ▼
+─────────────────────────────────────────────────────────────────────────+
|                 Why_Ai Core: dVPN Engine (Core/dvpn/)                   |
|                                                                         |
|  +───────────────────────+   +───────────────────────────────────────+  |
|  |     ProfileManager    |   |            RoutingEngine              |  |
|  |  (Free / Premium)     |   |   (Latency-based, Geo, Obfuscation)   |  |
|  +───────────┬───────────+   +───────────────────┬───────────────────+  |
|              │                                   │                      |
|              ▼                                   ▼                      |
|  +───────────────────────+   +───────────────────────────────────────+  |
|  |    ProtocolAdapter    |   |             HealthProber              |  |
|  | (WireGuard/VLESS/SS)  |   |    (Heartbeat, Jitter, Fallback)      |  |
|  +───────────────────────+   +───────────────────────────────────────+  |
+────────────────────────────────────┬────────────────────────────────────+
                                     │
                                     ▼
+─────────────────────────────────────────────────────────────────────────+
|                      Tool Layer: FastMCP Gateway                        |
|        (dvpn_get_status, dvpn_switch_node, dvpn_generate_config)        |
+─────────────────────────────────────────────────────────────────────────+
```

---

## Предлагаемые изменения

### 1. Модуль профилей и тарифных политик (`Core/dvpn/profiles.py`)
- Классы `UserTier` (`FREE`, `PREMIUM`, `ENTERPRISE`).
- `TierPolicy`:
  - **Free Tier:** Доступ к узлам сообщества, протоколы WireGuard / Shadowsocks, лимит пропускной способности, базовое шифрование.
  - **Premium Tier:** Выделенные высокоскоростные релеи, протоколы VLESS-XTLS Reality / Trojan с маскировкой под TLS, Kill-Switch, нулевое логирование, приоритетная полоса.
  - **Enterprise Tier:** Мульти-хоп (Double VPN / Onion-over-VPN), кастомные гео-маршруты.

### 2. Мультипротокольные адаптеры (`Core/dvpn/protocols.py`)
- `ProtocolConfig`: типизированные структуры генерации конфигов.
- Поддержка форматов:
  - **WireGuard**: приватный/публичный ключ, endpoint, allowed_ips, preshared_key, MTU.
  - **VLESS (XTLS Reality)**: UUID, server_name, public_key, short_id, spider_x.
  - **Shadowsocks (AEAD-2022)**: cipher (chacha20-poly1305 / aes-256-gcm), password, plugin (obfs/v2ray).

### 3. Детектор доступности и метрик узлов (`Core/dvpn/health_prober.py`)
- `NodeHealthProber`:
  - Асинхронная проверка TCP/TLS handshake latency, jitter и packet loss.
  - Экспоненциальное скользящее среднее (EMA) для оценки стабильности.
  - Автоматическая пометка узла `DEGRADED` / `OFFLINE` при превышении порога тайм-аута.

### 4. Адаптивный движок маршрутизации (`Core/dvpn/engine.py`)
- `AdaptiveDVPNRouter`:
  - Выбор оптимального узла по метрикам: $\text{Score} = w_1 \cdot \text{Latency} + w_2 \cdot \text{PacketLoss} + w_3 \cdot \text{Load}$.
  - **Fail-Safe Fallback**: при потере связи с активным узлом мгновенное переключение на резервный узел из пула того же или более высокого ранга за время $< 150\text{ms}$.
  - Учет политик Kill-Switch (запрет утечки пакетов в открытый интернет при переключении).

### 5. Интеграция с FastMCP (`Tool/connectors/dvpn_connector.py` & `Tool/mcp_server.py`)
- Регистрация MCP-инструментов:
  - `dvpn_get_router_status`: статус активного соединения, протокол, задержка, трафик.
  - `dvpn_list_nodes`: список доступных узлов с фильтрацией по стране и тарифу.
  - `dvpn_switch_node`: принудительное переключение на конкретный узел.
  - `dvpn_generate_client_config`: получение готового файла конфигурации (WireGuard `.conf` / VLESS URI).

### 6. Расширение Control Plane API (`Core/server.py`)
- REST эндпоинты:
  - `GET /api/dvpn/status` — текущий статус маршрутизатора.
  - `GET /api/dvpn/nodes` — список узлов и их метрик.
  - `POST /api/dvpn/switch_profile` — переключение тарифа Free/Premium.
  - `POST /api/dvpn/reconnect` — принудительный триггер Fallback переподключения.

### 7. Тестовое покрытие (`tests/test_dvpn_*.py`)
- `tests/test_dvpn_profiles.py`: валидация тарифных политик, квот и прав доступа.
- `tests/test_dvpn_protocols.py`: проверка корректности генерации конфигураций WireGuard, VLESS, Shadowsocks.
- `tests/test_dvpn_router.py`: тестирование алгоритма выбора узла, адаптивного Fallback при сбое и Kill-Switch.

---

## План верификации

### Автоматизированные тесты
- Запуск сьюта юнит-тестов: `python -m unittest discover -s tests -p "test_*.py"`
- Проверка всех тестовых сценариев (ожидается расширение с 54 до 65+ тестов, 100% Green).

### Интеграционная проверка через Browser UI
- Проверка отображения метрик dVPN узлов и переключения профилей в `dashboard.html`.
- Проверка вызовов API через Chrome DevTools.
