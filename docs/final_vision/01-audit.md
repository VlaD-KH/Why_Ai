# 01 — Аудит: что заявлено против того, что есть

**Дата:** 2026-08-21 · **Метод:** запуск кода, а не чтение документов
(`unittest`, `node --check`, `python -c "import ..."`, `classify_diff.py`, живые вызовы).
**Отпечаток политики на момент аудита:** `sha256:742f2e15…76fd`, `--self-check → ok: true`.

Правило чтения этого документа: **источник истины — код и `.ai-loop/policy/`,
а не `docs/`.** Всё в `docs/` — зона E, это предложения, а не правила.

---

## 1. Telegram-коннектор уже существует и является заглушкой

`Tool/connectors/telegram_connector.py` (127 строк) — чистый stdlib, **без единого
сетевого вызова**. Grep по `urllib|http.client|socket|requests|httpx|aiohttp|await`
по всем `Tool/connectors/*.py` и `Tool/mcp_server.py` даёт **0 совпадений**.

| Метод | Что делает на самом деле |
|---|---|
| `send_alert` (26–52) | возвращает захардкоженный `{"status":"SENT", "delivered": True}` |
| `send_panic_notification` (54–64) | форматирует текст → `send_alert` |
| `send_quorum_verdict` (66–80) | форматирует текст → `send_alert` |
| `handle_incoming_command` (82–126) | string-диспетчер с готовыми ответами |

Дополнительно:
- `__init__` (23–24) принимает **имя** переменной окружения и кладёт в атрибут.
  `os.getenv` в файле отсутствует — токен не читается никогда. `os` не импортирован.
- `message_id` фейковый — из `hashlib.md5(...)` (строка 40).
- **`handle_incoming_command` не имеет авторизации вообще**: нет параметра `user_id`,
  нет `allowed_operators`. И он **не зарегистрирован как MCP-инструмент**.
- Строка 99 содержит протухшую константу `"Tests: 52/52 PASS"` (фактически 76).
  Такая же протухшая константа в `Core/server.py:120` — `"32/32 PASS"`.

Зарегистрировано в `Tool/mcp_server.py` ровно 3 инструмента (258–273):
`telegram_send_alert`, `telegram_send_panic_notification`, `telegram_send_quorum_verdict`.
В `Tool/mcp_config.json` записи `telegram` **нет** — там `github`, `postgres`,
`slack`, `filesystem_sandbox`, причём `slack` описан как канал для `/panic`.

---

## 2. Предложенная спецификация — не инкремент, а несовместимая замена

### 2.1. Не компилируется

В `docs/(Telegram Connector)…md` буквально:

```python
self.allowed_operators =   # Доверенные ID
```

**SyntaxError на этапе импорта** — модуль не загрузится, MCP-сервер не стартует.
На этом значении держится единственная защита (`if user_id not in
connector.allowed_operators`). Даже «починка» на `= []` даёт отказ всем.
Обещанное в Части II чтение `allowed_operators` из `why_ai_config.yaml` в коде
отсутствует — там нет ни `yaml`, ни чтения конфига.

### 2.2. Хук в `launcher.py` не запустится и вставляется в несуществующую функцию

Блок импортов хука: `subprocess, httpx, json, logging, datetime`. Далее
используются `asyncio.run(...)` (2×) и `sys.exit(10)` (2×) → **NameError**.
В самом `Supervisor/launcher.py` есть `sys` и `subprocess`, но **нет `asyncio`**.

Функции `run_reviewed_commit_gate`, куда предлагается встроить хук,
**не существует**. `Supervisor/launcher.py` (141 строка) содержит только
`class SupervisorLauncher` (`panic_stop`, `start_runtime`, `get_status`) и `main()`.
Логика гейта живёт в `Supervisor/CommitGate.py` — `class ReviewedCommitGate`.

### 2.3. Четыре точки интеграции, которых не существует

Фактические маршруты `Core/server.py` (428 строк):

**GET:** `/`, `/api/status`, `/api/swarm/tasks`, `/api/identity`, `/api/config`,
`/api/dvpn/status`, `/api/dvpn/nodes*`, `/api/tests`, `/api/events/stream`
**POST:** `/api/panic`, `/api/worktrees/prune`, `/api/evolve`, `/api/mode`,
`/api/sync_db`, `/api/dvpn/{connect,switch_profile,fallback}`

| Что вызывает спецификация | Реальность |
|---|---|
| `POST /api/mcp/telegram_send_alert` | **нет**; пространства `/api/mcp/*` не существует |
| `POST /api/control/panic` | **нет**; реальный эндпоинт — `POST /api/panic` |
| мост `Core/server.py` ↔ `Tool/mcp_server.py` | **нет**; server не импортирует mcp_server |
| `run_reviewed_commit_gate` | **нет** такой функции |

> **Самое опасное место всей спецификации.** Вызов
> `await client.post(".../api/control/panic")` **не проверяет код ответа**.
> Оператор получит сообщение «🚨 Инициируется Exit Code 10», функция вернёт
> `"PANIC_SIGNAL_PROPAGATED"`, а система **не остановится** — маршрут вернёт 404.
> Тихий ложноположительный результат на самом критичном по безопасности пути.

Обработчик `/status` в спецификации делает `GET /api/events/stream` с
`timeout=1.0`, но это **бесконечный SSE-поток** (`while True`, `: ping`) — обычный
GET всегда упрётся в таймаут. И даже в успешной ветке возвращается мок
(`52/52 PASS`, `deficit: 0`). Нужный эндпоинт — `GET /api/status`.

### 2.4. Конфликт фреймворков и сигнатур

- Спецификация создаёт **второй** MCP-сервер (`mcp = FastMCP("Why_Ai_Telegram_Gateway")`,
  `mcp.run()`), тогда как в репозитории уже есть собственный класс `FastMCPServer`
  (`Tool/mcp_server.py:39–187`) с транспортом `--serve-stdio`.
- Инструменты в спецификации `async def`, а `FastMCPServer.call_tool:115` вызывает
  хендлер **синхронно** — регистрация вернёт корутину вместо результата.
- Ломающее изменение сигнатуры: спец. `telegram_send_alert(level, source, message)`
  против реальной `(chat_id, message, priority)` → сломает
  `tests/test_mcp_connectors.py:110,132`.

### 2.5. Спецификация нарушает собственный инвариант

Часть IV.2 предлагает вписать литеральный токен
`"123456789:ABCDefGhIJKlmNoPQRsTUVwxyZ"` прямо в `Tool/mcp_config.json` —
при том что сама же провозглашает «Zero Hardcoded Secrets», а существующие записи
в этом файле корректно используют плейсхолдеры `"${GITHUB_TOKEN}"`.
Файл коммитится, **репозиторий публичный**.

---

## 3. Зависимости: инвариант stdlib-only реален

| Пакет | Установлен глобально | Используется проектом |
|---|---|---|
| `httpx` | 0.28.1 ✔ | нет |
| `mcp` | 1.29.0 ✔ | нет (свой `FastMCPServer`) |
| `pytest` | 9.0.2 ✔ | **нет** — везде `unittest` |
| `yaml` | 6.0.3 ✔ | только в `try/except` с fallback (`miniyaml.py`) |

**Манифестов зависимостей в репозитории нет ни одного** — ни `requirements.txt`,
ни `pyproject.toml`, ни `package.json`. То, что пакеты установлены, — свойство
глобального Python пользователя, а не проекта. `import httpx` сломает инвариант.

Про `pytest` отдельно: спецификация вызывает
`subprocess.run(["pytest", f"{worktree_path}/tests/"])` **без `cwd=`**. Тесты
импортируются от корня репозитория (`tests/*.py`: `ROOT_DIR = ...parent.parent`,
`from Tool.connectors...`). Из чужого CWD это даст ImportError → `returncode != 0`
→ **ложный CRITICAL-алерт и ложный `sys.exit(10)` на каждом прогоне гейта**.

---

## 4. Eye-слой: `.tsx` — мёртвый код

| Файл | Размер | Статус |
|---|---|---|
| `Eye/Dashboard.tsx` | 516 строк | **не собирается никем** |
| `Eye/TelemetryDock.tsx` | 251 строка | **не собирается никем** |
| `Eye/dashboard.html` | 165 KB | **живой UI** |

Ни `package.json`, ни `tsconfig.json`, ни бандлера, ни `node_modules` — поиск по
всему репозиторию пуст. Доказательства, что `.tsx` — макеты:
`TelemetryDock.tsx:1` импортирует `useEffect` и **ни разу не использует**; в обоих
файлах **ноль** `fetch(`, **ноль** `EventSource`, **ноль** `/api/`; состояние
захардкожено; `onTriggerPanic` — проп, который никто не передаёт; Tailwind-классы
при полном отсутствии Tailwind.

Реальный UI — рукописный vanilla HTML/CSS/JS без внешних скриптов, обращается к
`/api/events/stream`, `/api/evolve`, `/api/identity`, `/api/mode`, `/api/panic`,
`/api/swarm/tasks`, `/api/worktrees/prune`.

**Telegram в `Eye/` отсутствует полностью** — `window.Telegram`, `WebApp`,
`telegram-web-app` встречаются только в прозе `docs/`.

---

## 5. Политика: 7 из 10 путей агенту запрещены

| Путь | Зона | Риск | Решение |
|---|---|---|---|
| `Supervisor/{launcher,CommitGate,QuorumReviewer}.py` | R | CRITICAL | require_human |
| `Tool/connectors/telegram_connector.py` | R | CRITICAL | require_human |
| `Tool/mcp_server.py`, `Tool/mcp_config.json`, `why_ai_config.yaml` | I | HIGH | require_human |
| `Eye/telegram_mini_app.html`, `Eye/TelemetryDock.tsx` | E | LOW | **allow** |
| `tests/test_telegram_connector.py` | T | MEDIUM | **allow** |

Совокупный диффект всех 10 путей: **CRITICAL / require_human / exit 10**.

Тонкость, которую легко пропустить: **даже два разрешённых файла в одном коммите
требуют человека.** Пара `Eye/TelemetryDock.tsx` + `tests/test_telegram_connector.py`
даёт эскалацию `test_and_product_same_diff`: MEDIUM → HIGH → `require_human`.

### Хук в Supervisor заблокирован тремя независимыми механизмами

1. **Зона R** → CRITICAL → `require_human` (exit 10).
2. **Жёсткое вето кворума**, `Supervisor/QuorumReviewer.py:42`:
   ```python
   if clean_f.startswith("Supervisor/") or "BIBLE.md" in clean_f or "CODEOWNERS" in clean_f:
       violations.append(f"Попытка прямой модификации защищенного контура Zone P/R: {clean_f}")
   ```
   → `REJECTED_BY_QUORUM`, `CommitGate` → `can_merge: false`, exit 10.
3. **BIBLE, Принцип 1** (Суверенное разделение ядра): «Агент **не имеет прямого
   доступа на запись** к процессу и коду своего супервизора.»

Противоречие в документах реально, но одностороннее: `docs/MASTER PROMPT…md:16`
сам пишет «You cannot modify /Supervisor», а `docs/(Telegram Connector)…md:8`
допускает альтернативу — «`Supervisor/launcher.py` **или** `Core/server.py`».
Только `docs/https___github…txt:47–114` требует правки Supervisor. Приоритет
однозначен: `protected_paths.yaml` побеждает `docs/`.

---

## 6. Две дыры в Конституции

Полнотекстовый поиск по `BIBLE.md` (13 принципов):

- **Хранение секретов — не упомянуто вообще.** `секрет|токен|token|ключ|PII|credential|env`
  → 0 совпадений. Требование «Zero PII & Credentials Leak» существует **только**
  в `docs/` (зона E) и в обосновании матричной записи `risk_classification.yaml`.
  Конституционного статуса у него нет.
- **Сетевой доступ из ядра — не упомянут.** Ни одного принципа про исходящие
  вызовы, эндпоинты, вебхуки. Исходящий HTTP из `Supervisor/` блокируется зоной R
  и вето кворума, а **не текстом BIBLE**.

Обе дыры стоит закрыть отдельным решением человека, если интеграция пойдёт в работу.

---

## 7. Побочные находки, требующие человека

1. **`Supervisor/launcher.py:121,123` — `type="str"` вместо `type=str`.**
   CLI полностью нерабочий: `python Supervisor/launcher.py --status` падает с
   `ValueError: 'str' is not callable` ещё до разбора аргументов. То есть
   **внеполосный рубильник `--panic-stop` из командной строки не запускается вообще**;
   работает только классовый API через `Core/server.py`. Зона R — агент не чинит сам.
   *Это подрывает саму предпосылку «внеполосного управления», ради которого
   затевается Telegram-консоль.*
2. `Core/server.py:332` читает `ROOT_DIR / "failures.jsonl"`, тогда как файл лежит
   в `Core/failures.jsonl`. `why_ai_config.yaml` тоже указывает путь без каталога.
3. `do_OPTIONS` (`Core/server.py:89`) ставит `Access-Control-Allow-Origin: *`,
   а на `POST /api/panic` **нет никакой аутентификации**.
4. Поля `reviewed_by`, `reviewed_at`, `baseline_commit` в `protected_paths.yaml:22-24`
   до сих пор `TODO` — формально контур не подписан человеком.

---

## 8. Гигиена репозитория — исправлено в этом цикле

| Дефект | Было | Стало |
|---|---|---|
| Скилл `/build` потерян | `.gitignore:12` `build/` матчил `Tool/skills/build/` на любой глубине; на GitHub 8 скиллов вместо 9 | `/build/` — только корень; скилл вернулся |
| Runtime-файлы в git | `.ai_workspace_state.json`, `.size_ratchets.json`, `Core/failures.jsonl` менялись при каждом запуске | сняты с отслеживания + в `.gitignore` |
| Дубликат дашборда | корневой `dashboard.html` и `Eye/dashboard.html`, ~328 KB | файлы были байт-идентичны; корневой удалён, канонический `Eye/` |
| PII в публичном репозитории | 2 документа с Telegram ID оператора не были защищены | внесены в `.gitignore`, остаются локально |

Изменение `.gitignore` классифицировано как **зона P → CRITICAL → require_human**;
одобрено оператором явно в диалоге 2026-08-21.

---

## Итог

**Спецификация Telegram-интеграции неисполнима в текущем виде.** Не из-за
амбициозности, а по конкретным причинам: синтаксическая ошибка в защитном контуре,
четыре несуществующие точки интеграции, несовместимый MCP-фреймворк, тихий отказ
на пути `/panic`, нарушение stdlib-инварианта и требование правки зоны R,
запрещённой тремя независимыми механизмами.

При этом **цель спецификации достижима полностью** — существующих точек
расширения (`broadcast_event` + SSE, `Core/failures.jsonl`, возвращаемые значения
`CommitGate`/`QuorumReviewer`) достаточно, чтобы закрыть все четыре заявленных
триггера алертов, не тронув `Supervisor/` ни одной строкой. См. `02-architecture.md`.
