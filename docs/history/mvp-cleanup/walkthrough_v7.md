# Why_Ai v1.1.0-Gold — Full Code Review & MVP Launch Report

## 1. Cleanup Summary (Очистка проекта)

### Удалённые артефакты
| Артефакт | Причина удаления |
|---|---|
| `__pycache__/` × 5 каталогов (35 `.pyc`) | Скомпилированный кэш — регенерируется автоматически |
| `.supervisor_pids.json` | Временный файл PID предыдущей сессии |
| `dashboard.html` (корень) | Дубликат `Eye/dashboard.html` — нарушал каноническую топологию |
| `docs/self_review.txt` | Устаревший черновик ревью |

### Переименованные / Архивированные
| Исходное имя | Новое имя | Причина |
|---|---|---|
| `docs/#Обновленная...` | `docs/Обновленная...` | Символ `#` в имени файла вызывает проблемы экранирования |
| `docs/todo.md` | `docs/legacy_todo_audit.md` | Устаревший первичный чеклист, замещён актуальным `todo.md` в корне |

### Созданные инфраструктурные файлы
| Файл | Назначение |
|---|---|
| `.ai-loop/policy/protected_paths.yaml` | Локальная политика защиты зон безопасности (Hierarchy v3 Guard) |
| `.ai-loop/policy/risk_classification.yaml` | Классификация рисков изменений по формуле MAX |
| `.gitignore` | Исключение `__pycache__/`, `*.pyc`, `.supervisor_pids.json`, `worktrees/*` |

---

## 2. Конфигурационные изменения

### `why_ai_config.yaml`
- `active_mode`: `self_evo` → **`prod_evo`** (фокус на продукте)
- `background_consciousness.enabled`: `true` → **`false`** (SIGTERM фонового демона)
- `swarm_visualizer.enabled`: **`true`** (SSE-телеметрия остаётся активной)

### `Core/server.py`
- Путь к `dashboard.html` обновлён: **`Eye/dashboard.html`** (канонический) с fallback на корень

---

## 3. Тестовое покрытие (Post-Cleanup)

```
Ran 54 tests in 2.078s
OK (54/54 PASS, 0 Failures, 0 Errors)
```

---

## 4. Каноническое дерево проекта (Post-Cleanup)

```text
Why_Ai/
├── .ai-loop/policy/                 ← [NEW] Hierarchy v3 Guard
│   ├── protected_paths.yaml
│   └── risk_classification.yaml
├── .gitignore                       ← [NEW]
├── .ai_workspace_state.json
├── .size_ratchets.json
├── CODEOWNERS
├── README.md
├── why_ai_config.yaml               ← [UPDATED] prod_evo mode
├── run_mvp.py                       ← Master Entrypoint
├── run.bat / run.ps1
├── todo.md                          ← Актуальная матрица задач
├── roadmap.md
├── function_list.md
│
├── Core/                            ← Zone E (Mutable Runtime)
│   ├── ContextFit.py
│   ├── MetaOverPatch.py
│   ├── PolicyDriftVector.py
│   ├── SummaryChunker.py
│   ├── server.py                    ← [UPDATED] Eye/ dashboard path
│   ├── identity.md                  ← Pinned: true
│   ├── scratchpad.md
│   └── failures.jsonl
│
├── Supervisor/                      ← Zone P/R (Immutable Floor)
│   ├── CommitGate.py
│   ├── EvolutionDaemon.py
│   ├── QuorumReviewer.py
│   ├── SizeRatchets.py
│   ├── WorkspaceOrchestrator.py
│   ├── WorktreeSandbox.py
│   ├── classify_diff.py
│   ├── guard-policy-plane.sh
│   ├── launcher.py
│   ├── miniyaml.py
│   └── Constitution/BIBLE.md
│
├── Tool/                            ← Инфраструктурные коннекторы
│   ├── mcp_server.py
│   ├── mcp_config.json
│   ├── connectors/
│   │   ├── github_connector.py
│   │   ├── postgres_connector.py
│   │   └── telegram_connector.py
│   └── skills/ (9 SKILL.md)
│
├── Eye/                             ← Зона наблюдаемости
│   ├── dashboard.html               ← [CANONICAL] Единственная копия
│   ├── Dashboard.tsx
│   └── TelemetryDock.tsx
│
├── tests/                           ← 17 тестовых модулей
│   └── test_*.py (54 unit tests)
│
├── docs/                            ← Нормативная база (11 документов)
│   └── legacy_todo_audit.md         ← [ARCHIVED]
│
└── worktrees/                       ← Эфемерные песочницы (пустая)
```

---

## 5. MVP Launch Status

| Компонент | Статус |
|---|---|
| Policy Guard (`.ai-loop/policy/`) | ✅ Создан и заполнен |
| Config (`why_ai_config.yaml`) | ✅ Обновлён на `prod_evo` |
| Unit Tests (54/54) | ✅ All PASS |
| Daemon API (`127.0.0.1:8765`) | ✅ Запущен, `/api/status` → 200 |
| Dashboard (`Eye/dashboard.html`) | ✅ Обслуживается по `/` |
| Browser UI Auto-Test | 🔄 В процессе |
