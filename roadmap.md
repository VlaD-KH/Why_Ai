# Project Roadmap: Self-Evolving AI Architecture (Self-Evo Framework)

## Overview & Milestones

Дорожная карта перехода системы от статического управляемого каркаса к полностью автономному контуру саморазвития (`[self_evo]`).

---

## Phase 1: Static Guardrails & Skills Integration (Завершено 100%)
*Цель:* Развертывание неизменяемого скелета Supervisor, интеграция инженерных навыков `addyosmani/agent-skills`, настройка статических барьеров безопасности и модульного UI.

- [x] **1.1. Базовая топология каталогов и суверенное зонирование:** `/Supervisor` (Zone P/R) и `/Core` (Zone E).
- [x] **1.2. Конституция и Инварианты:** 13 принципов безопасности в `/Supervisor/Constitution/BIBLE.md`.
- [x] **1.3. Детерминированный классификатор рисков в Supervisor:** `Supervisor/classify_diff.py` с каскадным $\max(\text{Risk})$ и `--self-check`.
- [x] **1.4. Динамический оркестратор Hierarchy v3:** `Supervisor/WorkspaceOrchestrator.py` с фиксацией Windows Git CRLF (`core.autocrlf false`, `core.eol lf`, `core.quotepath false`).
- [x] **1.5. Аппаратные храповики размера:** `Supervisor/SizeRatchets.py` по правилу `shrink-only`.
- [x] **1.6. Движок Meta-over-Patch:** `Core/MetaOverPatch.py` для анализа паттернов сбоев.
- [x] **1.7. Полноценный FastMCP сервер:** `Tool/mcp_server.py` с декораторами `@mcp.tool` и JSON-RPC транспортом.
- [x] **1.8. Модульный адаптивный интерфейс:** `Eye/Dashboard.tsx` и `dashboard.html` с интерактивными инспекторами.

---

## Phase 2: Worktree Isolation & Multi-Model Quorum (Завершено 100%)
*Цель:* Полная изоляция процесса кодогенерации и независимый кросс-модельный аудит перед слиянием.

- [x] **2.1. Изолированные песочницы субагентов (`Supervisor/WorktreeSandbox.py`):**
  - Автоматическое порождение и очистка эфемерных `Git Worktrees` в каталоге `worktrees/<task_id>/`.
  - Принудительная изоляция и локальная конфигурация `core.autocrlf false`, `core.eol lf`.
- [x] **2.2. Мультимодельный кворум арбитража (`Supervisor/QuorumReviewer.py`):**
  - Кросс-модельный аудит по 3 независимым проекциям (Claude 3.7 Sentinel, GPT-4o Functional, DeepSeek-R1 Bloat) с правилом вето `Angle Diversity`.
- [x] **2.3. Шлюз коммитов и двухэтапное хэширование (`Supervisor/CommitGate.py`):**
  - Двухэтапная проверка SHA-256 (`Preflight Fingerprint` $\rightarrow$ `Quorum` $\rightarrow$ `Re-fingerprint`).
  - Применение трехстороннего слияния (`3-Way Auto-Merge`) исключительно ядром Supervisor.
- [x] **2.4. Интеграция мета-навыка using-agent-skills (`Tool/skills/using-agent-skills/SKILL.md`):**
  - Автоматическое дерево диспетчеризации навыков и правило `Surface Assumptions`.

---

## Phase 3: Autonomous Recursive Loop Activation (Завершено 100% & АКТИВНО)
*Цель:* Активация непрерывной рекурсивной свободной эволюции, векторного анализа дрейфа политик и навигатора по версиям.

- [x] **3.1. Анализ дрейфа политик (`Core/PolicyDriftVector.py`):**
  - Векторное квантование и дельта-анализ эмбеддингов правил безопасности (Similarity & Drift Delta).
  - Автоматическое требование верификации человеком (Exit code 10) при всплеске расхождения.
- [x] **3.2. Фоновый демон свободной эволюции (`Supervisor/EvolutionDaemon.py`):**
  - Автономный контур рефакторинга кодовой базы в часы простоя.
  - Опрос `failures.jsonl` $\rightarrow$ изоляция в `WorktreeSandbox` $\rightarrow$ синтез патча $\rightarrow$ `QuorumReviewer` $\rightarrow$ `CommitGate` $\rightarrow$ запись в `SizeRatchets`.
- [x] **3.3. Векторизация нормативной базы (`Core/SummaryChunker.py`):**
  - Иерархический Summary-Augmented чанкинг для нормативно-правовых и архитектурных документов без потери контекста.
- [x] **3.4. Интерактивный навигатор по версиям и веткам (Time-Travel Explorer):**
  - Вкладка путешествия по версиям (`v1.0.0`, `v2.0.0`, `v3.0.0`, `sandbox/evo-*`) в `dashboard.html` с авто-воспроизведением эволюции.
- [x] **3.5. Доказательное тестирование всех трех фаз (30/30 PASS):**
  - 100% зеленых тестов во всех слоях за 1.587s.
