#!/usr/bin/env python3
"""
Модуль: Supervisor/classify_diff.py
Назначение: Детерминированная классификация рисков набора изменений на основе git diff и матрицы зон.
Архитектурный слой: Supervisor (Зона P / R - Immutable Core Floor).
Инвариант: diff_is_authoritative, fail-closed, правило MAX risk для каскадных политик.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import subprocess
import sys
from typing import Any, List, Dict, Tuple, Optional

# Добавление директории Supervisor в путь импорта
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import miniyaml
except ImportError:
    from Supervisor import miniyaml  # type: ignore

SCHEMA = "ai-loop/classification/v1"
LEVELS = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
LEVEL_INDEX = {name: i for i, name in enumerate(LEVELS)}

# Порядок защиты зон: наиболее защищенная зона побеждает при перекрытии
ZONE_PROTECTION_ORDER = ["R", "P", "I", "T", "E"]

EXIT_ALLOW = 0
EXIT_REQUIRE_HUMAN = 10
EXIT_ERROR = 2

DEFAULT_EXCLUSIONS = [
    ".ai-loop/ledger.jsonl",
    ".ai-loop/runs/",
    ".ai-loop/artifacts/",
    ".ai-loop/archive/",
    "**/__pycache__/*",
    "*.pyc",
]


class PolicyError(RuntimeError):
    """Исключение при ошибках загрузки или парсинга политик безопасности."""
    pass


class Policy:
    """Класс представления загруженной политики зон и рисков."""

    def __init__(self, protected: dict, risk: dict, fingerprint: str, policy_dir: str):
        self.protected = protected or {}
        self.risk = risk or {}
        self.fingerprint = fingerprint
        self.policy_dir = policy_dir

        enforcement = self.protected.get("enforcement") or {}
        self.diff_is_authoritative = bool(enforcement.get("diff_is_authoritative", True))
        self.mixed_diff_policy = enforcement.get("mixed_diff_policy", "MAX_RISK_WINS")
        self.default_unmatched = _level(enforcement.get("default_risk_for_unmatched", "CRITICAL"))

        self.exclusions = list(DEFAULT_EXCLUSIONS) + [
            str(p) for p in (enforcement.get("exclusions") or [])
        ]

        self.zones = self.protected.get("zones") or {}
        self.zone_default_risk = self.risk.get("zone_default_risk") or {}
        self.matrix = self.risk.get("matrix") or []
        self.gate = self.risk.get("gate") or {
            "LOW": "auto",
            "MEDIUM": "auto",
            "HIGH": "require_human",
            "CRITICAL": "require_human",
        }
        self.escalations = self.risk.get("escalations") or {}

    @property
    def version(self) -> str:
        return str(self.protected.get("version", "unknown"))


def _level(name: Any) -> str:
    text = str(name or "").strip().upper()
    if text not in LEVEL_INDEX:
        raise PolicyError(f"Неизвестный уровень риска: {name!r}")
    return text


def _max_level(a: str, b: str) -> str:
    return a if LEVEL_INDEX[a] >= LEVEL_INDEX[b] else b


def _bump(level: str, steps: int = 1) -> str:
    return LEVELS[min(len(LEVELS) - 1, LEVEL_INDEX[level] + max(0, steps))]


def find_policy_dir(repo: str, explicit: Optional[str] = None) -> str:
    """Поиск директории с политиками безопасности."""
    if explicit:
        return os.path.abspath(explicit)
    for candidate in (
        os.path.join(repo, ".ai-loop", "policy"),
        os.path.join(repo, "policy"),
        os.path.join(repo, "evolution", "policy"),
    ):
        if os.path.isdir(candidate):
            return candidate
    raise PolicyError(
        f"Директория политик не найдена в {repo}. Проверьте наличие .ai-loop/policy или policy."
    )


def load_policy(policy_dir: str) -> Policy:
    """Загрузка и верификация файлов protected_paths.yaml и risk_classification.yaml."""
    protected_path = os.path.join(policy_dir, "protected_paths.yaml")
    risk_path = os.path.join(policy_dir, "risk_classification.yaml")
    for path in (protected_path, risk_path):
        if not os.path.isfile(path):
            raise PolicyError(f"Отсутствует обязательный файл политики: {path}")

    digest = hashlib.sha256()
    for path in (protected_path, risk_path):
        with open(path, "rb") as handle:
            digest.update(handle.read())

    try:
        protected = miniyaml.load_path(protected_path)
        risk = miniyaml.load_path(risk_path)
    except Exception as exc:
        raise PolicyError(f"Ошибка парсинга политики ({exc}); аварийный отказ") from exc

    if not isinstance(protected, dict) or not isinstance(risk, dict):
        raise PolicyError("Файлы политик должны содержать ассоциативный массив (mapping)")

    return Policy(protected, risk, "sha256:" + digest.hexdigest(), policy_dir)


def _normalise(path: str) -> str:
    path = str(path).replace("\\", "/").strip()
    while path.startswith("./"):
        path = path[2:]
    return path.lstrip("/")


def _pattern_matches(pattern: str, path: str) -> bool:
    pattern = _normalise(str(pattern))
    if not pattern:
        return False
    if pattern.endswith("/"):
        return path == pattern.rstrip("/") or path.startswith(pattern)
    if pattern.startswith("**/"):
        suffix = pattern[3:]
        if path == suffix or path.endswith("/" + suffix) or fnmatch.fnmatch(path, suffix) or fnmatch.fnmatch(path, pattern):
            return True
    if any(ch in pattern for ch in "*?["):
        return fnmatch.fnmatch(path, pattern) or fnmatch.fnmatch(path, pattern + "/*")
    return path == pattern or path.startswith(pattern + "/")


def _specificity(pattern: str) -> int:
    pattern = _normalise(str(pattern))
    for index, ch in enumerate(pattern):
        if ch in "*?[":
            return index
    return len(pattern)


def zone_for(path: str, policy: Policy) -> Tuple[Optional[str], Optional[str]]:
    """Определение зоны для пути с учетом иерархии защиты."""
    for key in ZONE_PROTECTION_ORDER:
        spec = policy.zones.get(key)
        if not isinstance(spec, dict):
            continue
        best: Optional[str] = None
        for pattern in spec.get("paths") or []:
            if _pattern_matches(pattern, path):
                if best is None or _specificity(pattern) > _specificity(best):
                    best = str(pattern)
        if best is not None:
            return key, best

    for key, spec in policy.zones.items():
        if key in ZONE_PROTECTION_ORDER or not isinstance(spec, dict):
            continue
        for pattern in spec.get("paths") or []:
            if _pattern_matches(pattern, path):
                return key, str(pattern)
    return None, None


def matrix_for(path: str, policy: Policy) -> Optional[dict]:
    best: Optional[dict] = None
    best_spec = -1
    for entry in policy.matrix:
        if not isinstance(entry, dict):
            continue
        pattern = entry.get("path")
        if pattern and _pattern_matches(pattern, path):
            spec = _specificity(pattern)
            if spec > best_spec:
                best, best_spec = entry, spec
    return best


def is_excluded(path: str, policy: Policy) -> bool:
    path = _normalise(path)
    if "__pycache__/" in path or path.endswith(".pyc"):
        return True
    return any(_pattern_matches(pattern, path) for pattern in policy.exclusions)


def classify_path(path: str, policy: Policy) -> dict:
    """Классификация отдельного пути по зонам и матрице рисков."""
    path = _normalise(path)
    zone, zone_pattern = zone_for(path, policy)

    if zone is None:
        return {
            "path": path,
            "zone": None,
            "risk": policy.default_unmatched,
            "rule": "default_risk_for_unmatched",
            "note": "no zone rule matched this path; failing closed",
        }

    try:
        risk = _level(policy.zone_default_risk.get(zone, "CRITICAL"))
    except PolicyError:
        risk = "CRITICAL"
    rule = f"zone:{zone}:{zone_pattern}"

    entry = matrix_for(path, policy)
    if entry:
        try:
            entry_risk = _level(entry.get("risk"))
        except PolicyError:
            entry_risk = "CRITICAL"
        zone_spec = policy.zones.get(zone) or {}
        mutable_zone = bool(zone_spec.get("autonomous_mutation", False))
        if LEVEL_INDEX[entry_risk] > LEVEL_INDEX[risk] or mutable_zone:
            risk = entry_risk
            rule = f"matrix:{entry.get('path')}"
        else:
            rule = f"zone:{zone}:{zone_pattern} (matrix de-escalation ignored in protected zone)"
        if entry.get("human_approval_required") is True:
            risk = _max_level(risk, "HIGH")
            rule += " +human_approval_required"

    return {"path": path, "zone": zone, "risk": risk, "rule": rule}


def _git(repo: str, *args: str) -> str:
    """Вызов git с безопасной кодировкой UTF-8."""
    result = subprocess.run(
        ["git", "-C", repo, *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        raise PolicyError(f"git {' '.join(args)} завершился с ошибкой: {result.stderr.strip()}")
    return result.stdout


def collect_paths(args, repo: str) -> Tuple[List[str], str, int]:
    """Сбор путей диффа из git или аргументов."""
    if args.paths:
        return sorted({_normalise(p) for p in args.paths}), "explicit --paths", 0
    if args.paths_file:
        with open(args.paths_file, "r", encoding="utf-8") as handle:
            paths = [_normalise(line.strip()) for line in handle if line.strip()]
        return sorted(set(paths)), f"paths file {args.paths_file}", 0

    if args.range:
        diff_args = ["diff", "--numstat", args.range]
        source = f"git diff {args.range}"
    elif args.staged:
        diff_args = ["diff", "--numstat", "--cached"]
        source = "git diff --cached"
    else:
        diff_args = ["diff", "--numstat", "HEAD"]
        source = "git diff HEAD"

    raw = _git(repo, *diff_args)
    paths_set: set[str] = set()
    lines_changed = 0
    for line in raw.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        added, removed, path = parts[0], parts[1], parts[-1]
        for count in (added, removed):
            if count.isdigit():
                lines_changed += int(count)
        paths_set.add(_normalise(path))

    if not args.range and not args.staged:
        for path in _git(repo, "ls-files", "--others", "--exclude-standard").splitlines():
            if path.strip():
                paths_set.add(_normalise(path.strip()))
                source = "git diff HEAD + untracked"

    return sorted(paths_set), source, lines_changed


def apply_escalations(base: str, classified: List[dict], policy: Policy,
                      files_changed: int, lines_changed: int) -> Tuple[str, List[dict]]:
    """Применение правил эскалации риска."""
    risk = base
    applied: List[dict] = []
    esc = policy.escalations

    def record(rule: str, new_risk: str, detail: str) -> None:
        nonlocal risk
        if LEVEL_INDEX[new_risk] > LEVEL_INDEX[risk]:
            applied.append({"rule": rule, "from": risk, "to": new_risk, "detail": detail})
            risk = new_risk

    zones = {item["zone"] for item in classified}

    setting = esc.get("test_and_product_same_diff")
    if setting and "T" in zones and (zones - {"T"}):
        steps = setting if (isinstance(setting, int) and not isinstance(setting, bool)) else 1
        record(
            "test_and_product_same_diff",
            _bump(risk, steps),
            "Тесты и продуктовый код изменены в одном диффе (нарушение TDD)",
        )

    if "P" in zones:
        record("policy_plane_touched", "CRITICAL", "Изменение затрагивает контур управления (Zone P)")

    unmatched = [item["path"] for item in classified if item["zone"] is None]
    if unmatched:
        record(
            "unmatched_path",
            policy.default_unmatched,
            f"{len(unmatched)} путей не сопоставлены ни с одной зоной: {', '.join(unmatched[:5])}",
        )

    return risk, applied


def self_check(policy: Policy, repo: str) -> List[str]:
    """Аудит структуры политик на наличие уязвимостей и ослаблений."""
    problems: List[str] = []

    if not policy.diff_is_authoritative:
        problems.append("enforcement.diff_is_authoritative отключен: политика не может доверять самоотчетам")
    if policy.mixed_diff_policy != "MAX_RISK_WINS":
        problems.append("enforcement.mixed_diff_policy должен быть установлен в MAX_RISK_WINS")
    if policy.default_unmatched != "CRITICAL":
        problems.append("enforcement.default_risk_for_unmatched должен быть CRITICAL")

    for key in ("R", "P"):
        spec = policy.zones.get(key)
        if isinstance(spec, dict) and spec.get("autonomous_mutation"):
            problems.append(f"Зона {key} имеет autonomous_mutation: true; защищенные зоны должны быть immutable")

    return problems


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", default=".", help="Корень репозитория")
    parser.add_argument("--policy-dir", default=None, help="Переопределение директории политик")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--range", help="Диапазон ревизий (например, main..HEAD)")
    source.add_argument("--staged", action="store_true", help="Классифицировать staged diff")
    source.add_argument("--worktree", action="store_true", help="Классифицировать working tree vs HEAD")
    source.add_argument("--paths", nargs="+", help="Список путей")
    source.add_argument("--paths-file", help="Файл со списком путей")
    parser.add_argument("--self-check", action="store_true", help="Самопроверка целостности политик")
    parser.add_argument("--json", action="store_true", help="Вывод в формате JSON")
    parser.add_argument("--explain", action="store_true", help="Вывод детальной таблицы по путям")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    repo = os.path.abspath(args.repo)

    try:
        policy_dir = find_policy_dir(repo, args.policy_dir)
        policy = load_policy(policy_dir)
    except PolicyError as exc:
        payload = {
            "schema": SCHEMA,
            "risk": "CRITICAL",
            "gate": "require_human",
            "decision": "require_human",
            "error": str(exc),
            "reasons": ["Контур управления недоступен или поврежден; fail-closed"],
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return EXIT_ERROR

    if args.self_check:
        problems = self_check(policy, repo)
        payload = {
            "schema": "ai-loop/self-check/v1",
            "policy_dir": policy_dir,
            "policy_fingerprint": policy.fingerprint,
            "ok": not problems,
            "problems": problems,
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return EXIT_ALLOW if not problems else EXIT_REQUIRE_HUMAN

    try:
        paths, source, lines_changed = collect_paths(args, repo)
    except PolicyError as exc:
        print(json.dumps({
            "schema": SCHEMA, "risk": "CRITICAL", "gate": "require_human",
            "decision": "require_human", "error": str(exc),
        }, indent=2, ensure_ascii=False))
        return EXIT_ERROR

    excluded = [p for p in paths if is_excluded(p, policy)]
    paths = [p for p in paths if not is_excluded(p, policy)]

    classified = [classify_path(path, policy) for path in paths]
    base = "LOW"
    for item in classified:
        base = _max_level(base, item["risk"])
    if not classified:
        base = "LOW"

    risk, escalations = apply_escalations(base, classified, policy, len(paths), lines_changed)
    gate = str(policy.gate.get(risk, "require_human"))
    decision = "allow" if gate == "auto" else "require_human"

    reasons = [f"{item['path']} -> {item['zone'] or '-'} / {item['risk']} ({item['rule']})"
               for item in classified if item["risk"] == risk][:10]

    payload = {
        "schema": SCHEMA,
        "source": source,
        "diff_is_authoritative": policy.diff_is_authoritative,
        "policy_dir": policy_dir,
        "policy_version": policy.version,
        "policy_fingerprint": policy.fingerprint,
        "files_considered": len(paths),
        "excluded": excluded,
        "lines_changed": lines_changed,
        "paths": classified,
        "base_risk": base,
        "escalations": escalations,
        "risk": risk,
        "gate": gate,
        "decision": decision,
        "reasons": reasons,
    }

    if args.json:
        print(json.dumps(payload, ensure_ascii=False))
    else:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        if args.explain:
            width = max((len(i["path"]) for i in classified), default=4)
            print("\npath".ljust(width + 2) + "zone  risk      rule", file=sys.stderr)
            for item in classified:
                print(
                    item["path"].ljust(width + 2)
                    + f"{item['zone'] or '-':<6}{item['risk']:<10}{item['rule']}",
                    file=sys.stderr,
                )

    return EXIT_ALLOW if decision == "allow" else EXIT_REQUIRE_HUMAN


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(json.dumps({
            "schema": SCHEMA, "risk": "CRITICAL", "gate": "require_human",
            "decision": "require_human", "error": f"unexpected failure: {exc}",
        }, indent=2, ensure_ascii=False))
        sys.exit(EXIT_ERROR)
