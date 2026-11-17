#!/usr/bin/env python3
"""
Тест: tests/test_run_mvp_summary.py
Назначение: стартовый гейт run_mvp.py рапортует фактическое число тестов,
а не захардкоженный знаменатель.

Дефект, который закрывается: run_mvp.py печатал «208/32 тестов OK» —
знаменатель 32 был литералом с тех времён, когда тестов было 32, а при
нераспознанном выводе unittest подставлялось "32" и как числитель. То есть
гейт уверенно называл число, которого никто не измерял (CLAUDE.md, правило 2).

Тестируется чистая функция разбора вывода, а не run_integrity_self_check():
та запускает весь набор тестов, и вызов её из теста запустил бы набор
рекурсивно.
"""

import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

import run_mvp  # noqa: E402


class TestSummarizeTestRun(unittest.TestCase):
    def test_reports_measured_count_without_fixed_denominator(self):
        out = "....\n----------------------------------------------------------------------\nRan 208 tests in 30.144s\n\nOK\n"
        summary = run_mvp.summarize_test_run(out)
        self.assertIn("208", summary)
        self.assertNotIn("/32", summary)
        self.assertIn("OK", summary)

    def test_keeps_unittest_status_qualifiers(self):
        out = "Ran 190 tests in 27.2s\n\nOK (expected failures=1)\n"
        summary = run_mvp.summarize_test_run(out)
        self.assertIn("190", summary)
        self.assertIn("expected failures=1", summary)

    def test_unparsable_output_does_not_invent_a_number(self):
        summary = run_mvp.summarize_test_run("что-то пошло не так, строки Ran нет\n")
        self.assertNotIn("32", summary)
        self.assertIn("не распознан", summary)

    def test_banner_principle_count_comes_from_bible(self):
        banner = run_mvp.banner_lines()
        expected = run_mvp.count_principles()
        self.assertTrue(expected.isdigit(), expected)
        self.assertTrue(any(f"{expected} Principles" in line for line in banner), banner)


if __name__ == "__main__":
    unittest.main()
