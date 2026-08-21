# Functional Specification & API Surface (function_list.md)

Спецификация интерфейсов, сигнатур CLI и схем данных всех компонентов Self-Evo Architecture.

---

## 1. Supervisor Layer CLI Interfaces (Zone P / R)

### 1.1. `Supervisor/launcher.py`
Менеджер жизненного цикла процессов агента и внеполосный обработчик сигналов остановки.

```bash
# Обычный запуск супервизора
python Supervisor/launcher.py --start --mode project

# Экстренная внеполосная остановка всех дочерних процессов (Exit Code: 10)
python Supervisor/launcher.py --panic-stop --reason "Violation of BIBLE.md invariant #3"

# Проверка статуса супервизора
python Supervisor/launcher.py --status
```

---

### 1.2. `Supervisor/classify_diff.py`
Детерминированный классификатор риска на основе `git diff` с формулой $\max(\text{Risk})$.

```bash
# Классификация рабочего дерева с пояснением зон
python Supervisor/classify_diff.py --repo . --explain

# Самопроверка структуры политик и поиск попыток опустить пол (Exit Code: 10 при ошибке)
python Supervisor/classify_diff.py --repo . --self-check --json

# Классификация конкретного списка путей
python Supervisor/classify_diff.py --repo . --paths src/api.py tests/test_api.py
```

---

### 1.3. `Supervisor/WorktreeSandbox.py`
Менеджер изолированных песочниц Git Worktrees для субагентов.

```bash
# Создание изолированной песочницы для задачи
python Supervisor/WorktreeSandbox.py --create task-101 --base-ref HEAD

# Список активных песочниц
python Supervisor/WorktreeSandbox.py --list

# Удаление и очистка песочницы
python Supervisor/WorktreeSandbox.py --remove task-101
```

---

### 1.4. `Supervisor/QuorumReviewer.py`
Мультимодельный кворум арбитража Claudexor с правом вето (Angle Diversity).

```bash
# Проведение кворума для файла диффа
python Supervisor/QuorumReviewer.py --diff-file patch.diff --files Core/utils.py tests/test_utils.py

# Тестирование наложения вето при нарушении безопасности
python Supervisor/QuorumReviewer.py --simulate-veto
```

---

### 1.5. `Supervisor/CommitGate.py`
Reviewed Commit Gate с двухэтапной проверкой SHA-256 и 3-Way Auto-Merge.

```bash
# Этап 1: Фиксация Preflight отпечатка и запуск кворума
python Supervisor/CommitGate.py --diff-file patch.diff

# Этап 2: Проверка Re-fingerprint и применение трехстороннего слияния
python Supervisor/CommitGate.py --diff-file patch.diff --preflight-hash sha256:<hash> --commit-msg "Auto-merged patch"
```

---

### 1.6. `Supervisor/EvolutionDaemon.py`
Фоновый демон непрерывной автономной рекурсивной эволюции ядра.

```bash
# Выполнить один шаг автономного цикла эволюции
python Supervisor/EvolutionDaemon.py --step --task-name routine-opt

# Проверить статус демона
python Supervisor/EvolutionDaemon.py --status
```

---

### 1.7. `Supervisor/WorkspaceOrchestrator.py`
Динамическая инверсия путей Hierarchy v3 и фиксация настроек Git.

```bash
# Переключение в режим проекта (Project ⊃ agent)
python Supervisor/WorkspaceOrchestrator.py --switch-mode project --project-name vanguard

# Переключение в режим агента (Agent ⊃ Project)
python Supervisor/WorkspaceOrchestrator.py --switch-mode agent

# Фиксация параметров Git (core.autocrlf false, core.eol lf, core.quotepath false)
python Supervisor/WorkspaceOrchestrator.py --harden-git
```

---

### 1.8. `Supervisor/SizeRatchets.py`
Механизм аппаратных храповиков размера (shrink-only).

```bash
# Запись базовых размеров файлов кодовой базы
python Supervisor/SizeRatchets.py --record-baseline

# Проверка файла на превышение порога раздувания
python Supervisor/SizeRatchets.py --check-file Supervisor/launcher.py
```

---

## 2. Core Runtime CLI Interfaces (Zone E)

### 2.1. `Core/PolicyDriftVector.py`
Векторный анализ семантического дрейфа политик безопасности.

```bash
# Оценка дрейфа между базовой и кандидатной политикой
python Core/PolicyDriftVector.py --base-file .ai-loop/policy/root_policy.yaml --candidate-file new_policy.yaml

# Симуляция опасного дрейфа правил (Exit Code: 10)
python Core/PolicyDriftVector.py --simulate-drift
```

---

### 2.2. `Core/SummaryChunker.py`
Иерархическое разбиение документации и Конституции без потери контекста.

```bash
# Чанкинг markdown-документа
python Core/SummaryChunker.py --file Supervisor/Constitution/BIBLE.md
```

---

### 2.3. `Core/ContextFit.py`
Менеджер памяти на основе анализа графа импортов (`import-graph centrality`).

```bash
# Оценка графовой связности файлов проекта
python Core/ContextFit.py --analyze --repo .

# Сжатие контекста на заданный дефицит токенов
python Core/ContextFit.py --compact --deficit 4000
```

---

### 2.4. `Core/MetaOverPatch.py`
Анализ паттернов сбоев в `failures.jsonl` и планирование архитектурного рефакторинга.

```bash
# Анализ частоты сбоев по типам и принципам Конституции
python Core/MetaOverPatch.py --analyze

# Генерация плана структурного рефакторинга ядра
python Core/MetaOverPatch.py --generate-refactor-plan
```

---

## 3. Tool & FastMCP Server Interfaces

### 3.1. `Tool/mcp_server.py`
Полнофункциональный FastMCP RPC сервер.

```bash
# Вывод списка зарегистрированных инструментов с JSON-схемами
python Tool/mcp_server.py --list-tools

# Вызов инструмента через CLI
python Tool/mcp_server.py --call-tool github_create_draft_pr --args '{"title": "Test PR", "body": "Description", "head_branch": "feature/test"}'

# Запуск в режиме стандартного потока stdio для IDE/агентов
python Tool/mcp_server.py --serve-stdio
```

---

## 4. Eye UI Dashboard Interfaces

### 4.1. `Eye/Dashboard.tsx` & `dashboard.html`
Интерфейс с поддержкой:
1. Signal Canvas (Топология узлов и потоков сигналов).
2. Roadmap Milestones (Фазы 1, 2, 3 со 100% выполнением).
3. Live TODO Matrix (Интерактивный статус чек-листа задач).
4. **Time Travel Explorer** (Интерактивное путешествие по версиям `v1.0.0`, `v2.0.0`, `v3.0.0`, `sandbox/evo-*` и воспроизведение эволюции).
5. `relised_later` Inspector (Спецификации Что, Зачем, Где, Как, Фаза).
