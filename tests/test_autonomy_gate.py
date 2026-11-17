#!/usr/bin/env python3
"""
Тест: tests/test_autonomy_gate.py
Назначение: какие пути вправе затрагивать АВТОНОМНЫЙ кандидат самоэволюции.

До R-5 IdempotencyGate проверял пути подстрокой `"Supervisor/" in f or
"BIBLE.md" in f`. Пока кандидат был литералом, который всегда трогал
Core/evolution_log.txt, это ничего не стоило. С настоящим предложителем
(R-3) путь в диффе выбирает модель, и гейт становится несущим. Подстрока
пропускала:

  * всю policy-плоскость кроме BIBLE: .ai-loop/policy/, .ai-loop/bin/,
    .github/, CODEOWNERS (Принцип 4 — запрет самореференции);
  * .size_ratchets.json и .ai-loop/ledger.jsonl — классификатор их вообще
    исключает из входа как служебные, то есть кандидат мог бы сам поднять
    себе лимиты размера (Принцип 10) или переписать журнал, и никто бы не
    увидел;
  * supervisor/launcher.py в нижнем регистре — на NTFS это тот же файл.
"""

import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from Supervisor import AutonomyGate
from Supervisor.AutonomyGate import autonomous_path_violations
from Supervisor.EvolutionDaemon import IdempotencyGate

PLAN_WITH_FAILURES = {"title": "fixture", "steps": [], "patterns": [{"failure_type": "X"}], "total_failures": 1}


class TestAutonomousPathGate(unittest.TestCase):

    def setUp(self):
        # Рабочая область без собственной policy: гейт обязан взять policy
        # самого супервизора, а не остаться «без гейтов вообще».
        self.root = Path(tempfile.mkdtemp(prefix="autonomy-")).resolve()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.gate = IdempotencyGate(workspace_root=self.root, require_failure_binding=True)

    def _assert_rejected(self, path: str):
        valid, reason = self.gate.validate_proposal(PLAN_WITH_FAILURES, [path])
        self.assertFalse(valid, f"{path} пропущен гейтом: {reason}")
        self.assertIn("POLICY_REJECTED", reason)

    def _assert_allowed(self, path: str):
        valid, reason = self.gate.validate_proposal(PLAN_WITH_FAILURES, [path])
        self.assertTrue(valid, f"{path} отклонён: {reason}")

    def test_policy_plane_is_never_authored_autonomously(self):
        for path in (".ai-loop/policy/protected_paths.yaml", ".ai-loop/bin/classify_diff.py",
                     ".github/workflows/ai-loop-enforcement.yml", "CODEOWNERS"):
            with self.subTest(path=path):
                self._assert_rejected(path)

    def test_gate_bookkeeping_excluded_from_classification_is_rejected(self):
        """Классификатор исключает эти файлы из входа — для автономного
        кандидата это значит «нельзя», а не «не проверяется»."""
        for path in (".size_ratchets.json", ".ai-loop/ledger.jsonl", ".ai-loop/runs/x/spec.md"):
            with self.subTest(path=path):
                self._assert_rejected(path)

    def test_supervisor_is_protected_in_any_letter_case(self):
        for path in ("Supervisor/launcher.py", "supervisor/launcher.py", "SUPERVISOR/CommitGate.py",
                     "supervisor/constitution/bible.md"):
            with self.subTest(path=path):
                self._assert_rejected(path)

    def test_unzoned_and_escaping_paths_fail_closed(self):
        for path in ("stray_root_file.py", "../outside.py", "/etc/passwd", "C:/Windows/x.py"):
            with self.subTest(path=path):
                self._assert_rejected(path)

    def test_ordinary_zones_remain_proposable(self):
        """Ужесточение не должно запретить всё: E и T — законная цель,
        R публикуется в ветку на ревью человека (Принцип 13)."""
        for path in ("Tool/skills/plan/SKILL.md", "docs/guides/x.md", "tests/test_new.py", "Core/sample.py"):
            with self.subTest(path=path):
                self._assert_allowed(path)

    def test_classifier_failure_rejects_everything(self):
        with mock.patch.object(AutonomyGate, "CLASSIFIER", self.root / "missing" / "classify_diff.py"):
            violations = autonomous_path_violations(["Tool/skills/plan/SKILL.md"], self.root)
        self.assertTrue(violations)
        self.assertTrue(any("CLASSIFIER" in v["reason"] for v in violations), violations)

    def test_empty_candidate_is_rejected(self):
        self.assertTrue(autonomous_path_violations([], self.root))


if __name__ == "__main__":
    unittest.main()
