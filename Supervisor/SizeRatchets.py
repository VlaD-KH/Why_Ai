#!/usr/bin/env python3
"""
Модуль: Supervisor/SizeRatchets.py
Назначение: Механизм аппаратных храповиков размера (Size Ratchets) по принципу shrink-only.
Архитектурный слой: Supervisor (Зона P/R - Immutable Core).
Инвариант: Оптимизация кодовой базы навсегда фиксирует новый нижний лимит объема файла.
"""

import argparse
import datetime
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

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
        self._registry_rel = str(RATCHET_REGISTRY).replace("\\", "/")
        data = self._load_registry()
        self.limits: Dict[str, int] = data.get("limits", {})
        self.rebaselines: List[Dict[str, Any]] = data.get("rebaselines", [])

    @staticmethod
    def _normalize(rel_path: str) -> str:
        """Нормализация пути. НЕ `lstrip('./')`: то была посимвольная зачистка
        набора символов, из-за которой '.github/x.yml' превращался в
        'github/x.yml' — ведущая точка воспринималась как мусор наравне со
        слешем. Здесь снимается только буквальный префикс './', один раз."""
        p = rel_path.replace("\\", "/")
        if p.startswith("./"):
            p = p[2:]
        return p

    def _load_registry(self) -> Dict[str, Any]:
        if self.registry_file.exists():
            try:
                return json.loads(self.registry_file.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning(f"Ошибка загрузки реестра храповиков: {e}")
        return {}

    def _save_limits(self) -> None:
        """Сохранение реестра храповиков."""
        payload = {
            "schema": "ai-loop/size-ratchets/v1",
            "principle": "shrink-only",
            "limits": self.limits,
            "rebaselines": self.rebaselines,
        }
        self.registry_file.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    def record_baseline(self) -> Dict[str, int]:
        """Фиксация текущих размеров всех файлов кодовой базы как базовых лимитов."""
        scanned = 0
        for root, dirs, files in os.walk(self.workspace_root):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("venv", "node_modules", "__pycache__", "worktrees")]
            for file in files:
                ext = os.path.splitext(file)[1].lower()
                if ext not in (".py", ".ts", ".tsx", ".js", ".jsx", ".md", ".json", ".yaml", ".sh"):
                    continue
                full_path = Path(root) / file
                rel_path = str(full_path.relative_to(self.workspace_root)).replace("\\", "/")
                if rel_path == self._registry_rel:
                    # Реестр не может быть собственным храповиком: каждая
                    # запись в него меняла бы его же размер и раздувала бы
                    # сама себя на следующем проходе.
                    continue
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

    def check_file(self, rel_path: str, max_allowed_growth_ratio: float = 0.15, persist: bool = True) -> bool:
        """
        Проверка файла на превышение установленного храповика.
        Возвращает True, если размер в пределах нормы, False при раздувании (bloat).

        persist=False — режим гейта: только чтение, реестр на диске не
        меняется. Без этого CommitGate, проверяя дифф, попутно переписывал бы
        файл, который сам же охраняет.
        """
        norm_path = self._normalize(rel_path)
        full_path = self.workspace_root / norm_path

        if not full_path.exists():
            return True

        current_size = full_path.stat().st_size
        recorded_limit = self.limits.get(norm_path)

        if recorded_limit is None:
            # Новый файл - регистрируем его текущий размер
            if persist:
                self.limits[norm_path] = current_size
                self._save_limits()
            return True

        # Если файл уменьшился - фиксируем новый нижний лимит (shrink-only)
        if current_size < recorded_limit:
            if persist:
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

    def check_paths(self, paths: List[str], max_allowed_growth_ratio: float = 0.15, persist: bool = False) -> Dict[str, Any]:
        """Проверка списка путей (диффа) одним вызовом — контракт для CommitGate.

        Возвращает структурный список нарушителей, а не один булев флаг: гейт
        обязан показать оператору, что именно раздулось и насколько, а не
        просто отказать. По умолчанию persist=False — это и есть гейт-режим.
        """
        violations: List[Dict[str, Any]] = []
        for rel_path in paths:
            norm_path = self._normalize(rel_path)
            full_path = self.workspace_root / norm_path
            if not full_path.exists():
                continue
            current_size = full_path.stat().st_size
            recorded_limit = self.limits.get(norm_path)
            ok = self.check_file(rel_path, max_allowed_growth_ratio=max_allowed_growth_ratio, persist=persist)
            if not ok:
                ceiling = int(recorded_limit * (1.0 + max_allowed_growth_ratio))
                violations.append({
                    "path": norm_path,
                    "recorded_limit": recorded_limit,
                    "ceiling": ceiling,
                    "current_size": current_size,
                })
        return {"ok": not violations, "violations": violations, "checked": [self._normalize(p) for p in paths]}

    def rebaseline(self, rel_path: str, reason: str) -> Dict[str, Any]:
        """Явная, осознанная переустановка базы — единственный законный способ
        поднять лимит. Причина обязательна и остаётся в реестре как аудит-
        запись: рост объёма без объяснения — то самое раздувание, от которого
        Принцип 10 защищает."""
        reason = (reason or "").strip()
        if not reason:
            raise ValueError("rebaseline требует непустую причину — это аудит-запись, а не побочный эффект")

        norm_path = self._normalize(rel_path)
        full_path = self.workspace_root / norm_path
        current_size = full_path.stat().st_size if full_path.exists() else 0
        old_limit = self.limits.get(norm_path)

        self.limits[norm_path] = current_size
        record = {
            "path": norm_path,
            "old_limit": old_limit,
            "new_limit": current_size,
            "reason": reason,
            "at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        self.rebaselines.append(record)
        self._save_limits()
        logger.warning(f"[REBASELINE] {norm_path}: {old_limit} -> {current_size} B. Причина: {reason}")
        return record


def main() -> int:
    parser = argparse.ArgumentParser(description="Size Ratchets Shrink-Only Enforcer")
    parser.add_argument("--record-baseline", action="store_true", help="Зафиксировать базовые размеры файлов")
    parser.add_argument("--check-file", type=str, help="Проверить конкретный файл на раздувание")
    parser.add_argument("--status", action="store_true", help="Показать текущий реестр храповиков")
    parser.add_argument("--rebaseline", type=str, help="Явно переустановить базу для файла (требует --reason)")
    parser.add_argument("--reason", type=str, default="", help="Причина переустановки базы (обязательна с --rebaseline)")

    args = parser.parse_args()
    manager = SizeRatchetsManager()

    if args.rebaseline:
        try:
            rec = manager.rebaseline(args.rebaseline, args.reason)
        except ValueError as e:
            print(json.dumps({"ok": False, "error": str(e)}, indent=2, ensure_ascii=False))
            return 10
        print(json.dumps({"ok": True, **rec}, indent=2, ensure_ascii=False))
        return 0

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
