#!/usr/bin/env python3
"""
Модуль: Why_Ai/Core/server.py
Назначение: Фоновая служба Daemon API (Control Plane) на 127.0.0.1:8765 со стримингом SSE, деревом роя (Swarm Task-Tree) и REST управлением.
Архитектурный слой: Core / Control Plane (Зона E - Mutable Service).
Инвариант: Предоставляет легковесный HTTP/SSE интерфейс для телеметрии, дерева роя субагентов, манифеста идентичности и внеполосного /panic.
"""

import argparse
import datetime
import hmac
import http.server
import json
import logging
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Dict, Any, List, Optional

# Добавление путей к Supervisor и Core
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "Supervisor"))
sys.path.insert(0, str(ROOT_DIR / "Core"))

try:
    from launcher import SupervisorLauncher
    from EvolutionDaemon import AutonomousEvolutionDaemon
    from WorktreeSandbox import WorktreeSandboxManager
    from WorkspaceOrchestrator import WorkspaceOrchestrator
    from miniyaml import parse_yaml
except ImportError:
    from Supervisor.launcher import SupervisorLauncher  # type: ignore
    from Supervisor.EvolutionDaemon import AutonomousEvolutionDaemon  # type: ignore
    from Supervisor.WorktreeSandbox import WorktreeSandboxManager  # type: ignore
    from Supervisor.WorkspaceOrchestrator import WorkspaceOrchestrator  # type: ignore
    from Supervisor.miniyaml import parse_yaml  # type: ignore

try:
    from Tool.connectors.dvpn_connector import DVPNConnector
    global_dvpn_connector = DVPNConnector()
except Exception:
    global_dvpn_connector = None

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] [DAEMON-API] %(message)s")
logger = logging.getLogger("DaemonAPI")

# Очередь глобальных событий для SSE стриминга
EVENT_SUBSCRIBERS: List[queue.Queue] = []
SUBSCRIBERS_LOCK = threading.Lock()


def broadcast_event(event_type: str, data: Dict[str, Any]) -> None:
    """Отправка события всем активным SSE подписчикам."""
    payload = {
        "type": event_type,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "data": data,
    }
    msg = f"event: {event_type}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
    with SUBSCRIBERS_LOCK:
        for q in list(EVENT_SUBSCRIBERS):
            try:
                q.put_nowait(msg)
            except Exception:
                EVENT_SUBSCRIBERS.remove(q)


# ENV-имя общего секрета для внеполосного /panic. Значение никогда не логируется
# и не попадает в ответ — наружу уходит только факт совпадения/несовпадения.
PANIC_TOKEN_ENV = "WHY_AI_PANIC_TOKEN"


def count_declared_tests() -> str:
    """Фактическое число тестовых методов в tests/, посчитанное по исходникам.

    Раньше здесь стоял литерал "32/32 PASS" при 160+ реальных тестах — то есть
    статус-панель уверенно называла неверное число (CLAUDE.md, правило 2).
    Считаем объявления `def test_*` вместо прогона набора: /api/status обязан
    отвечать мгновенно, а полный прогон занимает ~13 секунд. Это честно
    описывает, что именно измерено — «объявлено», а не «прошло»: за фактический
    результат отвечает отдельный маршрут /api/tests, который реально запускает
    unittest.
    """
    tests_dir = ROOT_DIR / "tests"
    if not tests_dir.is_dir():
        return "0 tests discovered"
    total = 0
    for path in sorted(tests_dir.glob("test_*.py")):
        try:
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.lstrip().startswith("def test"):
                    total += 1
        except OSError:
            continue
    return f"{total} tests declared"


def count_bible_principles() -> str:
    """Фактическое число принципов в BIBLE.md, посчитанное по заголовкам.

    Раньше — литерал "13/13 BIBLE.md", хотя принципов 15 (14 и 15 ратифицированы
    2026-08-21). EvolutionDaemon уже рапортует 15/15, сервер отставал.
    """
    bible = ROOT_DIR / "Supervisor" / "Constitution" / "BIBLE.md"
    if not bible.is_file():
        return "BIBLE.md missing"
    try:
        text = bible.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "BIBLE.md unreadable"
    count = sum(1 for line in text.splitlines() if line.lstrip().startswith("### Принцип "))
    return f"{count}/{count} BIBLE.md"


class ControlApiHandler(http.server.BaseHTTPRequestHandler):
    """
    HTTP & SSE Обработчик для Daemon Control Plane.
    """

    def _send_json(self, status_code: int, data: Dict[str, Any]) -> None:
        body = json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Why-Ai-Panic-Token")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Why-Ai-Panic-Token")
        self.end_headers()

    def do_GET(self) -> None:
        # 1. Корневой статический файл dashboard.html (канонический путь: Eye/)
        if self.path in ("/", "/dashboard", "/dashboard.html"):
            dash_path = ROOT_DIR / "Eye" / "dashboard.html"
            if not dash_path.exists():
                dash_path = ROOT_DIR / "dashboard.html"
            if dash_path.exists():
                content = dash_path.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
                return

        # 2. REST: Статус системы
        if self.path == "/api/status":
            launcher = SupervisorLauncher(workspace_root=ROOT_DIR)
            status_data = {
                "daemon": "Why_Ai Sovereign Control Plane API",
                "version": "1.1.0-gold",
                "status": "RUNNING",
                "host": "127.0.0.1",
                "port": 8765,
                "workspace_root": str(ROOT_DIR),
                "supervisor": launcher.get_status(),
                "verified_tests": count_declared_tests(),
                "active_invariants": count_bible_principles(),
                "model_capability_grading": "Class 1/2/3 Active",
                "time": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            }
            self._send_json(200, status_data)
            return

        # 3. REST: Дерево роя субагентов (Swarm Task-Tree) — из реальных worktree-песочниц,
        # не из литерала. См. docs/final_vision/03-roadmap.md, пункт 5.1.2.
        if self.path == "/api/swarm/tasks":
            manager = WorktreeSandboxManager(workspace_root=ROOT_DIR)
            worktree_entries = manager.list_sandboxes()
            # Песочницей считается только то, что реально лежит под ROOT_DIR/worktrees/ —
            # именно туда WorktreeSandboxManager.create_sandbox() кладёт свои worktree.
            # Сравнение "путь != ROOT_DIR" здесь недостаточно: если сам демон запущен
            # из связанного worktree (а не из главного чекаута), список git worktree
            # содержит и главный чекаут репозитория — он не является песочницей.
            sandboxes_base = (ROOT_DIR / "worktrees").resolve()

            subagents: List[Dict[str, Any]] = []
            for entry in worktree_entries:
                wt_path_raw = entry.get("worktree", "")
                if not wt_path_raw:
                    continue
                wt_path = Path(wt_path_raw).resolve()
                try:
                    rel_path = wt_path.relative_to(sandboxes_base)
                except ValueError:
                    continue  # не под worktrees/ этой рабочей области — не песочница
                branch_ref = entry.get("branch", "")
                subagents.append({
                    "id": wt_path.name,
                    "role": "Active Sandbox Worktree",
                    "status": "DETACHED" if "detached" in entry else "RUNNING",
                    "worktree": ("worktrees/" + str(rel_path)).replace("\\", "/"),
                    "branch": branch_ref.replace("refs/heads/", "") if branch_ref else None,
                    "head": entry.get("HEAD", "")[:12],
                })

            orch = WorkspaceOrchestrator(workspace_root=ROOT_DIR)
            active_mode = orch.resolve_active_mode()["mode"]

            swarm_data = {
                "swarm_state": "ACTIVE" if subagents else "IDLE",
                "root_orchestrator": {
                    "id": "agent-root",
                    "role": "Global Sovereign Orchestrator (Rank 1)",
                    "status": "RUNNING",
                    "mode": active_mode,
                    "current_directive": "Continuous Core Refactoring & Quorum Supervision",
                },
                "subagents": subagents,
                "active_sandboxes_count": len(subagents),
                "lifecycle_clean": True,
            }
            self._send_json(200, swarm_data)
            return

        # 4. REST: Манифест идентичности (Living Identity & Scratchpad)
        if self.path == "/api/identity":
            id_file = ROOT_DIR / "Core" / "identity.md"
            sp_file = ROOT_DIR / "Core" / "scratchpad.md"
            self._send_json(200, {
                "identity_present": id_file.exists(),
                "identity_pinned": True,
                "identity_content": id_file.read_text(encoding="utf-8") if id_file.exists() else "",
                "scratchpad_present": sp_file.exists(),
                "scratchpad_content": sp_file.read_text(encoding="utf-8") if sp_file.exists() else "",
            })
            return

        # 5. REST: Конфигурация (why_ai_config.yaml)
        if self.path == "/api/config":
            conf_file = ROOT_DIR / "why_ai_config.yaml"
            if conf_file.exists():
                try:
                    conf = parse_yaml(conf_file.read_text(encoding="utf-8"))
                    self._send_json(200, conf)
                    return
                except Exception as e:
                    self._send_json(500, {"error": f"Failed to parse config: {e}"})
                    return
            self._send_json(404, {"error": "why_ai_config.yaml not found"})
            return

        # 6. REST: dVPN Router Status
        if self.path == "/api/dvpn/status":
            if global_dvpn_connector:
                self._send_json(200, global_dvpn_connector.get_status())
            else:
                self._send_json(200, {"status": "DISCONNECTED", "total_available_nodes": 0})
            return

        # 7. REST: dVPN Nodes List
        if self.path.startswith("/api/dvpn/nodes"):
            if global_dvpn_connector:
                self._send_json(200, {"nodes": global_dvpn_connector.list_nodes()})
            else:
                self._send_json(200, {"nodes": []})
            return

        # 8. REST: Запуск юнит-тестов
        if self.path == "/api/tests":
            cmd = [sys.executable, "-m", "unittest", "discover", "-s", str(ROOT_DIR / "tests"), "-p", "test_*.py"]
            env = os.environ.copy()
            env["PYTHONUTF8"] = "1"
            res = subprocess.run(cmd, cwd=str(ROOT_DIR), capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
            self._send_json(200, {
                "status": "PASSED" if res.returncode == 0 else "FAILED",
                "returncode": res.returncode,
                "stdout": res.stdout,
                "stderr": res.stderr,
            })
            return

        # 7. SSE: Стрим событий в реальном времени
        if self.path == "/api/events/stream":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()

            client_queue: queue.Queue = queue.Queue()
            with SUBSCRIBERS_LOCK:
                EVENT_SUBSCRIBERS.append(client_queue)

            initial_msg = f"event: connected\ndata: {json.dumps({'message': 'Connected to Why_Ai Telemetry & Swarm Stream', 'time': time.time()})}\n\n"
            self.wfile.write(initial_msg.encode("utf-8"))
            self.wfile.flush()

            try:
                while True:
                    try:
                        msg = client_queue.get(timeout=1.0)
                        self.wfile.write(msg.encode("utf-8"))
                        self.wfile.flush()
                    except queue.Empty:
                        self.wfile.write(b": ping\n\n")
                        self.wfile.flush()
            except (ConnectionResetError, BrokenPipeError):
                pass
            finally:
                with SUBSCRIBERS_LOCK:
                    if client_queue in EVENT_SUBSCRIBERS:
                        EVENT_SUBSCRIBERS.remove(client_queue)
            return

        self._send_json(404, {"error": "Not Found", "path": self.path})

    def _panic_authorized(self) -> bool:
        """Fail-closed проверка общего секрета для /panic.

        До этой правки маршрут не имел аутентификации вообще при
        `Access-Control-Allow-Origin: *` — то есть любая открытая в браузере
        оператора страница могла отправить POST и убить всё дерево процессов
        (launcher.panic_stop → taskkill /F /T). Секрет читается из ENV
        (Принцип 14 — ноль учётных данных в репозитории) и сравнивается
        constant-time.

        Fail-closed означает буквально: если секрет не задан в окружении,
        маршрут закрыт, а не открыт. Незаданный ENV — это не «проверка
        отключена», это «войти нельзя».
        """
        expected = (os.getenv(PANIC_TOKEN_ENV) or "").strip()
        if not expected:
            return False
        provided = (self.headers.get("X-Why-Ai-Panic-Token") or "").strip()
        if not provided:
            return False
        return hmac.compare_digest(provided, expected)

    def do_POST(self) -> None:
        # 1. Экстренный останов /panic — только с валидным общим секретом.
        if self.path == "/api/panic":
            if not self._panic_authorized():
                # Причина отказа намеренно не детализируется (не задан ENV
                # против неверного токена) — это подсказка атакующему.
                logger.warning("[PANIC] Отклонён неавторизованный запрос на внеполосный останов.")
                self._send_json(401, {
                    "status": "UNAUTHORIZED",
                    "error": f"POST /api/panic требует заголовок X-Why-Ai-Panic-Token, совпадающий с ${PANIC_TOKEN_ENV}",
                })
                return
            launcher = SupervisorLauncher(workspace_root=ROOT_DIR)
            code = launcher.panic_stop(reason="Remote /panic triggered via Control Plane API")
            broadcast_event("panic_stop", {"reason": "Remote API trigger", "exit_code": code})
            self._send_json(200, {"status": "PANIC_STOPPED", "exit_code": code})
            return

        # 2. Очистка песочниц (Worktree Lifecycle Manager)
        if self.path == "/api/worktrees/prune":
            sb = WorktreeSandboxManager(workspace_root=ROOT_DIR)
            count = sb.prune_all()
            broadcast_event("worktrees_pruned", {"pruned_count": count})
            self._send_json(200, {"status": "PRUNED", "pruned_count": count})
            return

        # 3. Запуск цикла самоэволюции
        if self.path == "/api/evolve":
            daemon = AutonomousEvolutionDaemon(workspace_root=ROOT_DIR)
            res = daemon.run_evolution_cycle(task_name="api-triggered-evo")
            broadcast_event("evolution_cycle", res)
            self._send_json(200, res)
            return

        # 4. Внеполосное переключение топологического режима [self_evo] <-> [prod_evo]
        if self.path == "/api/mode":
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
                params = json.loads(body) if body else {}
                raw_mode = params.get("mode", "self_evo")
                mode_l = raw_mode.lower()
                orch = WorkspaceOrchestrator(workspace_root=ROOT_DIR)
                if "self" in mode_l or "agent" in mode_l:
                    target_str = "agent"
                elif "prod" in mode_l or "project" in mode_l:
                    target_str = "project"
                else:
                    # Раньше любая нераспознанная строка (опечатка, документированный,
                    # но нереализованный "manual_override") молча резолвилась в
                    # "project". Неизвестный режим отклоняется явно.
                    self._send_json(400, {
                        "error": f"Неизвестный режим '{raw_mode}'. Допустимы значения, "
                                 "содержащие 'self'/'agent' (self_evo) или 'prod'/'project' (prod_evo)."
                    })
                    return
                # project_name не передан клиентом -> сохранить уже сконфигурированное
                # имя проекта, а не сбрасывать на жёсткий дефолт "default_project".
                project_name = params.get("project_name")
                if not project_name:
                    current = orch.get_current_topology()
                    project_name = current.get("project_name") or "default_project"
                res = orch.switch_mode(target_str, project_name=project_name)
                broadcast_event("mode_changed", {"mode": raw_mode, "result": res})
                self._send_json(200, {"status": "MODE_CHANGED", "mode": raw_mode, "result": res})
                return
            except Exception as e:
                self._send_json(500, {"error": f"Ошибка переключения режима: {e}"})
                return

        # 5. Синхронизация failures.jsonl и ledger.jsonl в БД
        if self.path == "/api/sync_db":
            try:
                from Tool.connectors.postgres_connector import PostgresConnector
                pg = PostgresConnector()
                f_res = pg.sync_failures_to_db(str(ROOT_DIR / "Core" / "failures.jsonl"))
                l_res = pg.sync_ledger_to_db(str(ROOT_DIR / "ledger.jsonl"))
                broadcast_event("db_synced", {"failures": f_res, "ledger": l_res})
                self._send_json(200, {"status": "DB_SYNCED", "failures": f_res, "ledger": l_res})
                return
            except Exception as e:
                self._send_json(500, {"error": f"Ошибка синхронизации БД: {e}"})
                return

        # 6. dVPN подключение
        if self.path == "/api/dvpn/connect":
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
                params = json.loads(body) if body else {}
                user_id = params.get("user_id", "default_user")
                tier = params.get("tier", "free")
                country = params.get("country")
                protocol = params.get("protocol")
                if global_dvpn_connector:
                    res = global_dvpn_connector.connect_node(user_id=user_id, tier=tier, country=country, protocol=protocol)
                    broadcast_event("dvpn_connected", res)
                    self._send_json(200, res)
                else:
                    self._send_json(503, {"error": "dVPN connector unavailable"})
                return
            except Exception as e:
                self._send_json(500, {"error": str(e)})
                return

        # 7. dVPN смена тарифного профиля
        if self.path == "/api/dvpn/switch_profile":
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
                params = json.loads(body) if body else {}
                user_id = params.get("user_id", "default_user")
                new_tier = params.get("tier", "premium")
                if global_dvpn_connector:
                    res = global_dvpn_connector.switch_tier_profile(user_id=user_id, new_tier=new_tier)
                    broadcast_event("dvpn_tier_switched", res)
                    self._send_json(200, res)
                else:
                    self._send_json(503, {"error": "dVPN connector unavailable"})
                return
            except Exception as e:
                self._send_json(500, {"error": str(e)})
                return

        # 8. dVPN принудительный Fallback
        if self.path == "/api/dvpn/fallback":
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
                params = json.loads(body) if body else {}
                user_id = params.get("user_id", "default_user")
                reason = params.get("reason", "Manual trigger via API")
                if global_dvpn_connector:
                    res = global_dvpn_connector.trigger_fallback(user_id=user_id, reason=reason)
                    broadcast_event("dvpn_fallback", res)
                    self._send_json(200, res)
                else:
                    self._send_json(503, {"error": "dVPN connector unavailable"})
                return
            except Exception as e:
                self._send_json(500, {"error": str(e)})
                return

        self._send_json(404, {"error": "Not Found", "path": self.path})


def run_daemon_server(host: str = "127.0.0.1", port: int = 8765) -> None:
    """Запуск HTTP & SSE сервера Control Plane."""
    server_address = (host, port)
    httpd = http.server.ThreadingHTTPServer(server_address, ControlApiHandler)
    logger.info(f"Why_Ai Daemon Control Plane запущен на http://{host}:{port}")
    logger.info(f"Дашборд доступен: http://{host}:{port}/dashboard.html")
    logger.info(f"SSE поток событий: http://{host}:{port}/api/events/stream")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("Остановка Daemon Control Plane...")
        httpd.server_close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Why_Ai Daemon Control Plane API Server")
    parser.add_argument("--host", default="127.0.0.1", help="Хост для привязки сервера")
    parser.add_argument("--port", type=int, default=8765, help="Порт для сервера (по умолчанию: 8765)")

    args = parser.parse_args()
    run_daemon_server(host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
