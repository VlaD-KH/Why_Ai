# Task Matrix & Acceptance Criteria (todo.md)

Детализированная матрица задач для развертывания ядра Self-Evo с измеримыми критериями приемки и статусом выполнения.

---

## 1. `/Supervisor` (Неизменяемое ядро, Зона P/R - Immutable Floor)
- [x] **TASK-SUP-01: Создание Конституции `BIBLE.md`**
  - *Критерий приёмки:* 13 неизменяемых принципов Ouroboros зафиксированы, файл защищен от записи.
- [x] **TASK-SUP-02: Разработка менеджера процессов `launcher.py`**
  - *Критерий приёмки:* Поддерживает флаг `--panic-stop`, выполняет внеполосное завершение дочерних агентов с кодом 10.
- [x] **TASK-SUP-03: Скрипт защиты зон `guard-policy-plane.sh`**
  - *Критерий приёмки:* Блокирует попытки записи в Supervisor и Root Policy, поддерживает безопасный онбординг политик проектов (`--allow-project-onboarding`).
- [x] **TASK-SUP-04: Детерминированный классификатор `classify_diff.py` в Supervisor**
  - *Критерий приёмки:* Вычисляет риск по фактическому `git diff`, объединяет политики по формуле $\max(\text{Risk})$, падает с кодом 10 на попытке опустить пол безопасности через `--self-check`.
- [x] **TASK-SUP-05: Динамический оркестратор `WorkspaceOrchestrator.py`**
  - *Критерий приёмки:* Реализует инверсию Hierarchy v3 (`Agent ⊃ Project` в `[self_evo]`, `Project ⊃ agent` в `[prod_evo]`) и фиксирует Git Windows инварианты (`core.autocrlf false`, `core.eol lf`, `core.quotepath false`).
- [x] **TASK-SUP-06: Аппаратные храповики размера `SizeRatchets.py`**
  - *Критерий приёмки:* Контролирует лимиты файлов по принципу `shrink-only` и блокирует раздувание кода (exit code 10).
- [x] **TASK-SUP-07: Изолированные песочницы `WorktreeSandbox.py`**
  - *Критерий приёмки:* Автоматически создает и очищает эфемерные `git worktrees` в `worktrees/<task_id>/` с `core.autocrlf false`.
- [x] **TASK-SUP-08: Мультимодельный кворум арбитража `QuorumReviewer.py`**
  - *Критерий приёмки:* Проводит независимый аудит по 3 проекциям (Security, Functional, Bloat) с правилом вето `Angle Diversity`.
- [x] **TASK-SUP-09: Шлюз коммитов `CommitGate.py`**
  - *Критерий приёмки:* Сравнивает Preflight SHA-256 с Re-fingerprint и применяет 3-Way Merge под контролем Supervisor.
- [x] **TASK-SUP-10: Фоновый демон свободной эволюции `EvolutionDaemon.py`**
  - *Критерий приёмки:* Автономно проводит полный цикл эволюции (анализ -> sandbox -> синтез -> кворум -> слияние).

---

## 2. `/Core` (Изменяемый рантайм, Зона E - Mutable Runtime)
- [x] **TASK-COR-01: Граф-менеджер контекста `ContextFit.py`**
  - *Критерий приёмки:* Вычисляет `import-graph centrality` файлов, возвращает сжатый контекст при вызове `ContextFit.py --compact --deficit <N>`.
- [x] **TASK-COR-02: Движок анализа сбоев `MetaOverPatch.py`**
  - *Критерий приёмки:* Анализирует `failures.jsonl` и формирует планы структурного рефакторинга ядра.
- [x] **TASK-COR-03: Анализатор семантического дрейфа политик `PolicyDriftVector.py`**
  - *Критерий приёмки:* Рассчитывает косинусную близость эмбеддингов правил и блокирует дрейф безопасности с кодом 10.
- [x] **TASK-COR-04: Иерархический чанкер базы знаний `SummaryChunker.py`**
  - *Критерий приёмки:* Генерирует Summary-Augmented фрагменты с сохранением родительского контекста для RAG.

---

## 3. `/Tool` (Навыки Agent-Skills и FastMCP)
- [x] **TASK-TOL-01: Установка набора `agent-skills`**
  - *Критерий приёмки:* В `/Tool/skills/` размещены 9 манифестов (`spec`, `plan`, `build`, `test`, `review`, `webperf`, `code-simplify`, `ship`, `using-agent-skills`).
- [x] **TASK-TOL-02: Полнофункциональный FastMCP сервер `Tool/mcp_server.py`**
  - *Критерий приёмки:* Реализованы декораторы `@mcp.tool`, генерация схем JSON-RPC и клиенты для GitHub, Postgres, Slack, Filesystem.

---

## 4. `/Eye` (Телеметрия, Модульный UI и Time-Travel)
- [x] **TASK-EYE-01: Модульный адаптивный интерфейс `Eye/Dashboard.tsx`**
  - *Критерий приёмки:* Реализован переключатель режимов Hierarchy v3, индикаторы SDLC и инспекторы модулей.
- [x] **TASK-EYE-02: Автономный интерактивный дашборд `dashboard.html` с Time-Travel**
  - *Критерий приёмки:* Веб-приложение с 5 вкладками (Signal Canvas, Roadmap, Live Matrix, Time Travel Timeline, relised_later Inspector) и авто-воспроизведением эволюции.

---

## 5. `/tests` (Доказательное тестирование)
- [x] **TASK-TST-01: Полный набор юнит-тестов (30/30 тестов)**
  - *Критерий приёмки:* Все 30 тестов пройдены (`OK`) за 1.587s с доказанным предварительным падением.
