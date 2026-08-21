#!/usr/bin/env python3
"""
Модуль: Supervisor/WorkspaceOrchestrator.py
Назначение: Динамический оркестратор топологии Hierarchy v3 и инициализатор безопасных настроек Git для песочниц.
Архитектурный слой: Supervisor (Зона P/R).
"""

import argparse
import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, Any, Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] [ORCHESTRATOR] %(message)s")
logger = logging.getLogger("WorkspaceOrchestrator")


class WorkspaceOrchestrator:
    """
    Оркестратор рабочей области: управляет инверсией рангов Hierarchy v3
    и гарантирует кроссплатформенные инварианты Git.
    """

    def __init__(self, workspace_root: Optional[Path] = None) -> None:
        self.workspace_root = (workspace_root or Path.cwd()).resolve()
        self.state_file = self.workspace_root / ".ai_workspace_state.json"

    def harden_git_invariants(self, target_repo: Optional[Path] = None) -> Dict[str, bool]:
        """
        Фиксация инвариантов Git на Windows/Unix для сохранения криптографической точности хэшей.
        Отключает автозамену CRLF и экранирование не-ASCII символов в путях.
        """
        repo = target_repo or self.workspace_root
        results = {}
        configs = [
            ("core.autocrlf", "false"),
            ("core.eol", "lf"),
            ("core.quotepath", "false"),
        ]

        for key, value in configs:
            try:
                subprocess.run(
                    ["git", "-C", str(repo), "config", "--local", key, value],
                    capture_output=True,
                    check=True,
                    text=True,
                )
                results[key] = True
                logger.info(f"Git invariant зафиксирован: {key}={value}")
            except Exception as e:
                logger.warning(f"Не удалось установить {key}={value}: {e}")
                results[key] = False

        return results

    def switch_mode(self, mode: str, project_name: str = "default_project") -> Dict[str, Any]:
        """
        Переключение топологического режима Hierarchy v3:
        - 'agent' ([self_evo]): Agent ⊃ Project (Ранг Agent = 1, Ранг Project = 3)
        - 'project' ([prod_evo]): Project ⊃ agent (Ранг Project = 1, Ранг Agent = 2)
        """
        mode = mode.lower()
        if mode not in ("agent", "project"):
            raise ValueError(f"Неизвестный режим: {mode}. Допустимы: 'agent', 'project'.")

        self.harden_git_invariants()

        if mode == "agent":
            # [self_evo]: Агент суверенен
            topology = {
                "mode": "AGENT_MODE_SELF_EVO",
                "hierarchy": "Agent ⊃ Project",
                "rank_map": {
                    "workspace_root": 0,
                    "Supervisor": 1,
                    "Core": 1,
                    "Tool": 1,
                    "Project": 3,
                },
                "operative_goal": "Self-evolution and internal tool enhancement",
                "question": "Does this weaken my own control plane?",
            }
        else:
            # [prod_evo]: Внешний проект в приоритете
            project_dir = self.workspace_root / f"Project_{project_name}"
            topology = {
                "mode": "PROJECT_MODE_PROD_EVO",
                "hierarchy": "Project ⊃ agent",
                "rank_map": {
                    "workspace_root": 0,
                    f"Project_{project_name}": 1,
                    "agent_instance": 2,
                },
                "operative_goal": f"100% focus on external module: {project_name}",
                "question": "Does this break the project's invariants?",
            }

        state_payload = {
            "current_mode": mode,
            "project_name": project_name,
            "topology": topology,
            "updated_at": str(Path.cwd()),
        }

        self.state_file.write_text(json.dumps(state_payload, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info(f"Режим переключен на: {topology['mode']} ({topology['hierarchy']})")
        return state_payload

    def get_current_topology(self) -> Dict[str, Any]:
        """Получение текущего состояния топологии и рангов."""
        if self.state_file.exists():
            try:
                return json.loads(self.state_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        # По умолчанию режим Project
        return self.switch_mode("project", "default")


def main() -> int:
    parser = argparse.ArgumentParser(description="Hierarchy v3 Workspace Orchestrator & Git Hardener")
    parser.add_argument("--switch-mode", choices=["project", "agent"], help="Переключить режим работы")
    parser.add_argument("--project-name", default="vanguard", help="Имя целевого внешнего проекта")
    parser.add_argument("--harden-git", action="store_true", help="Зафиксировать инварианты Git (CRLF/quotepath)")
    parser.add_argument("--status", action="store_true", help="Показать текущую топологию")

    args = parser.parse_args()
    orchestrator = WorkspaceOrchestrator()

    if args.harden_git:
        results = orchestrator.harden_git_invariants()
        print(json.dumps(results, indent=2))
        return 0

    if args.switch_mode:
        state = orchestrator.switch_mode(mode=args.switch_mode, project_name=args.project_name)
        print(json.dumps(state, indent=2, ensure_ascii=False))
        return 0

    if args.status:
        state = orchestrator.get_current_topology()
        print(json.dumps(state, indent=2, ensure_ascii=False))
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
