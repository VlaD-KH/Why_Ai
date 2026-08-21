# scratchpad.md — Эфемерный Холст Рассуждений (CoT & Sub-Task Breakdown)

> **Статус:** Рабочая область текущей сессии.  
> **Очистка:** Обнуляется или архивируется при завершении макро-задачи / фиксации коммита.

---

## Текущая сессия:

### 1. Текущий контекст задачи:
- Реализация требований v1.1.0-Gold:
  - Модуль 1: Living Identity & Scratchpad (`identity.md`, `scratchpad.md`).
  - Модуль 2: Фоновое самосознание (EvolutionDaemon) + Idempotency Gate (Failure-Binding + Shrink-Only).
  - Модуль 3: Swarm Task-Tree Visualizer + Worktree Lifecycle Manager.
  - Матрица градаций моделей (Class 1 Executor, Class 2 Architect, Class 3 Arbitrator) в Why_Ai Multi-Harness Engine.

### 2. Шаги декомпозиции:
- [x] Создание `why_ai_config.yaml` с Feature Flags.
- [x] Создание `Core/identity.md` (pinned) и `Core/scratchpad.md`.
- [ ] Обновление `Core/ContextFit.py` с поддержкой pin-флагов для `identity.md`.
- [ ] Обновление `Supervisor/EvolutionDaemon.py` с Idempotency Gate.
- [ ] Обновление `Supervisor/WorktreeSandbox.py` с Worktree Lifecycle Manager.
- [ ] Обновление `Supervisor/QuorumReviewer.py` с 3-уровневой матрицей градаций и Fail-Over vs Fail-Closed.
- [ ] Добавление вкладки Swarm Task-Tree в `dashboard.html` и эндпоинта `/api/swarm/tasks` в `Core/server.py`.
- [ ] Доказательные тесты и прогон 100% сьюта.
