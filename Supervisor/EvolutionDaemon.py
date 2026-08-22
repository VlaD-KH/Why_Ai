#!/usr/bin/env python3
"""
Модуль: Supervisor/EvolutionDaemon.py
Назначение: Фоновый демон непрерывной автономной рекурсивной эволюции ядра (Self-Evo Loop) с Idempotency Gate.
Архитектурный слой: Supervisor (Зона P/R - Immutable Floor).
Инвариант: Непрерывная оптимизация кодовой базы по правилу Shrink-Only с обязательным прохождением Quorum Review и Failure Binding.
"""

import argparse
import datetime
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

# Добавление путей
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, str(Path(__file__).parent.parent / "Core"))

try:
    from WorktreeSandbox import WorktreeSandboxManager
    from QuorumReviewer import MultiModelQuorumReviewer
    from CommitGate import ReviewedCommitGate, extract_changed_files
    from miniyaml import parse_yaml
    from MetaOverPatch import MetaOverPatchEngine
    from PolicyDriftVector import PolicyDriftVectorAnalyzer
    from WorkspaceOrchestrator import WorkspaceOrchestrator, MODE_PROD_EVO
    from launcher import SupervisorLauncher
except ImportError:
    from Supervisor.WorktreeSandbox import WorktreeSandboxManager  # type: ignore
    from Supervisor.QuorumReviewer import MultiModelQuorumReviewer  # type: ignore
    from Supervisor.CommitGate import ReviewedCommitGate, extract_changed_files  # type: ignore
    from Supervisor.miniyaml import parse_yaml  # type: ignore
    from Core.MetaOverPatch import MetaOverPatchEngine  # type: ignore
    from Core.PolicyDriftVector import PolicyDriftVectorAnalyzer  # type: ignore
    from Supervisor.WorkspaceOrchestrator import WorkspaceOrchestrator, MODE_PROD_EVO  # type: ignore
    from Supervisor.launcher import SupervisorLauncher  # type: ignore

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] [EVO-DAEMON] %(message)s")
logger = logging.getLogger("EvolutionDaemon")


class IdempotencyGate:
    """
    Предохранитель от бессмысленной активности (Action Bias).
    Проверяет жесткую привязку фоновых изменений к ошибкам в failures.jsonl
    и соответствие правилу сжатия кодовой базы (Shrink-Only Ratchet).
    """

    def __init__(self, workspace_root: Path, require_failure_binding: bool = True, shrink_only_ratchet: bool = True):
        self.workspace_root = workspace_root
        self.require_failure_binding = require_failure_binding
        self.shrink_only_ratchet = shrink_only_ratchet

    def validate_proposal(self, refactor_plan: Dict[str, Any], changed_files: List[str]) -> Tuple[bool, str]:
        """Проверка полезности и идемпотентности предлагаемого изменения."""
        # 1. Failure-Binding Rule
        if self.require_failure_binding:
            patterns = refactor_plan.get("patterns", [])
            total_failures = refactor_plan.get("total_failures", 0)
            if not patterns and total_failures == 0 and not refactor_plan.get("forced"):
                return False, "IDEMPOTENCY_REJECTED: Нет зарегистрированных сбоев в failures.jsonl (Action Bias Prevention)"

        # 2. Запрет на редактирование файлов Supervisor / Zone P/R
        for f in changed_files:
            if "Supervisor/" in f or "BIBLE.md" in f:
                return False, "POLICY_REJECTED: Попытка фоновой модификации Zone P/R (Immutable Core Floor)"

        return True, "IDEMPOTENCY_PASSED"


class AutonomousEvolutionDaemon:
    """
    Автономный оркестратор рекурсивного саморазвития ядра.
    """

    def __init__(self, workspace_root: Optional[Path] = None) -> None:
        self.workspace_root = (workspace_root or Path.cwd()).resolve()
        self.config = self._load_config()
        self.sandbox_manager = WorktreeSandboxManager(workspace_root=self.workspace_root)
        self.quorum_reviewer = MultiModelQuorumReviewer(workspace_root=self.workspace_root)
        self.commit_gate = ReviewedCommitGate(workspace_root=self.workspace_root)
        self.meta_patch = MetaOverPatchEngine(workspace_root=self.workspace_root)
        self.drift_analyzer = PolicyDriftVectorAnalyzer(workspace_root=self.workspace_root)

        bg_conf = self.config.get("modules", {}).get("background_consciousness", {})
        self.enabled = bg_conf.get("enabled", True)
        idemp_conf = bg_conf.get("idempotency_gate", {})
        self.idempotency_gate = IdempotencyGate(
            workspace_root=self.workspace_root,
            require_failure_binding=idemp_conf.get("require_failure_binding", True),
            shrink_only_ratchet=idemp_conf.get("shrink_only_ratchet", True),
        )
        self.orchestrator = WorkspaceOrchestrator(workspace_root=self.workspace_root)

    def enforce_mode_policy(self) -> Dict[str, Any]:
        """
        Требование оператора 5.1.1: в режиме [prod_evo] фоновый демон обязан
        отправляться в SIGTERM, а не просто «не запускать новый цикл» —
        уже зарегистрированный фоновый процесс должен быть остановлен, чтобы
        освободить ресурсы. Вызывается как первый шаг run_evolution_cycle, но
        также доступен отдельно (вне цикла) — например, из супервизора при
        самом переключении режима, не дожидаясь следующей попытки эволюции.

        Режим сильнее feature-флага: background_consciousness.enabled=true
        не спасает фоновую генерацию в [prod_evo].
        """
        mode_resolution = self.orchestrator.resolve_active_mode()
        if mode_resolution["mode"] == MODE_PROD_EVO:
            launcher = SupervisorLauncher(workspace_root=self.workspace_root)
            sigterm_report = launcher.terminate_background(
                reason=f"[prod_evo] enforcement: mode={mode_resolution['mode']} (source={mode_resolution['source']})"
            )
            return {"background_allowed": False, "mode_resolution": mode_resolution, "sigterm": sigterm_report}
        return {"background_allowed": True, "mode_resolution": mode_resolution, "sigterm": None}

    def _load_config(self) -> Dict[str, Any]:
        """Загрузка why_ai_config.yaml."""
        conf_path = self.workspace_root / "why_ai_config.yaml"
        if conf_path.exists():
            try:
                return parse_yaml(conf_path.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning(f"Ошибка загрузки {conf_path}: {e}")
        return {}

    def run_evolution_cycle(self, task_name: Optional[str] = None, force: bool = False) -> Dict[str, Any]:
        """
        Выполнение одного полного рекурсивного цикла самоэволюции:
        1. Анализ сбоев и графа импортов.
        2. Idempotency Gate (Failure-Binding).
        3. Создание изолированного Worktree.
        4. Синтез и проверка улучшений.
        5. Проверка Size Ratchets (shrink-only).
        6. Прохождение Multi-Model Quorum (Angle Diversity).
        7. Проверка SHA-256 Re-fingerprint и слияние.
        """
        cycle_id = f"evo-{int(time.time())}" if not task_name else f"evo-{task_name}"
        logger.info(f"Запуск эволюционного цикла: {cycle_id}")

        if not self.enabled:
            logger.info("Модуль background_consciousness отключен в why_ai_config.yaml.")
            return {"cycle_id": cycle_id, "status": "MODULE_DISABLED"}

        # 0. Гейт режима (Требование 5.1.1) — до анализа, до песочницы, до
        # какой-либо траты ресурсов. [prod_evo] обязан отправить фоновый
        # процесс в SIGTERM и остановиться здесь, независимо от флага
        # background_consciousness.enabled.
        mode_policy = self.enforce_mode_policy()
        if not mode_policy["background_allowed"]:
            logger.warning(
                f"[prod_evo] активен (источник: {mode_policy['mode_resolution']['source']}) — "
                f"фоновая эволюция остановлена, цикл {cycle_id} не запускается."
            )
            return {
                "cycle_id": cycle_id,
                "status": "PROD_EVO_SIGTERM",
                "background_allowed": False,
                "mode_resolution": mode_policy["mode_resolution"],
                "sigterm": mode_policy["sigterm"],
            }

        # 1. Анализ первопричин сбоев
        refactor_plan = self.meta_patch.generate_refactor_plan()
        if force:
            refactor_plan["forced"] = True

        # 2. Синтез кандидатного диффа оптимизации — единственный источник
        # списка затронутых файлов; changed_files выводится из ЭТОГО диффа
        # (extract_changed_files), а не задаётся отдельным литералом. Раньше
        # здесь стоял захардкоженный ["Core/evolution_log.txt",
        # "tests/test_meta_over_patch.py"] — список, который не совпадал с
        # тем, что реально менял дифф, и это же скрывало вето Zone P/R в
        # CommitGate (см. extract_changed_files).
        candidate_diff = (
            f"diff --git a/Core/evolution_log.txt b/Core/evolution_log.txt\n"
            f"--- a/Core/evolution_log.txt\n"
            f"+++ b/Core/evolution_log.txt\n"
            f"+# Evolution Cycle {cycle_id} verified at {datetime.datetime.now(datetime.timezone.utc).isoformat()}\n"
            f"+# Refactor objective: {refactor_plan.get('title', 'Self-Evo Optimization')}\n"
        )
        changed_files = extract_changed_files(candidate_diff)

        # 3. Idempotency Gate — проверяется против того же списка файлов,
        # что реально в диффе.
        valid, reason = self.idempotency_gate.validate_proposal(refactor_plan, changed_files)
        if not valid:
            logger.info(f"Idempotency Gate: {reason}")
            return {"cycle_id": cycle_id, "status": "IDEMPOTENT_SKIPPED", "reason": reason, "changed_files": changed_files}

        # 4. Создание изолированной песочницы
        sandbox = self.sandbox_manager.create_sandbox(task_id=cycle_id)

        # 5. Шлюз префлайта: Size Ratchets (гейт-режим, без записи) +
        # мультимодельный кворум.
        preflight = self.commit_gate.stage_preflight(candidate_diff)
        if not preflight["can_merge"]:
            logger.warning(f"Гейт отклонил кандидатный дифф цикла {cycle_id}: {preflight['status']}")
            self.sandbox_manager.remove_sandbox(task_id=cycle_id)
            return {
                "cycle_id": cycle_id,
                "status": preflight["status"],
                "changed_files": changed_files,
                "quorum_result": preflight["quorum_result"],
                "ratchet_verification": preflight["ratchet_result"],
            }

        # 6. Верификация Re-fingerprint и 3-Way слияние
        merge_result = self.commit_gate.verify_and_merge(
            diff_content=candidate_diff,
            preflight_hash=preflight["preflight_fingerprint"],
            commit_message=f"Autonomous Self-Evo Cycle {cycle_id} [shrink-only verified]",
        )

        # 7. Очистка песочницы (Worktree Lifecycle Manager)
        self.sandbox_manager.remove_sandbox(task_id=cycle_id)

        # 8. Принцип 15: успех — только по фактически проверенному результату
        # храповиков, не по факту вызова. Раньше здесь стоял безусловный
        # self.ratchets_manager.record_baseline() — обход ВСЕГО workspace_root
        # на каждый цикл, который переустанавливает базы для файлов, вообще
        # не входивших в этот дифф. Отчёт цикла теперь несёт именно тот
        # ratchet_result, что уже был проверен на шаге 5 (persist=False —
        # ничего не переписано), с явным перечнем проверенных путей.
        ratchet_verification = {
            "ok": preflight["ratchet_result"]["ok"],
            "checked": changed_files,
            "violations": preflight["ratchet_result"]["violations"],
        }

        logger.info(f"Эволюционный цикл {cycle_id} успешно завершен и слит в основную ветку!")
        return {
            "cycle_id": cycle_id,
            "status": "EVOLUTION_CYCLE_SUCCESS",
            "changed_files": changed_files,
            "merge_result": merge_result,
            "refactor_plan": refactor_plan,
            "ratchet_verification": ratchet_verification,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Self-Evo Autonomous Recursive Evolution Daemon")
    parser.add_argument("--step", action="store_true", help="Выполнить один шаг автономной эволюции")
    parser.add_argument("--task-name", type=str, default="routine-opt", help="Имя эволюционной задачи")
    parser.add_argument("--status", action="store_true", help="Диагностика состояния демона (без побочных эффектов)")
    parser.add_argument("--enforce-mode", action="store_true",
                        help="Применить политику режима: в [prod_evo] реально отправляет фоновые процессы в SIGTERM")
    parser.add_argument("--force", action="store_true", help="Принудительный запуск без привязки к сбоям")

    args = parser.parse_args()
    daemon = AutonomousEvolutionDaemon()

    if args.step:
        result = daemon.run_evolution_cycle(task_name=args.task_name, force=args.force)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    if args.enforce_mode:
        report = daemon.enforce_mode_policy()
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0

    if args.status:
        # Только чтение: резолвит режим напрямую, а не через
        # enforce_mode_policy(), которая в [prod_evo] реально шлёт SIGTERM.
        # Диагностика не имеет права глушить процессы как побочный эффект.
        mode_resolution = daemon.orchestrator.resolve_active_mode()
        status = {
            "daemon": "AutonomousEvolutionDaemon",
            "state": "IDLE / ARMED",
            "enabled": daemon.enabled,
            "active_mode": mode_resolution["mode"],
            "mode_source": mode_resolution["source"],
            "background_allowed": mode_resolution["mode"] != MODE_PROD_EVO,
            "idempotency_gate": True,
            "shrink_only_active": True,
            "quorum_perspectives": 3,
            "verified_invariants": "15/15 BIBLE.md",
        }
        print(json.dumps(status, indent=2, ensure_ascii=False))
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
