# Walkthrough: Фаза 4 — Адаптивное ядро dVPN / Proxy-роутера Why_Ai

## 1. Обзор проделанной работы

В рамках реализации **Фазы 4** разработан и верифицирован промышленный мультипротокольный модуль dVPN / Proxy-маршрутизации с тарифным разделением (Free/Premium), проактивным мониторингом узлов и защитой от утечек (Kill-Switch).

---

## 2. Разработанные компоненты

### А. Тарифные профили и политики безопасности ([`Core/dvpn/profiles.py`](file:///c:/Users/Huawei/source/_Ai/Why_Ai/Core/dvpn/profiles.py))
- **`UserTier`**: `FREE`, `PREMIUM`, `ENTERPRISE`.
- **`TierPolicy`**:
  - **Free:** До 25 Mbps, WireGuard/Shadowsocks, без выделенных релеев, квота 10 GB/мес.
  - **Premium:** До 500 Mbps, WireGuard/VLESS-Reality/Shadowsocks/Trojan, выделенные релеи, обязательный Kill-Switch, безлимитный трафик.
  - **Enterprise:** До 2000 Mbps, Multi-hop, приоритет 10.0.
- **`TierManager`**: управление сессиями, динамическое переключение тарифов, контроль квот и разграничение прав доступа.

### Б. Мультипротокольные адаптеры ([`Core/dvpn/protocols.py`](file:///c:/Users/Huawei/source/_Ai/Why_Ai/Core/dvpn/protocols.py))
- **`WireGuardConfig`**: генерация валидного файла `.conf` (интерфейс, ключи, endpoint, allowed IPs, preshared key).
- **`VLESSConfig`**: генерация URI ссылки `vless://` со спецификацией **XTLS-Reality** (`flow=xtls-rprx-vision`, `pbk`, `sid`, `sni`).
- **`ShadowsocksConfig`**: генерация URI ссылки `ss://` с шифрованием AEAD 2022 (`chacha20-ietf-poly1305` / `2022-blake3-aes-256-gcm`).
- **`TrojanConfig`**: генерация URI ссылки `trojan://` с TLS ALPN.
- **`ProtocolFactory`**: фабричное создание типизированных конфигураций.

### В. Детектор качества и мониторинг узлов ([`Core/dvpn/health_prober.py`](file:///c:/Users/Huawei/source/_Ai/Why_Ai/Core/dvpn/health_prober.py))
- **`HealthProber`**:
  - Экспоненциальное сглаживание задержки: $\text{EMA}_t = \alpha \cdot Y_t + (1 - \alpha) \cdot \text{EMA}_{t-1}$.
  - Динамический расчет скоринга качества: $\text{Score} = \text{EMA\_Latency} \cdot 1.0 + \text{Loss}\% \cdot 15.0 + \text{Load}\% \cdot 0.5$.
  - Автоматические переходы статусов: `ONLINE` $\rightarrow$ `DEGRADED` $\rightarrow$ `OFFLINE`.

### Г. Адаптивный маршрутизатор ([`Core/dvpn/engine.py`](file:///c:/Users/Huawei/source/_Ai/Why_Ai/Core/dvpn/engine.py))
- **`AdaptiveDVPNRouter`**:
  - Оптимальный выбор узлов с учетом тарифа и гео-предпочтений.
  - **Fail-Safe Fallback**: мгновенное бесшовное переключение на резервный узел (**$<150\text{ms}$**) при деградации метрик.
  - **Kill-Switch**: изоляция трафика во время миграции туннеля.

### Д. FastMCP Коннектор ([`Tool/connectors/dvpn_connector.py`](file:///c:/Users/Huawei/source/_Ai/Why_Ai/Tool/connectors/dvpn_connector.py) & [`Tool/mcp_server.py`](file:///c:/Users/Huawei/source/_Ai/Why_Ai/Tool/mcp_server.py))
Зарегистрированы 6 инструментов FastMCP:
1. `dvpn_get_status` — телеметрия активного туннеля.
2. `dvpn_list_nodes` — список узлов с фильтрацией по тарифу/стране.
3. `dvpn_connect_node` — установление соединения.
4. `dvpn_switch_tier_profile` — динамическая смена тарифа.
5. `dvpn_trigger_fallback` — принудительный запуск Fallback.
6. `dvpn_get_client_config` — экспорт клиентского файла/URI.

### Е. REST Control Plane API ([`Core/server.py`](file:///c:/Users/Huawei/source/_Ai/Why_Ai/Core/server.py))
- `GET /api/dvpn/status`
- `GET /api/dvpn/nodes`
- `POST /api/dvpn/connect`
- `POST /api/dvpn/switch_profile`
- `POST /api/dvpn/fallback`

---

## 3. Результаты верификации

### Автоматизированные тесты
```text
Ran 70 tests in 1.998s

OK (70/70 PASS, 0 Failures, 0 Errors)
```
- `test_dvpn_profiles.py` (4 теста) — квоты, тарифы, права доступа.
- `test_dvpn_protocols.py` (4 теста) — WireGuard .conf, VLESS Reality URI, Shadowsocks URI, ProtocolFactory.
- `test_dvpn_router.py` (6 тестов) — QoS скоринг, EMA задержка, переключение узлов, Fallback $<150\text{ms}$.
- `test_daemon_server.py` — REST эндпоинты `/api/dvpn/*`.
- `test_mcp_connectors.py` — FastMCP RPC вызовы `dvpn_*`.

### Браузерная Live-верификация
- Подтверждена работоспособность кнопок переключения топологии `[prod_evo]` / `[self_evo]` в [`Eye/dashboard.html`](file:///c:/Users/Huawei/source/_Ai/Why_Ai/Eye/dashboard.html) (`window.setHierarchyMode`).
- Проверены вызовы dVPN API через живой браузер: успешное подключение пользователя тарифа Premium (`vless://` туннель к Франкфурту, задержка 14.2ms) и мгновенный Fallback на Амстердам при симуляции сбоя.
