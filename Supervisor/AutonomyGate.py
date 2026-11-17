#!/usr/bin/env python3
"""
Модуль: Supervisor/AutonomyGate.py
Назначение: какие пути вправе затрагивать АВТОНОМНЫЙ кандидат самоэволюции.
Архитектурный слой: Supervisor (Зона R).

Почему это отдельный гейт, а не тот же классификатор, что судит PR:
классификатор (`.ai-loop/bin/classify_diff.py`) отвечает на вопрос «кто
обязан одобрить этот дифф» и для человеческого PR этого достаточно: любой
CRITICAL уходит человеку. Автономный кандидат — другое: его пишет модель,
и некоторые пути он не вправе даже авторствовать, как бы его потом ни
ревьюили (BIBLE, Принцип 4 — запрет самореференции):

  * policy-плоскость (зона P): `.ai-loop/policy/`, `.ai-loop/bin/`,
    `.github/`, `CODEOWNERS` — правила, по которым судят самого агента;
  * `Supervisor/` и `BIBLE.md` — неизменяемый пол (Принцип 1);
  * служебные файлы гейтов, которые классификатор ИСКЛЮЧАЕТ из входа
    (`.size_ratchets.json`, `.ai-loop/ledger.jsonl`, `.ai-loop/runs/` …):
    для PR исключение значит «не классифицировать бухгалтерию», для
    автономного кандидата — «нельзя трогать», иначе кандидат сам поднял бы
    себе лимиты размера (Принцип 10) или переписал журнал;
  * пути, не попавшие ни в одну зону, — fail-closed (Принцип 2).

Зоны E, T и R остаются доступными: кандидат публикуется не в main, а в
ветку self-evo/<cycle_id>, и слияние — право человека (Принцип 13).

Сравнение регистронезависимо: NTFS считает `supervisor/launcher.py` и
`Supervisor/launcher.py` одним файлом.

Policy берётся из рабочей области, если она там есть, иначе — policy самого
супервизора. Рабочая область без policy — это не «режим без гейтов»
(docs/guides/hierarchy-v3-RU.md, §3), а повод взять самый строгий
известный пол.
"""

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

MODULE_REPO = Path(__file__).resolve().parent.parent
CLASSIFIER = MODULE_REPO / ".ai-loop" / "bin" / "classify_diff.py"

# Пол, который не зависит от того, что скажет классификатор: даже если
# policy когда-нибудь ошибочно разметит эти пути мягче, автономный кандидат
# их не авторствует.
_FORBIDDEN_PREFIXES = ("supervisor/", ".ai-loop/", ".github/", ".git/")
_FORBIDDEN_NAMES = ("bible.md", "codeowners", ".size_ratchets.json", ".gitignore", ".gitattributes")
_ALLOWED_ZONES = ("E", "T", "R")


def _policy_repo(workspace_root: Path) -> Path:
    if (workspace_root / ".ai-loop" / "policy" / "protected_paths.yaml").is_file():
        return workspace_root
    return MODULE_REPO


def _floor_violation(path: str) -> str:
    """Структурный пол: выход за корень и запрещённые пути, без классификатора."""
    if not path:
        return "EMPTY_PATH"
    if path.startswith("/") or re.match(r"^[A-Za-z]:", path) or ".." in path.split("/"):
        return "PATH_ESCAPES_WORKSPACE"
    probe = path.casefold()
    if probe.startswith(_FORBIDDEN_PREFIXES):
        return "PROTECTED_PREFIX"
    if any(part in _FORBIDDEN_NAMES for part in probe.split("/")):
        return "PROTECTED_FILE"
    return ""


def _classify(paths: List[str], workspace_root: Path) -> Dict[str, Any]:
    """Вызов канонического классификатора в режиме --paths.

    Код выхода 10 — штатный вердикт require_human, не ошибка; JSON читается
    в любом случае. Любой другой сбой — исключение, и вызывающий трактует
    его как отказ всех путей.
    """
    if not CLASSIFIER.is_file():
        raise FileNotFoundError(f"классификатор не найден: {CLASSIFIER}")
    proc = subprocess.run(
        [sys.executable, str(CLASSIFIER), "--repo", str(_policy_repo(workspace_root)), "--paths", *paths],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
    )
    if proc.returncode not in (0, 10):
        raise RuntimeError(f"classify_diff.py exit={proc.returncode}: {(proc.stderr or '').strip()[:300]}")
    return json.loads(proc.stdout)


def autonomous_path_violations(paths: List[str], workspace_root: Path) -> List[Dict[str, Any]]:
    """Список нарушений; пустой список — все пути доступны автономному кандидату."""
    if not paths:
        return [{"path": None, "reason": "EMPTY_CANDIDATE"}]

    normalized = [p.replace("\\", "/").strip() for p in paths]
    violations = [{"path": p, "reason": r} for p in normalized for r in [_floor_violation(p)] if r]
    if violations:
        return violations

    try:
        verdict = _classify(normalized, Path(workspace_root))
    except Exception as exc:  # noqa: BLE001 — любой сбой гейта = отказ (Принцип 2)
        return [{"path": p, "reason": f"CLASSIFIER_UNAVAILABLE: {exc}"} for p in normalized]

    for excluded in verdict.get("excluded") or []:
        violations.append({"path": excluded, "reason": "GATE_BOOKKEEPING_EXCLUDED_FROM_CLASSIFICATION"})
    seen = set()
    for entry in verdict.get("paths") or []:
        seen.add(entry.get("path"))
        zone = entry.get("zone")
        if zone not in _ALLOWED_ZONES:
            violations.append({"path": entry.get("path"), "reason": f"ZONE_{zone or 'UNMATCHED'}_NOT_AUTONOMOUS"})
    for p in normalized:
        if p not in seen and not any(v["path"] == p for v in violations):
            # Классификатор не вернул вердикт по пути — не молчание, а отказ.
            violations.append({"path": p, "reason": "NO_CLASSIFIER_VERDICT"})
    return violations
