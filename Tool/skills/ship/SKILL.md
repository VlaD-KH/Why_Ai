---
name: ship
description: "Ship to production safely. Faster is safer with automated gates. /ship, подготовить релиз, открыть Draft PR"
---

# /ship — Release & Packaging Phase

## Purpose
Зафиксировать результаты прогона в журнале аудита, обновить долговременную память проекта и сформировать Draft Pull Request.

## Operating Principles
1. **Faster is Safer:** Автоматизированные, проверенные и небольшие релизы безопаснее редких массивных выкаток.
2. **Append-Only Ledger:** Хэш-цепочка `ledger.jsonl` обновляется атомарно с фиксацией SHA коммита.
3. **Human Merges Only:** Бот/агент никогда не мержит PR самостоятельно.

## Steps
1. **Обновление памяти:** Записать установленные факты в `.ai-loop/context.md`.
2. **Запись в журнал:** Вызвать `loop.py finish --run-id <id> --commit <sha>`.
3. **Открытие PR:** Создать Draft Pull Request через FastMCP GitHub коннектор и уведомить человека.
