---
name: test
description: "Prove it works with verifiable test evidence. Tests are proof only after observed failing. /test, запустить тесты, верификация TDD"
---

# /test — Verification & Proof of Falsification Phase

## Purpose
Доказать корректность реализации через автоматические тесты по принципу фальсификации (Red-Green TDD).

## Operating Principles
1. **Tests Are Proof:** Тест, который был только зеленым, доказывает лишь то, что он зеленый.
2. **Proof of Falsification:** Тест обязан быть зафиксирован падающим на сломанной реализации с сохранением вывода ошибки в лог.
3. **No Mixed Diffs:** Тесты и продуктовый код не коммитятся в одном диффе (эскалация риска).

## Steps
1. **Red Phase:** Запустить тест на неверной реализации и записать реальный вывод падения.
2. **Green Phase:** Применить корректную реализацию и зафиксировать прохождение всех тестов.
3. **Refactor & Coverage:** Проверить покрытие граничных случаев.
