#!/usr/bin/env python3
"""
Модуль: Supervisor/ProposalSynthesizer.py
Назначение: звено 4 конвейера самоэволюции — синтез кандидатного диффа.
Архитектурный слой: Supervisor (Зона R).

До R-5 на этом месте в EvolutionDaemon стоял литерал: дифф из двух строк
комментария в Core/evolution_log.txt. Конвейер «успешно» публиковал его в
ветку при любом состоянии — предложителя не существовало
(docs/final_vision/06-self-evo-audit.md, звено 4).

Здесь:
  * собирается промпт из плана Meta-over-Patch и содержимого целевых
    файлов на HEAD (кандидат применяется к HEAD — контекст обязан быть
    оттуда же, а не из грязного рабочего дерева);
  * вызывается предложитель — объект с контрактом LLMConnector.propose()
    (Tool/connectors/llm_connector.py). Сеть — только там: этот модуль
    сетевых вызовов не делает (Принцип 15);
  * из ответа извлекается ровно один unified diff.

Чего здесь НЕТ, и это намеренно: решения, можно ли применять кандидата.
Это делают AutonomyGate, кворум, храповики и прогон тестов в песочнице —
Принцип 5, предложитель ≠ оценщик. Модель лишь заранее узнаёт правила,
чтобы не тратить вызов на заведомо отклоняемый дифф.

Любой отказ — fail-closed: нет предложителя, нет ключа, отказ модели,
обрезанный ответ, два диффа вместо одного — кандидата нет, и цикл ничего
не публикует.
"""

import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from AutonomyGate import floor_violation
except ImportError:
    from Supervisor.AutonomyGate import floor_violation  # type: ignore

MAX_CONTEXT_BYTES = 60_000
MAX_FILE_BYTES = 20_000

SYSTEM_PROMPT = """Ты — предложитель в контуре самоэволюции проекта Why_Ai.
Твой ответ не применяется напрямую: дифф проходит детерминированные гейты,
применяется в изолированной копии репозитория, там прогоняется весь набор
тестов, и только тогда кандидат публикуется в отдельную ветку на ревью
человеку. Слияние в main — право человека.

Формат ответа — строго одно из двух:
1. Ровно один блок ```diff с unified diff в формате `git diff`: заголовки
   `diff --git a/<путь> b/<путь>`, `--- a/…`/`+++ b/…`, ханки `@@`. Дифф
   обязан применяться `git apply` к текущему HEAD. Новый файл — с
   `new file mode 100644` и `--- /dev/null`.
2. Одна строка NO_SAFE_CHANGE, если безопасного полезного изменения нет.

Кандидат будет отклонён целиком, если:
- затрагивает Supervisor/, .ai-loop/, .github/, CODEOWNERS, BIBLE.md,
  .size_ratchets.json, .gitignore, .gitattributes или путь вне зон проекта
  (разрешены зоны Eye/, docs/, Tool/skills/, tests/, Core/, Tool/connectors/);
- меняет Python-код (не тест) без изменения или добавления теста в tests/
  в том же диффе;
- добавляет больше 800 строк или раздувает существующий файл больше чем на
  15% сверх зафиксированного размера — предпочитай сокращение;
- содержит строки «TODO:» или заглушки;
- тянет зависимости вне стандартной библиотеки Python;
- ломает хотя бы один тест в tests/.

Изменение должно устранять первопричину повторяющегося сбоя из плана
(Meta-over-Patch), а не накладывать локальную заплатку."""

_FENCE_RE = re.compile(r"```[ \t]*([A-Za-z0-9_+-]*)[ \t]*\r?\n(.*?)```", re.DOTALL)


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, timeout=60)


def gather_context(workspace_root: Path, refactor_plan: Dict[str, Any],
                   max_bytes: int = MAX_CONTEXT_BYTES) -> List[Dict[str, str]]:
    """Содержимое целевых файлов плана на HEAD, без защищённых и бинарных."""
    files: List[Dict[str, str]] = []
    total = 0
    seen = set()
    for step in refactor_plan.get("steps") or []:
        target = str(step.get("target_module") or "").replace("\\", "/").strip()
        if not target or floor_violation(target):
            continue  # недоступную цель модели не показываем: правка туда будет отклонена
        listed = _git(workspace_root, "ls-tree", "-r", "--name-only", "HEAD", "--", target)
        if listed.returncode != 0:
            continue
        for rel in listed.stdout.decode("utf-8", "replace").splitlines():
            rel = rel.strip()
            if not rel or rel in seen or floor_violation(rel):
                continue
            seen.add(rel)
            blob = _git(workspace_root, "show", f"HEAD:{rel}")
            data = blob.stdout
            if blob.returncode != 0 or b"\x00" in data or len(data) > MAX_FILE_BYTES:
                continue
            if total + len(data) > max_bytes:
                continue
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                continue
            files.append({"path": rel, "text": text})
            total += len(data)
    return files


def build_prompt(refactor_plan: Dict[str, Any], context_files: List[Dict[str, str]]) -> str:
    plan_view = {
        "title": refactor_plan.get("title"),
        "total_failures": refactor_plan.get("total_failures"),
        "patterns": refactor_plan.get("patterns"),
        "steps": refactor_plan.get("steps"),
    }
    parts = [
        "План рефакторинга по зарегистрированным сбоям (Core/failures.jsonl → MetaOverPatch):",
        "```json", json.dumps(plan_view, ensure_ascii=False, indent=2), "```",
        "",
    ]
    if context_files:
        parts.append("Текущее содержимое целевых файлов на HEAD:")
        for f in context_files:
            parts += ["", f"### {f['path']}", "```", f["text"].rstrip("\n"), "```"]
    else:
        parts.append("Целевые файлы плана на HEAD не найдены или недоступны автономному кандидату.")
    parts += ["", "Предложи одно изменение по правилам из системного сообщения."]
    return "\n".join(parts)


def extract_unified_diff(text: str) -> Tuple[Optional[str], Optional[str]]:
    """Ровно один git-style diff из ответа модели, либо код отказа."""
    if not text:
        return None, "NO_DIFF_IN_PROPOSAL"
    normalized = text.replace("\r\n", "\n")
    blocks = [body for lang, body in _FENCE_RE.findall(normalized)
              if lang in ("", "diff", "patch") and "diff --git " in body]
    if len(blocks) > 1:
        return None, "AMBIGUOUS_PROPOSAL"
    if blocks:
        diff = blocks[0]
    elif normalized.lstrip().startswith("diff --git "):
        diff = normalized.strip("\n")
    else:
        # Без заголовков `diff --git` список затронутых файлов не выводится
        # (CommitGate.extract_changed_files) — такой дифф гейты не проверят.
        return None, "NO_DIFF_IN_PROPOSAL"
    diff = diff.lstrip("\n")
    if not diff.endswith("\n"):
        diff += "\n"
    return diff, None


def synthesize(proposer: Any, refactor_plan: Dict[str, Any], workspace_root: Path) -> Dict[str, Any]:
    """Синтез кандидата. `ok: True` — только при единственном валидном диффе."""
    context_files = gather_context(Path(workspace_root), refactor_plan)
    prompt = build_prompt(refactor_plan, context_files)
    result: Dict[str, Any] = {
        "ok": False, "status": None, "diff": None, "error": None,
        "prompt": prompt, "prompt_sha256": "sha256:" + hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "context_paths": [f["path"] for f in context_files],
        "response_text": None, "model": None, "usage": None, "stop_reason": None,
    }
    if proposer is None:
        result.update(status="PROPOSER_UNAVAILABLE", error="предложитель не сконфигурирован")
        return result

    try:
        answer = proposer.propose(prompt, system=SYSTEM_PROMPT)
    except Exception as exc:  # noqa: BLE001 — сбой транспорта не роняет цикл
        result.update(status="PROPOSAL_FAILED", error=f"{type(exc).__name__}: {exc}"[:600])
        return result

    result.update(response_text=answer.get("text"), model=answer.get("model"),
                  usage=answer.get("usage"), stop_reason=answer.get("stop_reason"))
    if not answer.get("proposed"):
        code = answer.get("error") or "UNKNOWN"
        status = {"NO_API_KEY": "PROPOSER_UNAVAILABLE", "REFUSAL": "PROPOSAL_REFUSED"}.get(code, "PROPOSAL_FAILED")
        result.update(status=status, error=f"{code}: {answer.get('error_detail') or ''}".strip()[:600])
        return result
    if answer.get("stop_reason") not in ("end_turn", "stop_sequence"):
        # max_tokens и прочее: ответ обрезан, дифф мог потерять хвост.
        result.update(status="PROPOSAL_INCOMPLETE", error=f"stop_reason={answer.get('stop_reason')}")
        return result

    diff, err = extract_unified_diff(answer.get("text") or "")
    if err:
        result.update(status=err)
        return result
    result.update(ok=True, status="PROPOSAL_READY", diff=diff)
    return result
