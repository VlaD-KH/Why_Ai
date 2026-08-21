#!/usr/bin/env python3
"""
Модуль: Core/PolicyDriftVector.py
Назначение: Векторный дельта-анализ семантического дрейфа политик безопасности через остаточное квантование.
Архитектурный слой: Core (Зона E - Mutable Task Runtime / Self-Evo Analysis).
Инвариант: Обнаружение микро-изменений формулировок правил, маскирующих попытки ослабления защиты. При всплеске ошибки — возврат кода 10.
"""

import argparse
import hashlib
import json
import logging
import math
import os
import re
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] [DRIFT-VECTOR] %(message)s")
logger = logging.getLogger("PolicyDriftVector")

EXIT_ALLOW = 0
EXIT_REQUIRE_HUMAN = 10


class PolicyDriftVectorAnalyzer:
    """
    Анализатор семантического дрейфа политик безопасности без внешних тяжелых зависимостей.
    Использует хешированные n-граммные эмбеддинги и косинусную дельта-метрику.
    """

    def __init__(self, workspace_root: Optional[Path] = None, dim: int = 64) -> None:
        self.workspace_root = (workspace_root or Path.cwd()).resolve()
        self.dim = dim

    def _tokenize_text(self, text: str) -> List[str]:
        """Токенизация текста правил на термы и биграммы."""
        cleaned = re.sub(r"[^\w\s]", " ", text.lower())
        tokens = [t for t in cleaned.split() if len(t) > 1]
        bigrams = [f"{tokens[i]}_{tokens[i+1]}" for i in range(len(tokens) - 1)]
        return tokens + bigrams

    def embed_policy(self, policy_text: str) -> List[float]:
        """Генерация детерминированного плотного вектора для текста политики."""
        tokens = self._tokenize_text(policy_text)
        vector = [0.0] * self.dim
        if not tokens:
            return vector

        for token in tokens:
            # Детерминированное хеширование токена в координату вектора
            h = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16)
            idx = h % self.dim
            sign = 1.0 if ((h >> 8) & 1) == 0 else -1.0
            vector[idx] += sign

        # L2-нормализация
        norm = math.sqrt(sum(x * x for x in vector))
        if norm > 1e-9:
            vector = [x / norm for x in vector]

        return vector

    def calculate_cosine_similarity(self, vec_a: List[float], vec_b: List[float]) -> float:
        """Расчет косинусной близости между двумя эмбеддингами."""
        dot = sum(a * b for a, b in zip(vec_a, vec_b))
        return max(-1.0, min(1.0, dot))

    def evaluate_drift(self, baseline_text: str, candidate_text: str,
                       drift_tolerance_threshold: float = 0.85) -> Dict[str, Any]:
        """
        Оценка семантического дрейфа между базовой (baseline) и предлагаемой (candidate) политикой.
        Если семантическое сходство ниже порога, фиксируется опасный дрейф правил.
        """
        vec_base = self.embed_policy(baseline_text)
        vec_cand = self.embed_policy(candidate_text)

        similarity = self.calculate_cosine_similarity(vec_base, vec_cand)
        drift_delta = 1.0 - similarity

        # Проверка на наличие критических ключевых слов ослабления
        relaxations = []
        relax_patterns = [
            ("require_human -> auto", r"require_human.*auto"),
            ("diff_is_authoritative: false", r"diff_is_authoritative\s*:\s*false"),
            ("MAX_RISK_WINS removal", r"mixed_diff_policy\s*:\s*(?!MAX_RISK_WINS)"),
        ]
        for name, pattern in relax_patterns:
            if re.search(pattern, candidate_text, re.IGNORECASE) and not re.search(pattern, baseline_text, re.IGNORECASE):
                relaxations.append(name)

        is_safe = similarity >= drift_tolerance_threshold and len(relaxations) == 0
        status = "DRIFT_ACCEPTABLE" if is_safe else "SEMANTIC_POLICY_DRIFT_DETECTED"

        result = {
            "schema": "ai-loop/policy-drift-vector/v1",
            "semantic_similarity": round(similarity, 4),
            "drift_delta": round(drift_delta, 4),
            "threshold": drift_tolerance_threshold,
            "status": status,
            "safe": is_safe,
            "explicit_relaxations": relaxations,
            "recommendation": "Одобрить политику" if is_safe else "БЛОКИРОВКА: Обнаружен семантический дрейф или ослабление правил! Требуется человек.",
        }

        logger.info(f"Оценка дрейфа политики: Similarity={similarity:.4f}, Safe={is_safe}")
        return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Policy Semantic Drift Vector Analyzer")
    parser.add_argument("--base-file", type=str, help="Базовый файл политики")
    parser.add_argument("--candidate-file", type=str, help="Предлагаемый файл политики")
    parser.add_argument("--simulate-drift", action="store_true", help="Симулировать дрейф правил")

    args = parser.parse_args()
    analyzer = PolicyDriftVectorAnalyzer()

    if args.simulate_drift:
        base = "enforcement:\n  diff_is_authoritative: true\n  mixed_diff_policy: MAX_RISK_WINS\n  gate:\n    CRITICAL: require_human\n"
        mutated = "enforcement:\n  diff_is_authoritative: false\n  mixed_diff_policy: MIN_RISK\n  gate:\n    CRITICAL: auto\n"
        res = analyzer.evaluate_drift(base, mutated)
        print(json.dumps(res, indent=2, ensure_ascii=False))
        return EXIT_REQUIRE_HUMAN

    if args.base_file and args.candidate_file:
        base_txt = Path(args.base_file).read_text(encoding="utf-8")
        cand_txt = Path(args.candidate_file).read_text(encoding="utf-8")
        res = analyzer.evaluate_drift(base_txt, cand_txt)
        print(json.dumps(res, indent=2, ensure_ascii=False))
        return EXIT_ALLOW if res["safe"] else EXIT_REQUIRE_HUMAN

    # Дефолтная самопроверка
    sample = "enforcement:\n  diff_is_authoritative: true\n  mixed_diff_policy: MAX_RISK_WINS\n"
    res = analyzer.evaluate_drift(sample, sample)
    print(json.dumps(res, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
