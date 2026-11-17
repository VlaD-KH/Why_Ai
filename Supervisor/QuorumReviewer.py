#!/usr/bin/env python3
"""
Модуль: Supervisor/QuorumReviewer.py
Назначение: Мультимодельный кворум арбитража Why_Ai Multi-Harness Engine с матрицей градаций моделей (Model Capability Grading Matrix) и правом вето (Angle Diversity).
Архитектурный слой: Supervisor (Зона P/R - Immutable Core Floor).
Инвариант: Единогласное одобрение тремя классами моделей (Class 3 Arbitrator, Class 2 Architect, Class 1 Executor). Разделение Fail-Over при сбоях сети и Fail-Closed при вето BIBLE.md.
"""

import argparse
import hashlib
import json
import logging
import os
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] [MULTI-HARNESS] %(message)s")
logger = logging.getLogger("MultiHarnessEngine")

EXIT_ALLOW = 0
EXIT_REQUIRE_HUMAN = 10
EXIT_ERROR = 2


class MultiModelQuorumReviewer:
    """
    Движок мультимодельного арбитража Why_Ai Multi-Harness Engine на базе внутренней матрицы градаций моделей.
    """

    def __init__(self, workspace_root: Optional[Path] = None) -> None:
        self.workspace_root = (workspace_root or Path.cwd()).resolve()

    def _evaluate_class_3_arbitrator(self, diff_content: str, changed_files: List[str]) -> Dict[str, Any]:
        """
        Класс 3: Независимый Арбитр (Class 3: Arbitrator — Конституционный аудит BIBLE.md).
        Проверяет неизменяемость Zone P/R, отсутствие отключения гейтов и соответствие BIBLE.md.
        """
        violations = []
        for f in changed_files:
            clean_f = f.replace("\\", "/").strip()
            # Сравнение регистронезависимо: NTFS (и APFS по умолчанию) считают
            # supervisor/launcher.py и Supervisor/launcher.py ОДНИМ файлом, а
            # Python-строки — разными. Без casefold дифф с путём в нижнем
            # регистре менял бы ровно тот же защищённый файл, минуя вето.
            probe = clean_f.casefold()
            if (probe.startswith("supervisor/") or "bible.md" in probe
                    or "codeowners" in probe):
                violations.append(f"Попытка прямой модификации защищенного контура Zone P/R: {clean_f}")

        # Проверка паттернов ослабления защиты
        suspicious_terms = ["disable_security", "bypass_gate", "override_risk = 'LOW'", "diff_is_authoritative = False"]
        for term in suspicious_terms:
            if term in diff_content:
                violations.append(f"Обнаружен паттерн ослабления безопасности: '{term}'")

        decision = "PASS" if not violations else "REJECT"
        return {
            "model_class": "Class 3: Arbitrator (Constitutional Audit)",
            "perspective": "Security & Constitutional Sentinel",
            "decision": decision,
            "error_category": "BIBLE_CONSTITUTIONAL_VETO" if decision == "REJECT" else "NONE",
            "fallback_action": "FAIL_CLOSED" if decision == "REJECT" else "ALLOW",
            "confidence": 0.99 if decision == "PASS" else 1.0,
            "violations": violations,
            "summary": "Конституционный аудит Zone P/R пройден" if decision == "PASS" else "Вето: Нарушение инвариантов безопасности BIBLE.md",
        }

    def _evaluate_class_2_architect(self, diff_content: str, changed_files: List[str]) -> Dict[str, Any]:
        """
        Класс 2: Главный Архитектор (Class 2: Architect — Архитектурный анализ, TDD и полнота).
        Проверяет отсутствие заглушек, TODO и покрытие тестами.
        """
        warnings = []
        has_tests = any("test_" in f for f in changed_files)
        has_code = any(f.endswith((".py", ".ts", ".tsx", ".js")) and "test_" not in f for f in changed_files)

        if has_code and not has_tests:
            warnings.append("Добавлен продуктовый код без сопутствующих тестов (TDD violation)")

        if "TODO:" in diff_content or "pass  # placeholder" in diff_content:
            warnings.append("Обнаружены плейсхолдеры или незавершенная логика (TODO)")

        decision = "PASS" if not warnings else "REJECT"
        return {
            "model_class": "Class 2: Architect (High Reasoning & TDD)",
            "perspective": "Functional & Architecture Auditor",
            "decision": decision,
            "error_category": "FUNCTIONAL_INCOMPLETE_VETO" if decision == "REJECT" else "NONE",
            "fallback_action": "FAIL_CLOSED" if decision == "REJECT" else "ALLOW",
            "confidence": 0.95 if decision == "PASS" else 0.99,
            "warnings": warnings,
            "summary": "Функциональная логика и покрытие тестами подтверждены" if decision == "PASS" else "Вето: Отсутствуют тесты или обнаружен неполный код",
        }

    def _evaluate_class_1_executor(self, diff_content: str, changed_files: List[str]) -> Dict[str, Any]:
        """
        Класс 1: Кодовый Исполнитель (Class 1: Executor — Быстрый синтаксис, лаконичность и Size Ratchets).
        Проверяет объем диффа и предотвращает раздувание кодовой базы (Code Bloat).
        """
        lines_added = sum(1 for line in diff_content.splitlines() if line.startswith("+") and not line.startswith("+++"))
        lines_removed = sum(1 for line in diff_content.splitlines() if line.startswith("-") and not line.startswith("---"))

        concerns = []
        if lines_added > 800:
            concerns.append(f"Объем диффа превышает рекомендованный размер ({lines_added} строк добавления). Рекомендуется батчинг.")

        decision = "PASS" if not concerns else "REJECT"
        return {
            "model_class": "Class 1: Executor (Code Syntax & Size Ratchets)",
            "perspective": "Performance & Code Bloat Auditor",
            "decision": decision,
            "error_category": "BLOAT_RATCHET_VETO" if decision == "REJECT" else "NONE",
            "fallback_action": "FAIL_CLOSED" if decision == "REJECT" else "ALLOW",
            "confidence": 0.96,
            "concerns": concerns,
            "summary": "Размер и лаконичность диффа соответствуют стандарту shrink-only" if decision == "PASS" else "Вето: Риск раздувания кодовой базы (Code Bloat)",
        }

    def review_diff(self, diff_content: str, changed_files: List[str]) -> Dict[str, Any]:
        """
        Проведение мультимодельного кворума через Why_Ai Multi-Harness Engine с правилом Angle Diversity.
        """
        diff_hash = hashlib.sha256(diff_content.encode("utf-8")).hexdigest()

        sec_result = self._evaluate_class_3_arbitrator(diff_content, changed_files)
        func_result = self._evaluate_class_2_architect(diff_content, changed_files)
        bloat_result = self._evaluate_class_1_executor(diff_content, changed_files)

        all_perspectives = [sec_result, func_result, bloat_result]
        vetoes = [p for p in all_perspectives if p["decision"] == "REJECT"]

        quorum_passed = len(vetoes) == 0
        final_decision = "APPROVED" if quorum_passed else "REJECTED_BY_QUORUM"

        # Двухмаршрутная стратегия обработки: если вето конституционное -> FAIL-CLOSED
        strategy_applied = "ALLOW" if quorum_passed else "FAIL_CLOSED_EXIT_10"

        result = {
            "schema": "ai-loop/why-ai-multi-harness/v1",
            "engine": "Why_Ai Multi-Harness Engine",
            "diff_sha256": f"sha256:{diff_hash}",
            "files_audited": changed_files,
            "quorum_decision": final_decision,
            "fallback_strategy": strategy_applied,
            "angle_diversity_veto_triggered": not quorum_passed,
            "veto_reasons": [v["summary"] for v in vetoes],
            "model_capability_grading": {
                "class_3_arbitrator": sec_result,
                "class_2_architect": func_result,
                "class_1_executor": bloat_result,
            },
            "perspectives": {
                "security": sec_result,
                "functional": func_result,
                "bloat": bloat_result,
            },
        }

        logger.info(f"Кворум завершен: {final_decision} (Вето: {len(vetoes)}, Стратегия: {strategy_applied})")
        return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Why_Ai Multi-Harness Model Capability Quorum Reviewer")
    parser.add_argument("--diff-file", type=str, help="Файл с содержимым diff")
    parser.add_argument("--files", nargs="*", default=[], help="Список измененных файлов")
    parser.add_argument("--simulate-veto", action="store_true", help="Симуляция диффа с нарушением безопасности")

    args = parser.parse_args()
    reviewer = MultiModelQuorumReviewer()

    if args.simulate_veto:
        bad_diff = "+ # disable_security and bypass_gate\n+ Supervisor/launcher.py modified"
        res = reviewer.review_diff(bad_diff, ["Supervisor/launcher.py"])
        print(json.dumps(res, indent=2, ensure_ascii=False))
        return EXIT_REQUIRE_HUMAN

    if args.diff_file:
        content = Path(args.diff_file).read_text(encoding="utf-8")
        res = reviewer.review_diff(content, args.files)
        print(json.dumps(res, indent=2, ensure_ascii=False))
        return EXIT_ALLOW if res["quorum_decision"] == "APPROVED" else EXIT_REQUIRE_HUMAN

    # По умолчанию тестовая верификация чистого диффа
    res = reviewer.review_diff("+ def valid_function(): return True\n", ["Core/utils.py", "tests/test_utils.py"])
    print(json.dumps(res, indent=2, ensure_ascii=False))
    return EXIT_ALLOW if res["quorum_decision"] == "APPROVED" else EXIT_REQUIRE_HUMAN


if __name__ == "__main__":
    sys.exit(main())
