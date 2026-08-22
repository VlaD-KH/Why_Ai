#!/usr/bin/env python3
"""
Unit tests for Supervisor/CommitGate.py
Verifies two-stage SHA-256 fingerprint verification, derivation of the audited
file list from the actual diff, and the Size Ratchet veto (BIBLE Принцип 10).
"""

import datetime
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from Supervisor.CommitGate import ReviewedCommitGate

ROOT = Path(__file__).resolve().parent.parent


class TestCommitGate(unittest.TestCase):

    def setUp(self):
        self.gate = ReviewedCommitGate(workspace_root=Path("."))

    def test_fingerprint_deterministic(self):
        """Проверка детерминированности и устойчивости хэша к CRLF/LF."""
        diff_lf = "diff --git a/test.py b/test.py\n+def hello(): pass\n"
        diff_crlf = "diff --git a/test.py b/test.py\r\n+def hello(): pass\r\n"
        hash_lf = self.gate.calculate_fingerprint(diff_lf)
        hash_crlf = self.gate.calculate_fingerprint(diff_crlf)
        self.assertEqual(hash_lf, hash_crlf)

    def test_re_fingerprint_mismatch_blocks_merge(self):
        """Проверка блокировки слияния при изменении диффа после кворума."""
        original_diff = "+ def original(): return 1\n"
        mutated_diff = "+ def mutated_malicious(): return 2\n"

        preflight_hash = self.gate.calculate_fingerprint(original_diff)
        res = self.gate.verify_and_merge(mutated_diff, preflight_hash, "Attempted merge with mutated diff")

        self.assertEqual(res["status"], "FINGERPRINT_MISMATCH")
        self.assertFalse(res["merged"])

    def test_merge_payload_is_bound_to_the_verified_diff(self):
        """Отчёт о слиянии обязан нести отпечаток именно проверенного диффа и время."""
        diff = "+ def valid(): return 1\n"
        preflight_hash = self.gate.calculate_fingerprint(diff)
        res = self.gate.verify_and_merge(diff, preflight_hash, "Clean verified merge")

        self.assertEqual(res["status"], "MERGED_SUCCESSFULLY")
        self.assertEqual(res["fingerprint_verified"], preflight_hash)
        self.assertEqual(res["commit_message"], "Clean verified merge")
        # В поле времени лежал str(Path.cwd()) — рабочий каталог вместо метки времени.
        datetime.datetime.fromisoformat(res["timestamp"])


class TestChangedFileExtraction(unittest.TestCase):

    def test_files_are_extracted_from_unified_diff_headers(self):
        """Список аудируемых файлов берётся из диффа: add / modify / delete / rename."""
        from Supervisor.CommitGate import extract_changed_files
        diff = (
            "diff --git a/Core/kept.py b/Core/kept.py\n"
            "--- a/Core/kept.py\n"
            "+++ b/Core/kept.py\n"
            "@@ -1 +1 @@\n"
            "-old\n+new\n"
            "diff --git a/Core/added.py b/Core/added.py\n"
            "new file mode 100644\n"
            "--- /dev/null\n"
            "+++ b/Core/added.py\n"
            "+fresh\n"
            "diff --git a/Core/gone.py b/Core/gone.py\n"
            "deleted file mode 100644\n"
            "--- a/Core/gone.py\n"
            "+++ /dev/null\n"
            "-bye\n"
            "diff --git a/Core/old_name.py b/Core/new_name.py\n"
            "rename from Core/old_name.py\n"
            "rename to Core/new_name.py\n"
        )
        files = extract_changed_files(diff)
        self.assertEqual(
            sorted(files),
            ["Core/added.py", "Core/gone.py", "Core/kept.py", "Core/new_name.py", "Core/old_name.py"],
        )
        self.assertNotIn("/dev/null", files)


class TestCommitGateRatchetVeto(unittest.TestCase):
    """Принцип 10 подключён к шлюзу: раздувание блокируется, а не логируется."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="gate-ratchet-")).resolve()
        (self.tmp / "Core").mkdir(parents=True, exist_ok=True)
        (self.tmp / "tests").mkdir(parents=True, exist_ok=True)
        (self.tmp / "tests" / "test_widget.py").write_bytes(b"t" * 100)
        (self.tmp / ".size_ratchets.json").write_text(
            json.dumps({
                "schema": "ai-loop/size-ratchets/v1",
                "principle": "shrink-only",
                "limits": {"Core/widget.py": 1000, "tests/test_widget.py": 100},
            }),
            encoding="utf-8",
        )
        self.gate = ReviewedCommitGate(workspace_root=self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _diff(self) -> str:
        return (
            "diff --git a/Core/widget.py b/Core/widget.py\n"
            "--- a/Core/widget.py\n"
            "+++ b/Core/widget.py\n"
            "+pad\n"
            "diff --git a/tests/test_widget.py b/tests/test_widget.py\n"
            "--- a/tests/test_widget.py\n"
            "+++ b/tests/test_widget.py\n"
            "+pad\n"
        )

    def test_growth_within_the_ceiling_passes_the_gate(self):
        """Контроль: гейт не отклоняет всё подряд — рост +10% проходит."""
        (self.tmp / "Core" / "widget.py").write_bytes(b"x" * 1100)
        res = self.gate.stage_preflight(self._diff())
        self.assertTrue(res["can_merge"], res)
        self.assertEqual(res["status"], "PREFLIGHT_READY")
        self.assertTrue(res["ratchet_result"]["ok"])

    def test_growth_beyond_the_ceiling_blocks_the_merge(self):
        """Патч, необоснованно увеличивающий объём, обязан быть заблокирован."""
        (self.tmp / "Core" / "widget.py").write_bytes(b"x" * 4000)
        res = self.gate.stage_preflight(self._diff())
        self.assertFalse(res["can_merge"], res)
        self.assertEqual(res["status"], "SIZE_RATCHET_VIOLATION")
        self.assertEqual([v["path"] for v in res["ratchet_result"]["violations"]], ["Core/widget.py"])

    def test_gate_does_not_rewrite_the_registry_it_enforces(self):
        """Проверка не имеет права молча переустановить базу проверяемого файла."""
        (self.tmp / "Core" / "widget.py").write_bytes(b"x" * 200)   # усадка
        before = (self.tmp / ".size_ratchets.json").read_bytes()
        self.gate.stage_preflight(self._diff())
        self.assertEqual(before, (self.tmp / ".size_ratchets.json").read_bytes())


class TestCommitGateCLI(unittest.TestCase):
    """Классовый API не доказывает работоспособность CLI — проверяем через subprocess."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="gate-cli-")).resolve()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, diff_text: str):
        diff_path = self.tmp / "candidate.diff"
        diff_path.write_text(diff_text, encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(ROOT / "Supervisor" / "CommitGate.py"), "--diff-file", str(diff_path)],
            cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace",
            env={**dict(__import__("os").environ), "PYTHONUTF8": "1"},
        )
        return proc

    def test_cli_audits_the_files_named_by_the_diff_not_a_literal(self):
        """CLI обязан аудировать файлы из диффа; жёсткий литерал скрывал вето Zone P/R."""
        diff = (
            "diff --git a/Supervisor/launcher.py b/Supervisor/launcher.py\n"
            "--- a/Supervisor/launcher.py\n"
            "+++ b/Supervisor/launcher.py\n"
            "+# background edit of the immutable floor\n"
        )
        proc = self._run(diff)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["quorum_result"]["files_audited"], ["Supervisor/launcher.py"])
        self.assertFalse(payload["can_merge"])
        self.assertEqual(proc.returncode, 10)

    def test_cli_exit_zero_on_a_clean_diff(self):
        """Контроль: чистый дифф в зоне E проходит и возвращает 0."""
        diff = (
            "diff --git a/Core/nonexistent_probe.py b/Core/nonexistent_probe.py\n"
            "--- a/Core/nonexistent_probe.py\n"
            "+++ b/Core/nonexistent_probe.py\n"
            "diff --git a/tests/test_nonexistent_probe.py b/tests/test_nonexistent_probe.py\n"
            "--- a/tests/test_nonexistent_probe.py\n"
            "+++ b/tests/test_nonexistent_probe.py\n"
            "+assert True\n"
        )
        proc = self._run(diff)
        payload = json.loads(proc.stdout)
        self.assertTrue(payload["can_merge"], payload)
        self.assertEqual(proc.returncode, 0)


if __name__ == "__main__":
    unittest.main()
