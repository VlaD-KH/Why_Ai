---
name: plan
description: "Plan how to build it. Breaks accepted specifications into small, atomic tasks and commits. /plan, спланировать реализацию, декомпозиция задач"
---

# /plan — Architecture & Task Planning Phase

## Purpose
Декомпозировать утвержденную спецификацию на атомарные шаги с расчетом прогнозируемого риска для каждого шага.

## Operating Principles
1. **Small Atomic Tasks:** Один шаг плана = один атомарный коммит = одна семантическая причина изменения.
2. **Pre-Classification:** Для каждого шага заранее указывается ожидаемый уровень риска (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`).
3. **Cumulative Awareness:** Учитывать кумулятивный дифф всего прогона.

## Steps
1. **Декомпозиция:** Разбить задачу на последовательные батчи (Архитектура/БД $\rightarrow$ Логика $\rightarrow$ API $\rightarrow$ UI).
2. **Проектирование тестов:** Спланировать тесты для фальсификации (Red-Green TDD) для каждого нового модуля.
3. **Формирование plan.md:** Записать план в `.ai-loop/runs/<id>/plan.md`.
4. **Handoff:** Представить план пользователю для утверждения перед началом фазы `/build`.
