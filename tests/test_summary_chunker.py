#!/usr/bin/env python3
"""
Unit tests for Core/SummaryChunker.py
Verifies Summary-Augmented Markdown splitting and context preservation.
"""

import unittest
from Core.SummaryChunker import SummaryAugmentedChunker


class TestSummaryChunker(unittest.TestCase):

    def setUp(self):
        self.chunker = SummaryAugmentedChunker()

    def test_chunk_markdown_hierarchy(self):
        """Проверка разбиения с добавлением контекста родительских секций."""
        md = "# Root Title\nDoc summary line.\n\n## Section One\nContent for section 1.\n\n## Section Two\nContent for section 2."
        chunks = self.chunker.chunk_markdown(md, doc_name="TestDoc")
        self.assertGreaterEqual(len(chunks), 2)
        self.assertIn("augmented_summary", chunks[0])
        self.assertIn("TestDoc", chunks[0]["augmented_summary"])


if __name__ == "__main__":
    unittest.main()
