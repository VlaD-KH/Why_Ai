#!/usr/bin/env python3
"""
Хелпер: tests/_git_workspace.py
Назначение: одноразовая git-рабочая область для герметичных тестов.

Не начинается с `test_`, поэтому не подхватывается discovery.

Зачем: и цикл самоэволюции, и снимок роя работают с НАСТОЯЩИМ git-репозиторием
(`git worktree add`). Проверять их против реального репозитория проекта нельзя:
тест начал бы создавать ветки `sandbox/*` и переписывать `.size_ratchets.json`,
находящийся под версионным контролем. Одноразовый репозиторий во временном
каталоге снимает оба риска и делает результат детерминированным.
"""

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

GIT_IDENTITY = [
    "-c", "user.name=why-ai-fixture",
    "-c", "user.email=fixture@example.invalid",
]


def init_git_repo(root: Path) -> None:
    """Инициализация репозитория с одним коммитом (нужен HEAD для worktree add)."""
    subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
    (root / "README.md").write_text("git workspace fixture\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(root), *GIT_IDENTITY, "commit", "-q", "-m", "fixture baseline"],
        check=True, capture_output=True,
    )


def write_config(root: Path, *, active_mode: str = "prod_evo", background_enabled: bool = False,
                 swarm_enabled: bool = True) -> Path:
    """Минимальный why_ai_config.yaml той же формы, что и продакшен-манифест."""
    conf = root / "why_ai_config.yaml"
    conf.write_text(
        "system:\n"
        '  project_name: "Why_Ai"\n'
        f'  active_mode: "{active_mode}"\n'
        "\n"
        "modules:\n"
        "  background_consciousness:\n"
        f"    enabled: {'true' if background_enabled else 'false'}\n"
        "    tick_interval_seconds: 300\n"
        "    idempotency_gate:\n"
        "      enabled: true\n"
        "      require_failure_binding: true\n"
        "      shrink_only_ratchet: true\n"
        "\n"
        "  swarm_visualizer:\n"
        f"    enabled: {'true' if swarm_enabled else 'false'}\n"
        '    stream_protocol: "SSE"\n'
        '    endpoint: "/api/events/stream"\n'
        "    refresh_rate_ms: 1000\n",
        encoding="utf-8",
    )
    return conf


def write_state(root: Path, current_mode: str, *, project_name: str = "fixture-project",
                topology_mode: str = None) -> Path:
    """Файл рантайм-состояния в той же форме, что пишет WorkspaceOrchestrator."""
    import json
    if topology_mode is None:
        topology_mode = "AGENT_MODE_SELF_EVO" if current_mode == "agent" else "PROJECT_MODE_PROD_EVO"
    payload = {
        "current_mode": current_mode,
        "project_name": project_name,
        "topology": {
            "mode": topology_mode,
            "hierarchy": "Agent ⊃ Project" if current_mode == "agent" else "Project ⊃ agent",
            "rank_map": {"workspace_root": 0},
            "operative_goal": f"fixture goal for {current_mode}",
        },
    }
    state = root / ".ai_workspace_state.json"
    state.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return state


class TempWorkspaceMixin(unittest.TestCase):
    """Создаёт временный каталог и убирает его после теста."""

    def make_workspace(self, *, git: bool = False) -> Path:
        root = Path(tempfile.mkdtemp(prefix="why-ai-test-")).resolve()
        # ignore_errors: на Windows .git содержит файлы только для чтения,
        # и падение уборки не должно маскировать результат самого теста.
        self.addCleanup(shutil.rmtree, root, True)
        if git:
            init_git_repo(root)
        return root
