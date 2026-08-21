# Why_Ai — Саморазвивающаяся Мультиагентная Система (Self-Evo Framework)

> **Архитектурный стандарт:** Ouroboros · Hierarchy v3 · Claudexor Multi-Model Quorum · FastMCP Gateway · Immutable Supervisor (Zone P/R)

---

## 1. Топология и структура проекта

Каталог `Why_Ai` представляет собой очищенное, каноническое рабочее пространство проекта:

```
Why_Ai/
├── Supervisor/                        # Zone P/R (Неизменяемый пол безопасности)
│   ├── launcher.py                    # Менеджер процессов и обработчик /panic (Exit Code: 10)
│   ├── classify_diff.py               # Детерминированный классификатор риска (MAX_RISK_WINS)
│   ├── miniyaml.py                    # Безинсталляционный YAML-парсер
│   ├── WorkspaceOrchestrator.py       # Оркестратор Hierarchy v3 и фиксатор Git Windows CRLF
│   ├── SizeRatchets.py                # Аппаратные храповики размера (shrink-only)
│   ├── WorktreeSandbox.py             # Изолированные Git Worktrees для субагентов
│   ├── QuorumReviewer.py              # Мультимодельный кворум с правом вето (Angle Diversity)
│   ├── CommitGate.py                  # Reviewed Commit Gate (Preflight & Re-fingerprint SHA-256)
│   ├── EvolutionDaemon.py             # Фоновый демон рекурсивного саморазвития
│   ├── guard-policy-plane.sh          # Скрипт защиты зон файловой системы
│   └── Constitution/
│       └── BIBLE.md                   # 13 Неизменяемых Конституционных Принципов
│
├── Core/                              # Zone E (Изменяемый контур задач и рантайм)
│   ├── server.py                      # Daemon Control Plane API (127.0.0.1:8765, REST & SSE)
│   ├── ContextFit.py                  # Менеджер памяти на основе графа импортов (AST)
│   ├── MetaOverPatch.py               # Анализ паттернов сбоев (failures.jsonl)
│   ├── PolicyDriftVector.py           # Векторный дельта-анализ дрейфа политик
│   ├── SummaryChunker.py              # Иерархический Summary-Augmented чанкер для RAG
│   └── failures.jsonl                 # Структурированный реестр сбоев
│
├── Tool/                              # Tool Layer (Инструменты и коннекторы)
│   ├── mcp_server.py                  # FastMCP RPC Server (@mcp.tool)
│   ├── mcp_config.json                # Манифест конфигурации MCP
│   └── skills/                        # 9 инженерных манифестов (spec, plan, build, test, review, webperf, code-simplify, ship, using-agent-skills)
│
├── Eye/                               # Eye Layer (Интерфейс, телеметрия и мониторинг)
│   ├── dashboard.html                 # Автономный веб-дашборд со стримингом SSE и Time Travel
│   ├── Dashboard.tsx                  # React 18 модульный компонент дашборда
│   └── TelemetryDock.tsx              # Компонент телеметрии
│
├── tests/                             # Доказательное тестирование (32 юнит-теста)
├── docs/                              # Каноническая документация и ТЗ
├── run_mvp.py                         # Главный суверенный входной узел
├── run.ps1                            # PowerShell скрипт быстрого запуска
└── run.bat                            # Windows Batch файл запуска
```

---

## 2. Быстрый старт и запуск

### Запуск полного стека MVP:
```powershell
# Из каталога Why_Ai:
python run_mvp.py
# Или через PowerShell:
.\run.ps1
```

При старте система:
1. Выполняет криптографическую самопроверку и прогоняет 100% юнит-тестов.
2. Поднимает Supervisor и Daemon API на `http://127.0.0.1:8765`.
3. Открывает интерактивный веб-дашборд `dashboard.html`.

### Только самопроверка (CI / Self-Check):
```bash
python run_mvp.py --self-test
```

### Запуск полного набора доказательных тестов:
```bash
python -m unittest discover -s tests -p "test_*.py" -v
```

---

## 3. Ключевые инварианты

1. **Rule of Max Risk:** Вложенная политика проекта может только сужать права, но не расширять их.
2. **Angle Diversity:** Право вето любой модели (Claude 3.7, GPT-4o, DeepSeek-R1) блокирует слияние.
3. **Shrink-Only:** Кодовая база защищена от раздувания храповиками `SizeRatchets.py`.
4. **Out-of-Band /PANIC:** Экстренная остановка с кодом 10 выполняется в абсолютный обход LLM.
