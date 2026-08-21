#!/usr/bin/env python3
"""
Модуль: Supervisor/SizeRatchets.py
Назначение: Механизм аппаратных храповиков размера (Size Ratchets) по принципу shrink-only.
Архитектурный слой: Supervisor (Зона P/R - Immutable Core).
Инвариант: Оптимизация кодовой базы навсегда фиксирует новый нижний лимит объема файла.
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Dict, Any, Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] [RATCHETS] %(message)s")
logger = logging.getLogger("SizeRatchets")

RATCHET_REGISTRY = Path(".size_ratchets.json")


class SizeRatchetsManager:
    """
    Менеджер контроля раздувания кодовой базы (Code Bloat Prevention).
    """

    def __init__(self, workspace_root: Optional[Path] = None) -> None:
        self.workspace_root = (workspace_root or Path.cwd()).resolve()
        self.registry_file = self.workspace_root / RATCHET_REGISTRY
        self.limits: Dict[str, int] = self._load_limits()

    def _load_limits(self) -> Dict[str, int]:
        """Загрузка зарегистрированных верхних лимитов файлов."""
        if self.registry_file.exists():
            try:
                data = json.loads(self.registry_file.read_text(encoding="utf-8"))
                return data.get("limits", {})
            except Exception as e:
                logger.warning(f"Ошибка загрузки реестра храповиков: {e}")
        return {}

    def _save_limits(self) -> None:
        """Сохранение реестра храповиков."""
        payload = {
            "schema": "ai-loop/size-ratchets/v1",
            "principle": "shrink-only",
            "limits": self.limits,
        }
        self.registry_file.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    def record_baseline(self) -> Dict[str, int]:
        """Фиксация текущих размеров всех файлов кодовой базы как базовых лимитов."""
        scanned = 0
        for root, dirs, files in os.walk(self.workspace_root):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("venv", "node_modules", "__pycache__", "worktrees")]
            for file in files:
                ext = os.path.splitext(file)[1].lower()
                if ext in (".py", ".ts", ".tsx", ".js", ".jsx", ".md", ".json", ".yaml", ".sh"):
                    full_path = Path(root) / file
                    rel_path = str(full_path.relative_to(self.workspace_root)).replace("\\", "/")
                    size = full_path.stat().st_size
                    # Если файл уже в реестре, обновляем только если размер уменьшился (shrink-only)
                    if rel_path in self.limits:
                        if size < self.limits[rel_path]:
                            logger.info(f"Храповик понижен для {rel_path}: {self.limits[rel_path]} -> {size} байт")
                            self.limits[rel_path] = size
                    else:
                        self.limits[rel_path] = size
                    scanned += 1

        self._save_limits()
        logger.info(f"Базовые храповики зафиксированы для {scanned} файлов.")
        return self.limits

    def check_file(self, rel_path: str, max_allowed_growth_ratio: float = 0.15) -> bool:
        """
        Проверка файла на превышение установленного храповика.
        Возвращает True, если размер в пределах нормы, False при раздувании (bloat).
        """
        norm_path = rel_path.replace("\\", "/").lstrip("./")
        full_path = self.workspace_root / norm_path

        if not full_path.exists():
            return True

        current_size = full_path.stat().st_size
        recorded_limit = self.limits.get(norm_path)

        if recorded_limit is None:
            # Новый файл - регистрируем его текущий размер
            self.limits[norm_path] = current_size
            self._save_limits()
            return True

        # Если файл уменьшился - фиксируем новый нижний лимит (shrink-only)
        if current_size < recorded_limit:
            logger.info(f"[SHRINK] Размер {norm_path} уменьшился ({recorded_limit} -> {current_size} B). Храповик обновлен.")
            self.limits[norm_path] = current_size
            self._save_limits()
            return True

        # Проверка допустимого порога
        ceiling = int(recorded_limit * (1.0 + max_allowed_growth_ratio))
        if current_size > ceiling:
            logger.error(f"[BLOAT-VIOLATION] Файл {norm_path} превысил лимит храповика! Текущий: {current_size} B, Лимит: {recorded_limit} B (Ceiling: {ceiling} B)")
            return False

        return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Size Ratchets Shrink-Only Enforcer")
    parser.add_argument("--record-baseline", action="store_true", help="Зафиксировать базовые размеры файлов")
    parser.add_argument("--check-file", type=str, help="Проверить конкретный файл на раздувание")
    parser.add_argument("--status", action="store_true", help="Показать текущий реестр храповиков")

    args = parser.parse_args()
    manager = SizeRatchetsManager()

    if args.record_baseline:
        limits = manager.record_baseline()
        print(json.dumps({"status": "recorded", "files_count": len(limits)}, indent=2))
        return 0

    if args.check_file:
        ok = manager.check_file(args.check_file)
        if not ok:
            print(json.dumps({"ok": False, "file": args.check_file, "error": "Size ratchet ceiling exceeded"}, indent=2))
            return 10
        print(json.dumps({"ok": True, "file": args.check_file}, indent=2))
        return 0

    if args.status:
        print(json.dumps(manager.limits, indent=2, ensure_ascii=False))
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
