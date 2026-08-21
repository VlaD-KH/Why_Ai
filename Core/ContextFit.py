#!/usr/bin/env python3
"""
Модуль: Core/ContextFit.py
Назначение: Графовое управление памятью и вычисление центральности узлов (import-graph centrality).
Архитектурный слой: Core (Зона E - Mutable Task Runtime).
Инвариант: Сохранение архитектурных инвариантов при оптимизации и компрессии контекстного окна.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional


class ContextFitManager:
    """
    Менеджер графовой связности кодовой базы и семантической компрессии контекста.
    """

    def __init__(self, repo_path: str = ".") -> None:
        self.repo_path = Path(repo_path).resolve()
        self.graph: Dict[str, Set[str]] = defaultdict(set)
        self.in_degree: Dict[str, int] = defaultdict(int)
        self.file_sizes: Dict[str, int] = {}
        self._build_import_graph()

    def _build_import_graph(self) -> None:
        """Сканирование репозитория и построение графа зависимостей файлов."""
        for root, dirs, files in os.walk(self.repo_path):
            # Пропуск скрытых каталогов и виртуальных окружений
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("venv", "node_modules", "__pycache__", "worktrees")]
            for file in files:
                ext = os.path.splitext(file)[1].lower()
                if ext in (".py", ".ts", ".tsx", ".js", ".jsx", ".md"):
                    full_path = Path(root) / file
                    rel_path = str(full_path.relative_to(self.repo_path)).replace("\\", "/")
                    self.file_sizes[rel_path] = full_path.stat().st_size
                    self._extract_dependencies(full_path, rel_path)

    def _extract_dependencies(self, file_path: Path, rel_path: str) -> None:
        """Извлечение импортов из исходного файла."""
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return

        if file_path.suffix == ".py":
            try:
                tree = ast.parse(content, filename=str(file_path))
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for name in node.names:
                            self._add_edge(rel_path, name.name.replace(".", "/") + ".py")
                    elif isinstance(node, ast.ImportFrom) and node.module:
                        self._add_edge(rel_path, node.module.replace(".", "/") + ".py")
            except SyntaxError:
                pass
        elif file_path.suffix in (".ts", ".tsx", ".js", ".jsx"):
            # Поиск JS/TS import/require
            patterns = [
                r'import\s+.*?\s+from\s+[\'"](.*?)[\'"]',
                r'require\([\'"](.*?)[\'"]\)'
            ]
            for pat in patterns:
                for match in re.findall(pat, content):
                    self._add_edge(rel_path, match)

    def _add_edge(self, source: str, target: str) -> None:
        """Добавление ребра в граф импортов."""
        self.graph[source].add(target)
        self.in_degree[target] += 1

    def compute_centrality(self) -> Dict[str, float]:
        """
        Вычисление нормализованной центральности узлов (Degree & Reachability Centrality).
        Файлы, от которых зависит много других модулей, получают наивысший вес.
        """
        scores: Dict[str, float] = {}
        max_in = max(self.in_degree.values(), default=1) or 1
        
        for file in self.file_sizes:
            in_score = self.in_degree.get(file, 0) / max_in
            out_score = len(self.graph.get(file, set())) * 0.1
            # Базовый вес: связность + наличие в корневых модулях
            score = round((in_score * 0.7) + (out_score * 0.3) + 0.1, 4)
            scores[file] = min(score, 1.0)
            
        return dict(sorted(scores.items(), key=lambda item: item[1], reverse=True))

    def compact_context(self, token_deficit: int, approx_chars_per_token: int = 4) -> Dict[str, Any]:
        """
        Сжатие контекста: ранжирует файлы по центральности и определяет
        список кандидатов на компрессию/выгрузку для высвобождения токенов.
        """
        centrality = self.compute_centrality()
        needed_chars = token_deficit * approx_chars_per_token
        freed_chars = 0
        evicted_files: List[Dict[str, Any]] = []
        retained_files: List[Dict[str, Any]] = []

        # Сортировка от наименее важных (низкая центральность) к наиболее важным
        sorted_files = sorted(centrality.items(), key=lambda x: x[1])

        for file, score in sorted_files:
            size = self.file_sizes.get(file, 0)
            # Защита файлов ядра, Конституции и манифеста идентичности от вытеснения (pinned: true)
            if "BIBLE.md" in file or "identity.md" in file or "classify_diff.py" in file or "protected_paths.yaml" in file:
                retained_files.append({"file": file, "score": score, "size_bytes": size, "reason": "Pinned Core / Living Identity"})
                continue

            if freed_chars < needed_chars:
                freed_chars += size
                evicted_files.append({"file": file, "score": score, "size_bytes": size, "action": "summarize_or_evict"})
            else:
                retained_files.append({"file": file, "score": score, "size_bytes": size, "action": "keep_full"})

        return {
            "token_deficit": token_deficit,
            "target_freed_chars": needed_chars,
            "actual_freed_chars": freed_chars,
            "approx_tokens_freed": freed_chars // approx_chars_per_token,
            "evicted_count": len(evicted_files),
            "retained_count": len(retained_files),
            "evicted_files": evicted_files,
            "retained_files": retained_files,
        }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ContextFit Graph-Centrality Memory Manager")
    parser.add_argument("--repo", default=".", help="Корень репозитория")
    parser.add_argument("--analyze", action="store_true", help="Анализ связности графа импортов")
    parser.add_argument("--compact", action="store_true", help="Расчет сжатия контекста")
    parser.add_argument("--deficit", type=int, default=2000, help="Дефицит токенов в контексте")
    parser.add_argument("--json", action="store_true", help="Вывод в формате JSON")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    manager = ContextFitManager(repo_path=args.repo)

    if args.compact:
        result = manager.compact_context(token_deficit=args.deficit)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    elif args.analyze or args.json:
        centrality = manager.compute_centrality()
        payload = {
            "total_files": len(centrality),
            "centrality_rankings": centrality
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0
    else:
        # Вывод краткой сводки по топ-10 узлам
        centrality = manager.compute_centrality()
        print("\n=== ContextFit: Топ-10 центральных узлов кодовой базы ===")
        for i, (file, score) in enumerate(list(centrality.items())[:10], 1):
            print(f"{i:2d}. {file:<45} [Score: {score:.4f}]")
        print("========================================================\n")
        return 0


if __name__ == "__main__":
    sys.exit(main())
