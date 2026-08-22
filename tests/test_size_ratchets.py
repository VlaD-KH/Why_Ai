#!/usr/bin/env python3
"""
Unit tests for Supervisor/SizeRatchets.py
Verifies bloat detection, side-effect-free checking (gate mode), path
normalisation and explicit, reasoned re-baselining.
"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from Supervisor.SizeRatchets import SizeRatchetsManager, RATCHET_REGISTRY


class TestSizeRatchets(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ratchet-")).resolve()
        self.registry = self.tmp / RATCHET_REGISTRY

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, rel: str, size: int) -> Path:
        p = self.tmp / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"x" * size)
        return p

    def test_growth_beyond_ceiling_is_rejected(self):
        """Рост в пределах 15% допустим, рост выше потолка обязан отклоняться."""
        self._write("mod.py", 1000)
        m = SizeRatchetsManager(workspace_root=self.tmp)
        self.assertTrue(m.check_file("mod.py"))          # регистрация базы 1000
        self._write("mod.py", 1100)                      # +10% — в пределах потолка
        self.assertTrue(m.check_file("mod.py"))
        self._write("mod.py", 1200)                      # +20% — за потолком
        self.assertFalse(m.check_file("mod.py"))

    def test_check_in_gate_mode_writes_nothing(self):
        """Гейт не имеет права переустанавливать базу побочным эффектом проверки."""
        self._write("known.py", 1000)
        m = SizeRatchetsManager(workspace_root=self.tmp)
        m.check_file("known.py")                         # база 1000 записана
        before = self.registry.read_bytes()

        self._write("fresh.py", 4242)                    # новый файл — соблазн зарегистрировать
        self._write("known.py", 400)                     # усадка — соблазн понизить лимит
        gate = SizeRatchetsManager(workspace_root=self.tmp)
        self.assertTrue(gate.check_file("fresh.py", persist=False))
        self.assertTrue(gate.check_file("known.py", persist=False))

        self.assertEqual(before, self.registry.read_bytes())

    def test_check_paths_names_every_violator(self):
        """check_paths обязан вернуть структурный список нарушителей, а не один флаг."""
        self._write("ok.py", 1000)
        self._write("bad_one.py", 1000)
        self._write("bad_two.py", 1000)
        m = SizeRatchetsManager(workspace_root=self.tmp)
        for f in ("ok.py", "bad_one.py", "bad_two.py"):
            m.check_file(f)
        self._write("bad_one.py", 5000)
        self._write("bad_two.py", 9000)

        res = m.check_paths(["ok.py", "bad_one.py", "bad_two.py"])
        self.assertFalse(res["ok"])
        self.assertEqual({v["path"] for v in res["violations"]}, {"bad_one.py", "bad_two.py"})
        offender = [v for v in res["violations"] if v["path"] == "bad_two.py"][0]
        self.assertEqual(offender["recorded_limit"], 1000)
        self.assertEqual(offender["ceiling"], 1150)
        self.assertEqual(offender["current_size"], 9000)

    def test_dot_prefixed_paths_are_not_mangled(self):
        """`.github/x.yml` не должен нормализоваться в `github/x.yml` (lstrip('./'))."""
        self._write(".github/workflows/gate.yml", 1000)
        m = SizeRatchetsManager(workspace_root=self.tmp)
        m.check_file(".github/workflows/gate.yml")
        self.assertIn(".github/workflows/gate.yml", m.limits)
        self._write(".github/workflows/gate.yml", 5000)
        self.assertFalse(m.check_file(".github/workflows/gate.yml"))

    def test_rebaseline_refuses_without_a_reason(self):
        """Переустановка базы вверх без записанной причины запрещена."""
        self._write("grown.py", 1000)
        m = SizeRatchetsManager(workspace_root=self.tmp)
        m.check_file("grown.py")
        self._write("grown.py", 9000)
        with self.assertRaises(ValueError):
            m.rebaseline("grown.py", "   ")
        self.assertFalse(m.check_file("grown.py"))

    def test_rebaseline_records_old_new_and_reason(self):
        """Явная переустановка базы обязана оставить аудит-запись в реестре."""
        self._write("grown.py", 1000)
        m = SizeRatchetsManager(workspace_root=self.tmp)
        m.check_file("grown.py")
        self._write("grown.py", 9000)

        rec = m.rebaseline("grown.py", "Задача 5.0: перенос базы при активации гейта")
        self.assertEqual(rec["old_limit"], 1000)
        self.assertEqual(rec["new_limit"], 9000)
        self.assertTrue(m.check_file("grown.py"))

        stored = json.loads(self.registry.read_text(encoding="utf-8"))
        audit = stored["rebaselines"]
        self.assertEqual(len(audit), 1)
        self.assertEqual(audit[0]["path"], "grown.py")
        self.assertEqual(audit[0]["old_limit"], 1000)
        self.assertEqual(audit[0]["new_limit"], 9000)
        self.assertIn("5.0", audit[0]["reason"])

    def test_registry_does_not_ratchet_itself(self):
        """Реестр не может быть собственным храповиком: каждая запись раздувает его."""
        self._write("mod.py", 1000)
        m = SizeRatchetsManager(workspace_root=self.tmp)
        m.record_baseline()                     # первый проход создаёт сам реестр
        m.record_baseline()                     # второй уже видит его на диске
        self.assertIn("mod.py", m.limits)
        self.assertNotIn(str(RATCHET_REGISTRY).replace("\\", "/"), m.limits)
        self.assertTrue(SizeRatchetsManager(workspace_root=self.tmp).check_file(str(RATCHET_REGISTRY)))

    def test_record_baseline_never_raises_a_limit(self):
        """record_baseline — shrink-only: рост базы через него невозможен."""
        self._write("mod.py", 1000)
        m = SizeRatchetsManager(workspace_root=self.tmp)
        m.record_baseline()
        self._write("mod.py", 9000)
        m.record_baseline()
        self.assertEqual(m.limits["mod.py"], 1000)


if __name__ == "__main__":
    unittest.main()
