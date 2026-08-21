#!/usr/bin/env python3
"""
Модуль: Supervisor/WorktreeSandbox.py
Назначение: Управление жизненным циклом изолированных эфемерных рабочих деревьев Git Worktrees для субагентов.
Архитектурный слой: Supervisor (Зона P/R - Immutable Core Floor).
Инвариант: Субагенты Scout и Child работают строго в изолированных worktrees с гарантированной фиксацией Windows CRLF/quotepath и авто-очисткой Worktree Lifecycle Manager.
"""

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] [WORKTREE] %(message)s")
logger = logging.getLogger("WorktreeSandbox")

WORKTREES_DIR = Path("worktrees")


class WorktreeLifecycleManager:
    """
    Управление детерминированным жизненным циклом песочниц.
    Обеспечивает высвобождение дескрипторов Windows и безопасное удаление не закоммиченных веток.
    """

    @staticmethod
    def cleanup_all(workspace_root: Path) -> int:
        """Принудительная очистка всех зависших рабочих деревьев и git worktree prune."""
        base_dir = workspace_root / WORKTREES_DIR
        pruned_count = 0
        if base_dir.exists():
            for item in base_dir.iterdir():
                if item.is_dir():
                    try:
                        subprocess.run(["git", "-C", str(workspace_root), "worktree", "remove", "--force", str(item)], capture_output=True)
                        shutil.rmtree(item, ignore_errors=True)
                        pruned_count += 1
                    except Exception as e:
                        logger.warning(f"Ошибка удаления worktree {item}: {e}")
        subprocess.run(["git", "-C", str(workspace_root), "worktree", "prune"], capture_output=True)
        return pruned_count


class WorktreeSandboxManager:
    """
    Менеджер изолированных песочниц на базе Git Worktrees.
    """

    def __init__(self, workspace_root: Optional[Path] = None) -> None:
        self.workspace_root = (workspace_root or Path.cwd()).resolve()
        self.worktrees_base = self.workspace_root / WORKTREES_DIR
        self.worktrees_base.mkdir(parents=True, exist_ok=True)
        self.lifecycle_manager = WorktreeLifecycleManager()

    def _run_git(self, args: List[str], cwd: Optional[Path] = None) -> subprocess.CompletedProcess:
        """Безопасный вызов git команд с кодировкой UTF-8."""
        cmd = ["git", "-C", str(cwd or self.workspace_root)] + args
        res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        return res

    def create_sandbox(self, task_id: str, base_ref: str = "HEAD") -> Dict[str, Any]:
        """
        Создание изолированного worktree для задачи:
        1. Создает ветку task/<task_id>
        2. Монтирует worktree в worktrees/<task_id>
        3. Принудительно устанавливает core.autocrlf=false, core.eol=lf, core.quotepath=false
        """
        clean_task_id = "".join(c for c in task_id if c.isalnum() or c in ("-", "_")).strip()
        if not clean_task_id:
            raise ValueError("Недопустимый task_id для создания песочницы.")

        target_dir = self.worktrees_base / clean_task_id
        branch_name = f"sandbox/{clean_task_id}"

        if target_dir.exists():
            logger.warning(f"Песочница {target_dir} уже существует, очистка...")
            self.remove_sandbox(clean_task_id)

        # Создаем worktree
        add_res = self._run_git(["worktree", "add", "-b", branch_name, str(target_dir), base_ref])
        if add_res.returncode != 0 and "already exists" not in add_res.stderr:
            # Fallback если ветка уже существует
            add_res = self._run_git(["worktree", "add", str(target_dir), branch_name])
            if add_res.returncode != 0:
                raise RuntimeError(f"Ошибка создания git worktree: {add_res.stderr.strip()}")

        # Фиксируем инварианты Git внутри созданной песочницы
        configs = [
            ("core.autocrlf", "false"),
            ("core.eol", "lf"),
            ("core.quotepath", "false"),
        ]
        for key, val in configs:
            self._run_git(["config", "--local", key, val], cwd=target_dir)

        payload = {
            "status": "CREATED",
            "task_id": clean_task_id,
            "branch": branch_name,
            "path": str(target_dir.relative_to(self.workspace_root)).replace("\\", "/"),
            "absolute_path": str(target_dir),
            "git_invariants": {k: v for k, v in configs},
        }

        logger.info(f"Песочница создана: {payload['path']} (ветка: {branch_name})")
        return payload

    def list_sandboxes(self) -> List[Dict[str, Any]]:
        """Получение списка всех активных git worktrees."""
        res = self._run_git(["worktree", "list", "--porcelain"])
        sandboxes: List[Dict[str, Any]] = []
        if res.returncode == 0:
            current: Dict[str, str] = {}
            for line in res.stdout.splitlines():
                if not line.strip():
                    if current:
                        sandboxes.append(dict(current))
                        current = {}
                    continue
                parts = line.split(" ", 1)
                key = parts[0]
                val = parts[1] if len(parts) > 1 else ""
                current[key] = val
            if current:
                sandboxes.append(dict(current))
        return sandboxes

    def prune_all(self) -> int:
        """Очистка всех неиспользуемых рабочих деревьев."""
        return self.lifecycle_manager.cleanup_all(self.workspace_root)

    def remove_sandbox(self, task_id: str, force: bool = True) -> Dict[str, Any]:
        """Удаление изолированного worktree и сопутствующей ветки."""
        clean_task_id = "".join(c for c in task_id if c.isalnum() or c in ("-", "_")).strip()
        target_dir = self.worktrees_base / clean_task_id
        branch_name = f"sandbox/{clean_task_id}"

        # Удаление через git worktree remove
        cmd = ["worktree", "remove"]
        if force:
            cmd.append("--force")
        cmd.append(str(target_dir))
        self._run_git(cmd)

        # Очистка директории если осталась
        if target_dir.exists():
            shutil.rmtree(target_dir, ignore_errors=True)

        # Prune
        self._run_git(["worktree", "prune"])

        # Удаление временной ветки
        self._run_git(["branch", "-D", branch_name])

        logger.info(f"Песочница {clean_task_id} удалена.")
        return {"status": "REMOVED", "task_id": clean_task_id}


def main() -> int:
    parser = argparse.ArgumentParser(description="Git Worktree Sandbox Manager for Self-Evo Subagents")
    parser.add_argument("--create", type=str, help="Создать песочницу с указанным task_id")
    parser.add_argument("--remove", type=str, help="Удалить песочницу с указанным task_id")
    parser.add_argument("--list", action="store_true", help="Список активных песочниц")
    parser.add_argument("--prune-all", action="store_true", help="Очистить все неиспользуемые песочницы")
    parser.add_argument("--base-ref", default="HEAD", help="Базовая ревизия для создания ветки")

    args = parser.parse_args()
    manager = WorktreeSandboxManager()

    if args.create:
        res = manager.create_sandbox(task_id=args.create, base_ref=args.base_ref)
        print(json.dumps(res, indent=2, ensure_ascii=False))
        return 0

    if args.remove:
        res = manager.remove_sandbox(task_id=args.remove)
        print(json.dumps(res, indent=2, ensure_ascii=False))
        return 0

    if args.prune_all:
        count = manager.prune_all()
        print(f"Очищено песочниц: {count}")
        return 0

    if args.list:
        sandboxes = manager.list_sandboxes()
        print(json.dumps(sandboxes, indent=2, ensure_ascii=False))
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
