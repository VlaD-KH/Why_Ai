# Фактическое состояние на 2026-08-22 (коммит `11f37b3`)

Указатели «файл:что», не пересказ содержимого. Проверяйте запуском, не верьте
на слово — то же правило, что и в `CLAUDE.md`.

## (а) Сделано, реально работает, запушено

- **MCP-сервер** `Tool/mcp_server.py` — исправлен MCP-хендшейк (`initialize`),
  схема `inputSchema` вместо `parameters`. Зарегистрирован в scope `Why_Ai`
  (`claude mcp get why-ai-mcp` → Connected).
- **Control-plane ai-loop** — `.ai-loop/policy/{protected_paths,risk_classification}.yaml`
  на правильной схеме (зоны R/P/I/T/E), классификатор вендорен в
  `.ai-loop/bin/`, `--self-check` → `ok: true`.
- **Telegram-коннектор** `Tool/connectors/telegram_connector.py` — реальный
  транспорт (`urllib.request`), fail-closed авторизация операторов из ENV,
  экранирование MarkdownV2. 40 тестов, мутационно проверены.
- **Telegram Mini App** `Eye/telegram_mini_app.html` — vanilla JS, честная
  обработка `/panic` (проверяет реальный код ответа, не факт отправки).
  **Не отдаётся сервером** — маршрута в `Core/server.py` нет.
- **Дашборд** `Eye/dashboard.html` — фикс лживого подтверждения `/panic`
  (было: alert всегда «остановлено», без проверки ответа).
- **Храповики размера** — `Supervisor/SizeRatchets.py`
  (`check_file(persist=)`, `check_paths()`, `rebaseline()`) подключены к
  `Supervisor/CommitGate.py:stage_preflight()`. Принцип 10 BIBLE впервые
  реально принуждается.
- **IdempotencyGate** — `Core/MetaOverPatch.py:generate_refactor_plan()`
  теперь возвращает `patterns`/`total_failures`; раньше гейт всегда видел
  нули и отклонял всё кроме `--force`.
- **SIGTERM для `[prod_evo]`** — `Supervisor/EvolutionDaemon.py:enforce_mode_policy()`,
  вызывается как шаг 0 `run_evolution_cycle()`, до создания песочницы.
  `Supervisor/launcher.py:terminate_background()` реально шлёт SIGTERM.
- **Резолвер режима** — `Supervisor/WorkspaceOrchestrator.py:resolve_active_mode()`,
  единственный источник — `why_ai_config.yaml`. См. `decisions.md`.
- **Фикс бага**: PID-реестр в `launcher.py` резолвился от `cwd`, а не
  `workspace_root` — `SupervisorLauncher(workspace_root=ROOT_DIR)` (именно
  так вызывает `Core/server.py`) видел пустой список. Исправлено.
- **CommitGate.extract_changed_files()** — список файлов из заголовков
  реального диффа; раньше был захардкоженный литерал, скрывавший вето Zone P/R.
- 157/157 тестов, `run_mvp.py --self-test` → 0.

## (б) Задокументировано / спроектировано, НЕ реализовано

- **Swarm Task-Tree** — `Core/server.py:/api/swarm/tasks` отдаёт
  **выдуманных** агентов (`scout-01`, `child-01`), не связанных с реальным
  `WorktreeSandbox`. Флаг `swarm_visualizer` не читается нигде.
- **Telegram Фаза 2** — `Tool/connectors/telegram_bridge.py` **не
  существует**. Мост SSE→Telegram, long polling для входящих команд,
  честная обработка `/panic` через мост — всё спроектировано в
  `docs/final_vision/03-roadmap.md`/`04-todo.md`, код не писался.
- **Маршрут Mini App** в `Core/server.py` — не добавлен (зона R).
- **Self-evo конвейер** — по аудиту (`docs/final_vision/06-self-evo-audit.md`)
  работает 1 звено из 9. **Не реализовано**: предложитель (вызов модели —
  ноль вхождений в продакшен-коде), применитель (`CommitGate.verify_and_merge`
  всё ещё возвращает литерал, не делает git-операций), откат, подключение
  `.ai-loop/bin/ledger.py` (файл `.ai-loop/ledger.jsonl` не существует),
  автопополнение `Core/failures.jsonl` из реальных сбоев.
- **Runtime mode (light/advanced/pro) и propose/publish** — решение принято
  (`decisions.md`), код не начат.
- **Data-root вне репозитория** — решение принято, код не начат.
- **dVPN** (`Core/dvpn/`) — детерминированный симулятор: узлы захардкожены,
  ключи демо (`protocols.py`), нет сетевого I/O нигде. Решение «доводить
  или зафиксировать» — открыто.
- **`Project_dVPN/` как внешний модуль ранга 1** — не построен, вопрос
  возможно снят самим self-evo аудитом (см. `decisions.md`).

## (в) Карта — где что искать

| Что нужно | Файл |
|---|---|
| Рабочая память ai-loop (сжатая, 2 стр.) | `.ai-loop/context.md` |
| Правила зон/риска | `.ai-loop/policy/protected_paths.yaml`, `risk_classification.yaml` |
| Полный Telegram-цикл (аудит спецификации → архитектура → план) | `docs/final_vision/README.md` |
| Разбор self-evo цикла + сравнение с Ouroboros | `docs/final_vision/06-self-evo-audit.md` |
| Контракт проекта, язык, правила | `CLAUDE.md` (корень) |
| Обоснование Варианта 1 для храповиков | `docs/Вариант 1 check_file() со шлюзом.md` |
| Конституция, 15 принципов | `Supervisor/Constitution/BIBLE.md` |

## Живая проверка перед продолжением

```bash
python -m unittest discover -s tests -p "test_*.py"   # ожидается 157/157
python run_mvp.py --self-test                          # ожидается exit 0
python .ai-loop/bin/classify_diff.py --repo . --self-check   # ok: true
```
