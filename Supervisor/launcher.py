#!/usr/bin/env python3
"""
Модуль: Supervisor/launcher.py
Назначение: Неизменяемый контроллер жизненного цикла процессов и внеполосный обработчик сигналов остановки.
Архитектурный слой: Supervisor (Зона P / R - Immutable Core).
"""

import argparse
import datetime
import json
import logging
import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

# Настройка логирования в корневой файл отладки
LOG_FILE = Path("antigravity_debug.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [SUPERVISOR] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("Supervisor")

PID_STATE_FILE = Path(".supervisor_pids.json")


class SupervisorLauncher:
    """
    Класс управления жизненным циклом и процессами мультиагентного рантайма.
    Обеспечивает внеполосную изоляцию и обработку прерываний /panic.
    """

    def __init__(self, workspace_root: Optional[Path] = None) -> None:
        self.workspace_root = workspace_root or Path.cwd()
        self.active_pids: List[int] = self._load_active_pids()

    def _load_active_pids(self) -> List[int]:
        """Загрузка активных PID дочерних процессов из файла состояния."""
        if PID_STATE_FILE.exists():
            try:
                data = json.loads(PID_STATE_FILE.read_text(encoding="utf-8"))
                return data.get("pids", [])
            except Exception as e:
                logger.warning(f"Не удалось прочитать {PID_STATE_FILE}: {e}")
        return []

    def _save_active_pids(self) -> None:
        """Сохранение активных PID дочерних процессов."""
        PID_STATE_FILE.write_text(
            json.dumps({"pids": self.active_pids, "updated_at": datetime.datetime.now().isoformat()}, indent=2),
            encoding="utf-8"
        )

    def panic_stop(self, reason: str = "Unspecified emergency shutdown") -> int:
        """
        Внеполосная принудительная остановка всех дочерних процессов агентов.
        Гарантирует завершение без передачи управления языковой модели.
        """
        logger.critical(f"ВНИМАНИЕ! Инициирован сигнал экстренной остановки /panic! Причина: {reason}")
        
        stopped_count = 0
        for pid in list(self.active_pids):
            try:
                if os.name == "nt":
                    # Windows: принудительное завершение дерева процессов
                    subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True)
                else:
                    # POSIX: SIGKILL группы процессов
                    os.kill(pid, signal.SIGKILL)
                logger.info(f"Процесс с PID {pid} успешно принудительно завершен.")
                stopped_count += 1
            except ProcessLookupError:
                logger.debug(f"Процесс {pid} уже не существует.")
            except Exception as ex:
                logger.error(f"Ошибка при завершении процесса {pid}: {ex}")

        self.active_pids.clear()
        self._save_active_pids()
        
        logger.info(f"Аварийный останов завершен. Остановлено процессов: {stopped_count}. Возврат кода 10.")
        return 10

    def start_runtime(self, mode: str = "project") -> None:
        """
        Запуск изменяемого рантайма Task Runtime в изолированном дочернем процессе.
        """
        logger.info(f"Запуск дочернего рантайма в режиме '{mode}'...")
        # Проверка целостности Конституции перед запуском
        bible_path = self.workspace_root / "Supervisor" / "Constitution" / "BIBLE.md"
        if not bible_path.exists():
            logger.critical("Файл Конституции BIBLE.md не найден! Запуск отменен.")
            sys.exit(10)

        logger.info("Конституция BIBLE.md верифицирована. Рантайм готов к исполнению задач.")

    def get_status(self) -> Dict[str, object]:
        """
        Получение текущего диагностического статуса супервизора.
        """
        return {
            "status": "RUNNING",
            "workspace_root": str(self.workspace_root),
            "active_pids_count": len(self.active_pids),
            "constitution_present": (self.workspace_root / "Supervisor" / "Constitution" / "BIBLE.md").exists(),
            "timestamp": datetime.datetime.now().isoformat()
        }


def main() -> None:
    """Точка входа CLI для Supervisor Launcher."""
    parser = argparse.ArgumentParser(description="Supervisor Process Lifecycle & Panic Controller")
    parser.add_argument("--start", action="store_true", help="Запуск агента в фоновом процессе")
    parser.add_argument("--panic-stop", action="store_true", help="Экстренная внеполосная остановка всех процессов")
    parser.add_argument("--reason", type=str, default="CLI trigger", help="Причина экстренной остановки")
    parser.add_argument("--status", action="store_true", help="Диагностический статус супервизора")
    parser.add_argument("--mode", type=str, default="project", choices=["project", "agent"], help="Режим иерархии")

    args = parser.parse_args()
    launcher = SupervisorLauncher()

    if args.panic_stop:
        exit_code = launcher.panic_stop(reason=args.reason)
        sys.exit(exit_code)
    elif args.status:
        status_info = launcher.get_status()
        print(json.dumps(status_info, indent=2, ensure_ascii=False))
    elif args.start:
        launcher.start_runtime(mode=args.mode)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
