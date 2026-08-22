#!/usr/bin/env python3
"""
Модуль: Core/MetaOverPatch.py
Назначение: Анализ реестра сбоев failures.jsonl и реализация принципа Meta-over-Patch.
Архитектурный слой: Core (Зона E - Mutable Task Runtime).
Инвариант: Устранение системных первопричин сбоев через рефакторинг ядра вместо локальных костылей.
"""

import argparse
import datetime
import json
import logging
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List, Any, Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] [META-PATCH] %(message)s")
logger = logging.getLogger("MetaOverPatch")


class MetaOverPatchEngine:
    """
    Движок рекурсивного анализа паттернов сбоев.
    """

    def __init__(self, workspace_root: Optional[Path] = None) -> None:
        self.workspace_root = (workspace_root or Path.cwd()).resolve()
        self.failures_file = self.workspace_root / "Core" / "failures.jsonl"

    def record_failure(self, failure_type: str, root_cause: str, principle_violated: int, resolution: str) -> Dict[str, Any]:
        """Запись нового инцидента в append-only реестр."""
        record = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "failure_type": failure_type,
            "root_cause": root_cause,
            "principle_violated": principle_violated,
            "resolution": resolution,
        }
        with open(self.failures_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        logger.info(f"Сбой зафиксирован: {failure_type} (Принцип {principle_violated})")
        return record

    def load_failures(self) -> List[Dict[str, Any]]:
        """Чтение всех записей из failures.jsonl."""
        records: List[Dict[str, Any]] = []
        if self.failures_file.exists():
            with open(self.failures_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            records.append(json.loads(line))
                        except Exception:
                            continue
        return records

    def analyze_patterns(self) -> Dict[str, Any]:
        """Анализ частоты сбоев и выявление системных уязвимостей."""
        failures = self.load_failures()
        type_counts = Counter(f.get("failure_type", "UNKNOWN") for f in failures)
        principle_counts = Counter(f.get("principle_violated", 0) for f in failures)

        # Выявление топ-паттернов, требующих Meta-рефакторинга
        meta_candidates = []
        for ftype, count in type_counts.items():
            if count >= 1:
                meta_candidates.append({
                    "failure_type": ftype,
                    "occurrences": count,
                    "recommendation": f"Рефакторинг контура оркестрации для предотвращения {ftype}",
                })

        return {
            "total_failures_recorded": len(failures),
            "distribution_by_type": dict(type_counts),
            "distribution_by_principle": dict(principle_counts),
            "meta_refactor_candidates": meta_candidates,
        }

    def generate_refactor_plan(self) -> Dict[str, Any]:
        """Формирование плана структурного рефакторинга ядра на основе опыта."""
        analysis = self.analyze_patterns()
        plan_steps = []
        for i, candidate in enumerate(analysis["meta_refactor_candidates"], 1):
            plan_steps.append({
                "step": i,
                "target_module": "Supervisor/launcher.py" if "PANIC" in candidate["failure_type"] else "Tool/skills/",
                "objective": candidate["recommendation"],
                "metric": f"Снижение частоты {candidate['failure_type']} до 0",
            })

        return {
            "title": "Experience-Driven Architectural Refactor Plan",
            "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "steps": plan_steps,
            # Сигнал, который эта функция вычисляет (analyze_patterns), но
            # раньше не возвращала: IdempotencyGate читает именно эти два
            # поля (Принцип 12 — привязка к реальным сбоям), и без них видел
            # нули при трёх реально зафиксированных сбоях — план всегда
            # отклонялся, кроме как через --force.
            "total_failures": analysis["total_failures_recorded"],
            "patterns": analysis["meta_refactor_candidates"],
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Meta-over-Patch Failure Pattern Engine")
    parser.add_argument("--analyze", action="store_true", help="Анализ реестра сбоев")
    parser.add_argument("--generate-refactor-plan", action="store_true", help="Сгенерировать план рефакторинга")
    parser.add_argument("--record", action="store_true", help="Записать новый сбой")
    parser.add_argument("--type", type=str, default="CUSTOM_FAILURE", help="Тип сбоя")
    parser.add_argument("--cause", type=str, default="Unspecified cause", help="Первопричина")
    parser.add_argument("--principle", type=int, default=1, help="Номер нарушенного принципа Конституции")
    parser.add_argument("--resolution", type=str, default="Manual fix", help="Резолюция")

    args = parser.parse_args()
    engine = MetaOverPatchEngine()

    if args.record:
        rec = engine.record_failure(args.type, args.cause, args.principle, args.resolution)
        print(json.dumps(rec, indent=2, ensure_ascii=False))
        return 0

    if args.generate_refactor_plan:
        plan = engine.generate_refactor_plan()
        print(json.dumps(plan, indent=2, ensure_ascii=False))
        return 0

    if args.analyze:
        analysis = engine.analyze_patterns()
        print(json.dumps(analysis, indent=2, ensure_ascii=False))
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
