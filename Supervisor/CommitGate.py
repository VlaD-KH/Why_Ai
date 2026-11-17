#!/usr/bin/env python3
"""
Модуль: Supervisor/CommitGate.py
Назначение: ШлюзReviewed Commit Gate с двухэтапной проверкой SHA-256 отпечатков и трехсторонним слиянием (3-Way Merge).
Архитектурный слой: Supervisor (Зона P/R - Immutable Core Floor).
Инвариант: Несовпадение Preflight SHA-256 и Re-fingerprint блокирует слияние. Слияние выполняет только Supervisor.
"""

import argparse
import datetime
import hashlib
import json
import logging
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional

# Добавление директории Supervisor в путь поиска
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from QuorumReviewer import MultiModelQuorumReviewer
    from SizeRatchets import SizeRatchetsManager
except ImportError:
    from Supervisor.QuorumReviewer import MultiModelQuorumReviewer  # type: ignore
    from Supervisor.SizeRatchets import SizeRatchetsManager  # type: ignore

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] [COMMIT-GATE] %(message)s")
logger = logging.getLogger("CommitGate")

_DIFF_GIT_RE = re.compile(r"^diff --git a/(.+?) b/(.+)$")
_RENAME_FROM_RE = re.compile(r"^rename from (.+)$")
_RENAME_TO_RE = re.compile(r"^rename to (.+)$")


def extract_changed_files(diff_text: str) -> List[str]:
    """Список аудируемых файлов — из ЗАГОЛОВКОВ unified diff, а не из
    переданного отдельно списка. Раньше `stage_preflight` принимал
    `files_changed` как отдельный аргумент, и вызывающий код был волен
    передать туда что угодно — жёсткий литерал `["Core/sample.py", ...]` в
    CLI и в `EvolutionDaemon` годами скрывал вето Zone P/R: кворум проверял
    не те файлы, что реально менялись."""
    files: set = set()
    for line in diff_text.splitlines():
        m = _DIFF_GIT_RE.match(line)
        if m:
            a, b = m.group(1).strip(), m.group(2).strip()
            if a and a != "/dev/null":
                files.add(a)
            if b and b != "/dev/null":
                files.add(b)
            continue
        m = _RENAME_FROM_RE.match(line) or _RENAME_TO_RE.match(line)
        if m:
            p = m.group(1).strip()
            if p and p != "/dev/null":
                files.add(p)
    return sorted(files)


class ReviewedCommitGate:
    """
    Криптографический шлюз фиксации изменений с защитой от подмены в процессе кворума.
    """

    def __init__(self, workspace_root: Optional[Path] = None) -> None:
        self.workspace_root = (workspace_root or Path.cwd()).resolve()
        self.quorum_reviewer = MultiModelQuorumReviewer(workspace_root=self.workspace_root)
        self.ratchets = SizeRatchetsManager(workspace_root=self.workspace_root)

    def calculate_fingerprint(self, content: str) -> str:
        """Расчет криптографического отпечатка SHA-256."""
        # Нормализация окончаний строк для кроссплатформенной стабильности
        normalized = content.replace("\r\n", "\n").strip()
        return "sha256:" + hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def stage_preflight(self, diff_content: str) -> Dict[str, Any]:
        """
        Этап 1: список файлов из самого диффа, проверка Size Ratchets
        (Принцип 10 — гейт-режим, реестр не переписывается) и мультимодельный
        кворум. Раздувание объёма блокирует слияние независимо от вердикта
        кворума: это отдельный, а не декоративный, гейт.
        """
        preflight_hash = self.calculate_fingerprint(diff_content)
        files_changed = extract_changed_files(diff_content)
        logger.info(f"Preflight отпечаток зафиксирован: {preflight_hash}; файлов в диффе: {len(files_changed)}")

        ratchet_result = self.ratchets.check_paths(files_changed, persist=False)
        quorum_result = self.quorum_reviewer.review_diff(diff_content, files_changed)
        quorum_passed = quorum_result["quorum_decision"] == "APPROVED"

        can_merge = quorum_passed and ratchet_result["ok"]
        if not ratchet_result["ok"]:
            status = "SIZE_RATCHET_VIOLATION"
        elif not quorum_passed:
            status = "QUORUM_VETOED"
        else:
            status = "PREFLIGHT_READY"

        return {
            "status": status,
            "preflight_fingerprint": preflight_hash,
            "quorum_result": quorum_result,
            "ratchet_result": ratchet_result,
            "can_merge": can_merge,
        }

    def _git(self, args: List[str], cwd: Optional[Path] = None,
             stdin_text: Optional[str] = None) -> subprocess.CompletedProcess:
        """Единая обёртка git с явной кодировкой.

        encoding/errors обязательны: на Windows консоль по умолчанию cp1250,
        и git-вывод с кириллицей роняет процесс UnicodeDecodeError. Тот же
        приём уже применён в WorktreeSandbox._run_git. check=True не
        используем — разбираем returncode явно, как везде в Supervisor/.
        """
        return subprocess.run(
            ["git", "-C", str(cwd or self.workspace_root), *args],
            input=stdin_text,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )

    def run_sandbox_tests(self, sandbox: Path, timeout_s: int = 600) -> Dict[str, Any]:
        """Прогон tests/ внутри песочницы. Структурный результат, не булев флаг.

        Итоговую строку "Ran N tests" unittest пишет в stderr, не в stdout —
        ищем в объединении потоков (тот же дефект уже был пойман вживую в
        дашборде, Волна 0).

        Каталог тестов передаётся АБСОЛЮТНЫМ путём, и его существование
        проверяется заранее. Причина не теоретическая: при `-s tests` и
        отсутствующем ./tests unittest трактует "tests" как имя МОДУЛЯ и
        находит установленный сторонний пакет `tests` в site-packages —
        наблюдалось вживую на фикстуре без tests/, прогон подхватил 2108
        чужих тестов и упал. То есть «красные тесты песочницы» могли бы
        означать «в окружении стоит пакет с таким именем», а не «кандидат
        сломал сборку».
        """
        tests_dir = Path(sandbox) / "tests"
        if not tests_dir.is_dir():
            return {"passed": False, "status": "TESTS_DIR_MISSING", "summary": "0 tests",
                    "output_tail": f"В песочнице нет каталога tests/: {tests_dir}"}
        try:
            res = subprocess.run(
                [sys.executable, "-m", "unittest", "discover",
                 "-s", str(tests_dir), "-t", str(sandbox), "-p", "test_*.py"],
                cwd=str(sandbox), capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=timeout_s,
            )
        except subprocess.TimeoutExpired:
            return {"passed": False, "status": "TEST_TIMEOUT", "summary": "timeout",
                    "output_tail": f"Прогон не уложился в {timeout_s} с."}

        combined = (res.stdout or "") + (res.stderr or "")
        match = re.search(r"Ran (\d+) tests?", combined)
        summary = f"{match.group(1)} tests" if match else "unknown"
        if res.returncode != 0:
            return {"passed": False, "status": "TEST_FAILURE", "summary": summary,
                    "output_tail": "\n".join(combined.splitlines()[-40:])}
        return {"passed": True, "status": "TESTS_PASSED", "summary": summary,
                "output_tail": "\n".join(combined.splitlines()[-10:])}

    def verify_and_merge(self, diff_content: str, preflight_hash: str, commit_message: str,
                         sandbox_path: Optional[str] = None,
                         publish_branch: Optional[str] = None) -> Dict[str, Any]:
        """
        Этап 2: Re-fingerprint, реальное применение диффа в песочнице, прогон
        тестов и публикация проверенного кандидата в отдельную ветку.

        Раньше этот метод возвращал литерал {"status": "MERGED_SUCCESSFULLY"}
        без единого git-вызова: `import subprocess` в модуле был, но не
        использовался ни разу. «Слияние» отчитывалось об успехе, не сделав
        ничего — ровно то, от чего предостерегает CLAUDE.md, правило 2.

        Почему публикация в ВЕТКУ, а не мерж в main:
        `.ai-loop/policy/risk_classification.yaml` объявляет
        `separation.merge_authority: human`, а BIBLE.md — Принцип 13
        («Исключительное право человека на слияние»). Автономный мерж в main
        нарушил бы обе нормы. Поэтому конвейер доводит кандидата до реального,
        проверенного коммита на ветке self-evo/<cycle_id> и останавливается:
        решение о слиянии остаётся человеку, через тот же PR-процесс, которым
        проходит любое изменение зоны R.

        Возвращаемый commit_sha настоящий: разрешается `git cat-file -e` из
        workspace_root даже после удаления песочницы, потому что publish_branch
        держит объект достижимым.
        """
        re_fingerprint = self.calculate_fingerprint(diff_content)

        if re_fingerprint != preflight_hash:
            logger.error(f"[SECURITY-VIOLATION] Несовпадение отпечатков! Preflight: {preflight_hash} != Re-fingerprint: {re_fingerprint}")
            return {
                "status": "FINGERPRINT_MISMATCH",
                "preflight": preflight_hash,
                "re_fingerprint": re_fingerprint,
                "merged": False,
                "error": "Криптографический отпечаток диффа изменился после кворума! Слияние заблокировано.",
            }

        if not sandbox_path or not publish_branch:
            # Fail-closed: применять дифф вне песочницы некуда. Раньше в этом
            # месте безусловно возвращался успех.
            return {
                "status": "NO_SANDBOX_PROVIDED", "merged": False,
                "fingerprint_verified": re_fingerprint,
                "error": "verify_and_merge требует sandbox_path и publish_branch.",
            }

        sandbox = Path(sandbox_path)
        logger.info(f"Отпечатки совпадают ({re_fingerprint}). Применение диффа в песочнице {sandbox}...")

        # 1. Применить дифф в песочнице (--check первым, чтобы не оставить
        #    частично применённый патч).
        check = self._git(["apply", "--check", "-"], cwd=sandbox, stdin_text=diff_content)
        if check.returncode != 0:
            return {"status": "PATCH_APPLY_FAILED", "merged": False,
                    "fingerprint_verified": re_fingerprint,
                    "git_error": (check.stderr or "").strip()}
        applied = self._git(["apply", "-"], cwd=sandbox, stdin_text=diff_content)
        if applied.returncode != 0:
            return {"status": "PATCH_APPLY_FAILED", "merged": False,
                    "fingerprint_verified": re_fingerprint,
                    "git_error": (applied.stderr or "").strip()}

        # 2. Зафиксировать кандидата реальным коммитом.
        self._git(["add", "-A"], cwd=sandbox)
        committed = self._git(["commit", "-m", commit_message], cwd=sandbox)
        if committed.returncode != 0:
            return {"status": "SANDBOX_COMMIT_FAILED", "merged": False,
                    "fingerprint_verified": re_fingerprint,
                    "git_error": (committed.stderr or committed.stdout or "").strip()}
        sandbox_sha = self._git(["rev-parse", "HEAD"], cwd=sandbox).stdout.strip()

        # 3. Прогнать тесты ВНУТРИ песочницы против этого коммита. Раньше между
        #    созданием и удалением песочницы не выполнялось ничего.
        test_res = self.run_sandbox_tests(sandbox)
        if not test_res["passed"]:
            return {"status": test_res["status"], "merged": False,
                    "fingerprint_verified": re_fingerprint,
                    "sandbox_commit": sandbox_sha,
                    "test_output_tail": test_res["output_tail"]}

        # 4. Опубликовать проверенный коммит в отдельную ветку. Worktree делит
        #    хранилище объектов с workspace_root — это запись ref, не push.
        exists = self._git(["rev-parse", "--verify", "--quiet", publish_branch])
        if exists.returncode == 0:
            # Не перезаписываем: у человека эта ветка может быть уже в PR.
            return {"status": "SELF_EVO_BRANCH_COLLISION", "merged": False,
                    "fingerprint_verified": re_fingerprint,
                    "sandbox_commit": sandbox_sha, "publish_branch": publish_branch}
        published = self._git(["branch", publish_branch, sandbox_sha])
        if published.returncode != 0:
            return {"status": "BRANCH_PUBLISH_FAILED", "merged": False,
                    "fingerprint_verified": re_fingerprint,
                    "sandbox_commit": sandbox_sha,
                    "git_error": (published.stderr or "").strip()}

        logger.info(f"Кандидат верифицирован и опубликован: {publish_branch} -> {sandbox_sha}")
        return {
            "status": "CANDIDATE_VERIFIED_AND_PUBLISHED",
            "merged": True,
            "fingerprint_verified": re_fingerprint,
            "commit_message": commit_message,
            "commit_sha": sandbox_sha,
            "publish_branch": publish_branch,
            "tests_ran": test_res["summary"],
            "merged_by": "Supervisor Sovereign Core",
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "human_action_required": (
                f"git push origin {publish_branch} и открыть PR в main — слияние "
                "остаётся за человеком (BIBLE Принцип 13, merge_authority: human)"
            ),
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Supervisor Reviewed Commit Gate & 3-Way Auto-Merge")
    parser.add_argument("--diff-file", type=str, help="Файл с диффом для префлайта")
    parser.add_argument("--preflight-hash", type=str, help="Ранее полученный preflight хэш")
    parser.add_argument("--commit-msg", default="Auto-merged self_evo patch", help="Сообщение коммита")
    parser.add_argument("--sandbox-path", type=str, help="Абсолютный путь песочницы (worktree), где применяется дифф")
    parser.add_argument("--publish-branch", type=str, help="Ветка для публикации проверенного кандидата (self-evo/<id>)")

    args = parser.parse_args()
    gate = ReviewedCommitGate()

    if args.diff_file:
        content = Path(args.diff_file).read_text(encoding="utf-8")
        if args.preflight_hash:
            # Этап 2: Re-fingerprint, применение в песочнице, тесты, публикация.
            # CLI ведёт ровно тот же путь, что и EvolutionDaemon — иначе через
            # него можно было бы «слить» непроверенный дифф в обход тестов.
            res = gate.verify_and_merge(content, args.preflight_hash, args.commit_msg,
                                        sandbox_path=args.sandbox_path,
                                        publish_branch=args.publish_branch)
            print(json.dumps(res, indent=2, ensure_ascii=False))
            return 0 if res.get("merged") is not False else 10
        else:
            # Этап 1: Preflight & Quorum. Список файлов берётся из самого
            # диффа (extract_changed_files) — раньше здесь был жёсткий
            # литерал, из-за которого CLI аудировал не те файлы, что реально
            # менялись, и вето Zone P/R не срабатывало.
            res = gate.stage_preflight(content)
            print(json.dumps(res, indent=2, ensure_ascii=False))
            return 0 if res.get("can_merge") else 10

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
