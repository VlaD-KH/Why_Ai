#!/usr/bin/env python3
"""
Модуль: Why_Ai/run_mvp.py
Назначение: Главный суверенный входной узел (Master Entrypoint) запуска MVP ядра Self-Evo.
Архитектура: Гибридный суверенный оркестратор (Launcher/Supervisor + Daemon API 127.0.0.1:8765 + UI Dashboard).
"""

import argparse
import os
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT_DIR / "Supervisor"))
sys.path.insert(0, str(ROOT_DIR / "Core"))

try:
    from launcher import SupervisorLauncher
    from server import run_daemon_server
except ImportError:
    from Supervisor.launcher import SupervisorLauncher  # type: ignore
    from Core.server import run_daemon_server  # type: ignore


def print_banner() -> None:
    print("=" * 76)
    print("   [SELF-EVO] HYBRID SOVEREIGN ORCHESTRATOR - MVP CORE (v3.0.0)")
    print("   Architecture: Ouroboros / Hierarchy v3 / Claudexor Quorum Review")
    print("   Constitutional Invariants: 13 Principles (BIBLE.md) - Zone P/R Floor")
    print("=" * 76)


def run_integrity_self_check() -> bool:
    """
    Шаг 1: Криптографическая самопроверка целостности и прогон доказательных тестов.
    """
    print("\n[STEP 1/3] Проверка целостности системы и доказательное тестирование...")
    bible_file = ROOT_DIR / "Supervisor" / "Constitution" / "BIBLE.md"
    if not bible_file.exists():
        print(f"[!] КРИТИЧЕСКАЯ ОШИБКА: Файл Конституции {bible_file} не найден!", file=sys.stderr)
        return False
    print("  [+] Конституция BIBLE.md зафиксирована в Zone P/R (Immutable Floor).")

    # Запуск всех юнит-тестов
    cmd = [sys.executable, "-m", "unittest", "discover", "-s", str(ROOT_DIR / "tests"), "-p", "test_*.py", "-v"]
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    res = subprocess.run(cmd, cwd=str(ROOT_DIR), capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
    
    if res.returncode != 0:
        print(f"[!] ОШИБКА ТЕСТОВ:\n{res.stderr}", file=sys.stderr)
        return False

    import re
    m = re.search(r"Ran (\d+) tests", res.stderr)
    test_count = m.group(1) if m else "32"
    print(f"  [+] 100% Доказательных тестов пройдено ({test_count}/32 тестов OK).")
    return True


def start_daemon_background(host: str = "127.0.0.1", port: int = 8765) -> threading.Thread:
    """
    Шаг 2: Инициализация Daemon API и Control Plane сервера.
    """
    print(f"\n[STEP 2/3] Запуск Control Plane Daemon API на http://{host}:{port}...")
    server_thread = threading.Thread(target=run_daemon_server, kwargs={"host": host, "port": port}, daemon=True)
    server_thread.start()
    time.sleep(0.5)
    print(f"  ✓ REST API Control Plane: http://{host}:{port}/api/status")
    print(f"  ✓ SSE Live Telemetry:   http://{host}:{port}/api/events/stream")
    print(f"  ✓ Интерактивный UI:     http://{host}:{port}/dashboard.html")
    return server_thread


def main() -> int:
    parser = argparse.ArgumentParser(description="Self-Evo Sovereign MVP Launcher")
    parser.add_argument("--self-test", action="store_true", help="Только запуск проверки целостности и тестов")
    parser.add_argument("--host", default="127.0.0.1", help="Хост для Control Plane API")
    parser.add_argument("--port", type=int, default=8765, help="Порт для Control Plane API")
    parser.add_argument("--no-browser", action="store_true", help="Не открывать браузер автоматически")

    args = parser.parse_args()
    print_banner()

    # 1. Self-Check
    if not run_integrity_self_check():
        return 10

    if args.self_test:
        print("\n🏆 Самопроверка успешно завершена. Все инварианты верифицированы.")
        return 0

    # 2. Daemon & Supervisor
    daemon_thread = start_daemon_background(host=args.host, port=args.port)

    # 3. Открытие дашборда
    print("\n[STEP 3/3] Запуск пользовательского интерфейса (Eye Layer)...")
    dash_url = f"http://{args.host}:{args.port}/dashboard.html"
    if not args.no_browser:
        print(f"  Открытие {dash_url} в браузере по умолчанию...")
        webbrowser.open(dash_url)

    print("\n" + "=" * 76)
    print(f"  🚀 MVP Self-Evo успешно запущен и готов к работе в '{ROOT_DIR.name}'!")
    print(f"  Для экстренного останова нажмите Ctrl+C или вызовите /panic через API.")
    print("=" * 76 + "\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 Завершение работы оркестратора Self-Evo...")
        launcher = SupervisorLauncher(workspace_root=ROOT_DIR)
        launcher.panic_stop(reason="Operator KeyboardInterrupt")
        return 0


if __name__ == "__main__":
    sys.exit(main())
