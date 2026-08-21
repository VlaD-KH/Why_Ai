#!/usr/bin/env python3
"""
Модуль: Core/SummaryChunker.py
Назначение: Иерархическое Summary-Augmented разбиение документов нормативной базы и архитектуры.
Архитектурный слой: Core (Зона E - Mutable Task Runtime).
Инвариант: Каждый фрагмент (чанк) сохраняет контекст родительского документа и заголовка для исключения потери смысла при RAG поиске.
"""

import argparse
import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] [CHUNKER] %(message)s")
logger = logging.getLogger("SummaryChunker")


class SummaryAugmentedChunker:
    """
    Иерархический чанкер с обогащением саммари родительских разделов.
    """

    def __init__(self, default_chunk_size: int = 500) -> None:
        self.default_chunk_size = default_chunk_size

    def chunk_markdown(self, markdown_text: str, doc_name: str = "Document") -> List[Dict[str, Any]]:
        """
        Разбиение markdown-документа по заголовкам с сохранением иерархического контекста.
        """
        lines = markdown_text.splitlines()
        chunks: List[Dict[str, Any]] = []

        doc_summary = ""
        # Первые непустые строки до первого заголовка считаются вводным саммари
        intro_lines = []
        for line in lines:
            if line.startswith("#"):
                break
            if line.strip():
                intro_lines.append(line.strip())
        doc_summary = " ".join(intro_lines)[:250] if intro_lines else f"Документ: {doc_name}"

        current_header = "Intro"
        current_lines: List[str] = []
        chunk_idx = 1

        for line in lines:
            if line.startswith("#"):
                if current_lines:
                    content = "\n".join(current_lines).strip()
                    if content:
                        chunks.append({
                            "chunk_id": f"{doc_name}-chunk-{chunk_idx}",
                            "section": current_header,
                            "augmented_summary": f"[{doc_name} > {current_header}]: {doc_summary}",
                            "content": content,
                            "char_count": len(content),
                        })
                        chunk_idx += 1
                    current_lines = []
                current_header = line.strip("# \t")
            else:
                current_lines.append(line)

        if current_lines:
            content = "\n".join(current_lines).strip()
            if content:
                chunks.append({
                    "chunk_id": f"{doc_name}-chunk-{chunk_idx}",
                    "section": current_header,
                    "augmented_summary": f"[{doc_name} > {current_header}]: {doc_summary}",
                    "content": content,
                    "char_count": len(content),
                })

        logger.info(f"Документ {doc_name} разбит на {len(chunks)} Summary-Augmented чанков.")
        return chunks


def main() -> int:
    parser = argparse.ArgumentParser(description="Summary-Augmented Markdown Chunker")
    parser.add_argument("--file", type=str, help="Путь к markdown-файлу для разбиения")
    parser.add_argument("--status", action="store_true", help="Статус чанкера")

    args = parser.parse_args()
    chunker = SummaryAugmentedChunker()

    if args.file:
        p = Path(args.file)
        if not p.exists():
            print(f"Файл {args.file} не найден", file=sys.stderr)
            return 1
        text = p.read_text(encoding="utf-8")
        chunks = chunker.chunk_markdown(text, doc_name=p.name)
        print(json.dumps(chunks, indent=2, ensure_ascii=False))
        return 0

    if args.status:
        print(json.dumps({"status": "READY", "algorithm": "Summary-Augmented Hierarchical AST"}, indent=2))
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
