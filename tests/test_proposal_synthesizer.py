#!/usr/bin/env python3
"""
Тест: tests/test_proposal_synthesizer.py
Назначение: звено 4 конвейера самоэволюции — синтез кандидатного диффа
предложителем (R-3, Tool/connectors/llm_connector.py) — и его отказы.

Предложитель здесь — подделка с тем же контрактом, что LLMConnector.propose():
сеть в тестах не трогается ни при каком окружении (ключ API может быть
задан у оператора, и тест не имеет права тратить его деньги).
"""

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from Supervisor.ProposalSynthesizer import (
    MAX_CONTEXT_BYTES,
    SYSTEM_PROMPT,
    extract_unified_diff,
    gather_context,
    synthesize,
)

DIFF = (
    "diff --git a/Tool/skills/plan/SKILL.md b/Tool/skills/plan/SKILL.md\n"
    "--- a/Tool/skills/plan/SKILL.md\n"
    "+++ b/Tool/skills/plan/SKILL.md\n"
    "@@ -1,2 +1,2 @@\n"
    " # plan\n"
    "-old rule\n"
    "+new rule\n"
)

PLAN = {
    "title": "Experience-Driven Architectural Refactor Plan",
    "steps": [{"step": 1, "target_module": "Tool/skills/",
               "objective": "Рефакторинг для предотвращения PROMPT_TO_SHIP_ATTEMPT",
               "metric": "Снижение частоты PROMPT_TO_SHIP_ATTEMPT до 0"},
              {"step": 2, "target_module": "Supervisor/launcher.py",
               "objective": "Рефакторинг для предотвращения PANIC_X", "metric": "x"}],
    "patterns": [{"failure_type": "PROMPT_TO_SHIP_ATTEMPT", "occurrences": 3}],
    "total_failures": 3,
}


class FakeProposer:
    """Тот же контракт, что LLMConnector.propose()."""

    def __init__(self, reply=None, **overrides):
        self.calls = []
        self.result = {"proposed": True, "text": reply, "model": "fake-model", "stop_reason": "end_turn",
                       "error": None, "error_detail": None, "usage": {"input_tokens": 10, "output_tokens": 5}}
        self.result.update(overrides)

    def propose(self, prompt, system=None):
        self.calls.append((prompt, system))
        return dict(self.result)


def _git(root, *args):
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


class TestExtractUnifiedDiff(unittest.TestCase):

    def test_fenced_diff_block(self):
        diff, err = extract_unified_diff(f"Вот правка:\n```diff\n{DIFF}```\nГотово.")
        self.assertIsNone(err)
        self.assertEqual(diff, DIFF)

    def test_raw_diff_without_fence(self):
        diff, err = extract_unified_diff(DIFF)
        self.assertIsNone(err)
        self.assertEqual(diff, DIFF)

    def test_crlf_is_normalised_and_trailing_newline_added(self):
        diff, err = extract_unified_diff("```diff\r\n" + DIFF.rstrip("\n").replace("\n", "\r\n") + "\r\n```")
        self.assertIsNone(err)
        self.assertEqual(diff, DIFF)

    def test_two_diff_blocks_are_ambiguous(self):
        diff, err = extract_unified_diff(f"```diff\n{DIFF}```\nили\n```diff\n{DIFF}```")
        self.assertIsNone(diff)
        self.assertEqual(err, "AMBIGUOUS_PROPOSAL")

    def test_prose_without_diff_is_not_a_proposal(self):
        for text in ("NO_SAFE_CHANGE", "```python\nprint(1)\n```", "--- a/x\n+++ b/x\n@@ -1 +1 @@\n-a\n+b\n"):
            with self.subTest(text=text[:20]):
                diff, err = extract_unified_diff(text)
                self.assertIsNone(diff)
                self.assertEqual(err, "NO_DIFF_IN_PROPOSAL")


class TestGatherContext(unittest.TestCase):

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="synth-ctx-")).resolve()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        _git(self.root, "init", "-q")
        _git(self.root, "config", "user.email", "fixture@why-ai.test")
        _git(self.root, "config", "user.name", "Synth Fixture")
        (self.root / "Tool" / "skills" / "plan").mkdir(parents=True)
        (self.root / "Tool" / "skills" / "plan" / "SKILL.md").write_text("# plan\nold rule\n", encoding="utf-8")
        (self.root / "Tool" / "skills" / "big.md").write_text("z" * (MAX_CONTEXT_BYTES + 10), encoding="utf-8")
        (self.root / "Supervisor").mkdir()
        (self.root / "Supervisor" / "launcher.py").write_text("SECRET_FLOOR = 1\n", encoding="utf-8")
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-q", "-m", "fixture")
        # Незакоммиченная правка: кандидат применяется к HEAD, контекст обязан быть из HEAD.
        (self.root / "Tool" / "skills" / "plan" / "SKILL.md").write_text("# plan\nDIRTY\n", encoding="utf-8")

    def test_context_comes_from_head_and_skips_protected_and_oversized_files(self):
        files = {f["path"]: f["text"] for f in gather_context(self.root, PLAN)}
        self.assertEqual(files.get("Tool/skills/plan/SKILL.md"), "# plan\nold rule\n")
        self.assertNotIn("Supervisor/launcher.py", files, "защищённый путь не должен попадать в контекст")
        self.assertNotIn("Tool/skills/big.md", files)
        self.assertLessEqual(sum(len(t.encode("utf-8")) for t in files.values()), MAX_CONTEXT_BYTES)


class TestSynthesize(unittest.TestCase):

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="synth-")).resolve()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def test_no_proposer_fails_closed(self):
        res = synthesize(None, PLAN, self.root)
        self.assertFalse(res["ok"])
        self.assertEqual(res["status"], "PROPOSER_UNAVAILABLE")
        self.assertIsNone(res["diff"])

    def test_missing_api_key_is_unavailable_not_a_success(self):
        fake = FakeProposer(proposed=False, text=None, stop_reason=None, error="NO_API_KEY",
                            error_detail="ANTHROPIC_API_KEY не задана")
        res = synthesize(fake, PLAN, self.root)
        self.assertEqual(res["status"], "PROPOSER_UNAVAILABLE")
        self.assertIn("NO_API_KEY", res["error"])

    def test_refusal_and_transport_failures_are_reported(self):
        refused = synthesize(FakeProposer(proposed=False, error="REFUSAL", stop_reason="refusal"), PLAN, self.root)
        self.assertEqual(refused["status"], "PROPOSAL_REFUSED")
        failed = synthesize(FakeProposer(proposed=False, error="HTTP_ERROR"), PLAN, self.root)
        self.assertEqual(failed["status"], "PROPOSAL_FAILED")

    def test_truncated_answer_is_not_applied(self):
        res = synthesize(FakeProposer(f"```diff\n{DIFF}```", stop_reason="max_tokens"), PLAN, self.root)
        self.assertEqual(res["status"], "PROPOSAL_INCOMPLETE")
        self.assertIsNone(res["diff"])

    def test_valid_answer_yields_the_diff_and_an_auditable_prompt(self):
        fake = FakeProposer(f"```diff\n{DIFF}```")
        res = synthesize(fake, PLAN, self.root)
        self.assertTrue(res["ok"], res)
        self.assertEqual(res["status"], "PROPOSAL_READY")
        self.assertEqual(res["diff"], DIFF)
        self.assertEqual(res["model"], "fake-model")
        self.assertTrue(res["prompt_sha256"].startswith("sha256:"))

        prompt, system = fake.calls[0]
        self.assertEqual(system, SYSTEM_PROMPT)
        self.assertIn("PROMPT_TO_SHIP_ATTEMPT", prompt)
        # Модель заранее знает, что отклонит гейт, а не узнаёт об этом по факту.
        for forbidden in ("Supervisor/", ".ai-loop/", ".size_ratchets.json"):
            self.assertIn(forbidden, SYSTEM_PROMPT)

    def test_no_safe_change_is_not_an_error_of_the_proposer(self):
        res = synthesize(FakeProposer("NO_SAFE_CHANGE"), PLAN, self.root)
        self.assertFalse(res["ok"])
        self.assertEqual(res["status"], "NO_DIFF_IN_PROPOSAL")


if __name__ == "__main__":
    unittest.main()


class TestFencesInsideTheDiff(unittest.TestCase):
    """Найдено ревью R-5: SKILL.md и docs/ содержат блоки кода. Внутри диффа
    их ограждения идут с префиксом строки диффа (« », «+», «-»), и закрывать
    блок ответа они не должны — иначе обрезанный дифф не применится никогда."""

    MD_DIFF = (
        "diff --git a/Tool/skills/plan/SKILL.md b/Tool/skills/plan/SKILL.md\n"
        "--- a/Tool/skills/plan/SKILL.md\n"
        "+++ b/Tool/skills/plan/SKILL.md\n"
        "@@ -1,4 +1,4 @@\n"
        " # plan\n"
        "-```bash\n"
        "+```sh\n"
        " run\n"
        " ```\n"
    )

    def test_inner_code_fences_do_not_truncate_the_diff(self):
        diff, err = extract_unified_diff(f"Правка:\n```diff\n{self.MD_DIFF}```\n")
        self.assertIsNone(err)
        self.assertEqual(diff, self.MD_DIFF)
