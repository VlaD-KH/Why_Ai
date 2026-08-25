#!/usr/bin/env python3
"""
Unit tests for Core/MetaOverPatch.py
Verifies failure pattern analysis and refactor plan generation.

Фикстура — собственный временный каталог, а не рабочее дерево. Прежняя версия
брала MetaOverPatchEngine(workspace_root=Path(".")) и требовала >= 1 записи в
Core/failures.jsonl. Этот файл в .gitignore как runtime-состояние, поэтому на
свежем клоне его нет: тест краснел, run_mvp.py --self-test отдавал 10. Зелёный
статус в чекауте автора был артефактом неотслеживаемого файла на диске, а не
свойством кода — то есть тест проверял окружение разработчика, а не движок.
"""

import shutil
import tempfile
import unittest
from pathlib import Path

from Core.MetaOverPatch import MetaOverPatchEngine


def _make_registry(*failure_types: str) -> Path:
    """Временный workspace_root с реестром, набранным через публичный API движка.

    Записи создаются record_failure(), а не прямой записью в файл: иначе тест
    разошёлся бы с форматом, который движок реально пишет, и перестал бы его
    покрывать.
    """
    root = Path(tempfile.mkdtemp(prefix="metapatch-")).resolve()
    (root / "Core").mkdir(parents=True, exist_ok=True)
    engine = MetaOverPatchEngine(workspace_root=root)
    for i, failure_type in enumerate(failure_types):
        engine.record_failure(
            failure_type=failure_type,
            root_cause=f"recorded by the fixture, entry {i}",
            principle_violated=12,
            resolution="covered by this test",
        )
    return root


class TestMetaOverPatch(unittest.TestCase):
    """Реестр из трёх сбоёв двух типов: 2 x ALPHA_FAILURE, 1 x BETA_FAILURE."""

    def setUp(self):
        self.root = _make_registry("ALPHA_FAILURE", "ALPHA_FAILURE", "BETA_FAILURE")
        self.engine = MetaOverPatchEngine(workspace_root=self.root)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_registry_is_the_fixture_not_the_repository(self):
        """Движок читает реестр фикстуры, а не Core/failures.jsonl рабочего дерева."""
        self.assertEqual(self.engine.failures_file, self.root / "Core" / "failures.jsonl")
        self.assertTrue(self.engine.failures_file.exists())

    def test_load_and_analyze(self):
        """Анализ отражает ровно те записи, которые записала фикстура."""
        analysis = self.engine.analyze_patterns()
        self.assertEqual(analysis["total_failures_recorded"], 3)
        self.assertEqual(
            analysis["distribution_by_type"],
            {"ALPHA_FAILURE": 2, "BETA_FAILURE": 1},
        )
        self.assertEqual(analysis["distribution_by_principle"], {12: 3})
        self.assertEqual(len(analysis["meta_refactor_candidates"]), 2)
        occurrences = {
            candidate["failure_type"]: candidate["occurrences"]
            for candidate in analysis["meta_refactor_candidates"]
        }
        self.assertEqual(occurrences, {"ALPHA_FAILURE": 2, "BETA_FAILURE": 1})

    def test_generate_refactor_plan(self):
        """План строится по кандидатам: один шаг на каждый тип сбоя."""
        plan = self.engine.generate_refactor_plan()
        self.assertEqual(plan["title"], "Experience-Driven Architectural Refactor Plan")
        self.assertEqual(len(plan["steps"]), 2)
        self.assertEqual({step["step"] for step in plan["steps"]}, {1, 2})

    def test_plan_carries_the_failure_binding_signal(self):
        """План обязан нести привязку к сбоям, а не выбрасывать её (Принцип 12)."""
        analysis = self.engine.analyze_patterns()
        plan = self.engine.generate_refactor_plan()
        self.assertEqual(plan["total_failures"], analysis["total_failures_recorded"])
        self.assertEqual(plan["patterns"], analysis["meta_refactor_candidates"])
        self.assertEqual(len(plan["steps"]), len(analysis["meta_refactor_candidates"]))
        # Привязка наблюдаема только на непустом реестре: при нулевом все три
        # равенства выше выполняются тривиально (0 == 0, [] == [], 0 == 0).
        self.assertEqual(plan["total_failures"], 3)


class TestMetaOverPatchWithoutRegistry(unittest.TestCase):
    """Фактическое состояние свежего клона: Core/failures.jsonl отсутствует."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="metapatch-empty-")).resolve()
        (self.root / "Core").mkdir(parents=True, exist_ok=True)
        self.engine = MetaOverPatchEngine(workspace_root=self.root)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_missing_registry_is_not_an_error(self):
        """Отсутствие реестра даёт нули, а не исключение."""
        self.assertFalse(self.engine.failures_file.exists())
        analysis = self.engine.analyze_patterns()
        self.assertEqual(analysis["total_failures_recorded"], 0)
        self.assertEqual(analysis["distribution_by_type"], {})
        self.assertEqual(analysis["meta_refactor_candidates"], [])

    def test_missing_registry_yields_an_empty_plan(self):
        """На пустом реестре план пуст — именно это и видит IdempotencyGate."""
        plan = self.engine.generate_refactor_plan()
        self.assertEqual(plan["steps"], [])
        self.assertEqual(plan["total_failures"], 0)
        self.assertEqual(plan["patterns"], [])


if __name__ == "__main__":
    unittest.main()
