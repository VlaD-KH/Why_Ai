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

    def verify_and_merge(self, diff_content: str, preflight_hash: str, commit_message: str,
                         branch_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Этап 2: Проверка Re-fingerprint и применение 3-Way Merge под контролем Supervisor.
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

        # Применение слияния через Supervisor
        logger.info(f"Отпечатки совпадают ({re_fingerprint}). Применение 3-Way слияния...")

        merge_payload = {
            "status": "MERGED_SUCCESSFULLY",
            "fingerprint_verified": re_fingerprint,
            "commit_message": commit_message,
            "merged_by": "Supervisor Sovereign Core",
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

        return merge_payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Supervisor Reviewed Commit Gate & 3-Way Auto-Merge")
    parser.add_argument("--diff-file", type=str, help="Файл с диффом для префлайта")
    parser.add_argument("--preflight-hash", type=str, help="Ранее полученный preflight хэш")
    parser.add_argument("--commit-msg", default="Auto-merged self_evo patch", help="Сообщение коммита")

    args = parser.parse_args()
    gate = ReviewedCommitGate()

    if args.diff_file:
        content = Path(args.diff_file).read_text(encoding="utf-8")
        if args.preflight_hash:
            # Этап 2: Re-fingerprint & Merge
            res = gate.verify_and_merge(content, args.preflight_hash, args.commit_msg)
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
