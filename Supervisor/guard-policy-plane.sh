#!/usr/bin/env bash
# ==============================================================================
# Скрипт: Supervisor/guard-policy-plane.sh
# Назначение: Глубино-чувствительная блокировка модификации защищенных зон (P/R)
# с поддержкой безопасного онбординга локальных политик внешних проектов.
# ==============================================================================

set -euo pipefail

TARGET_PATH="${1:-}"
MODE="${2:-strict}"

if [[ "$TARGET_PATH" == "--path" ]]; then
    TARGET_PATH="${2:-}"
    MODE="${3:-strict}"
fi

if [[ -z "$TARGET_PATH" ]]; then
    echo "[GUARD] Ошибка: Не указан путь для проверки. Использование: guard-policy-plane.sh --path <путь> [strict|onboard]"
    exit 2
fi

NORMALIZED_PATH=$(echo "$TARGET_PATH" | tr '\\' '/')

# Абсолютно неизменяемый контур супервизора и корня (Root Policy Plane)
IMMUTABLE_ROOT_PATTERNS=(
    "Supervisor/"
    "BIBLE.md"
    "CODEOWNERS"
    ".github/"
    ".gitattributes"
    "settings.json"
    ".ai-loop/policy"
    ".ai-loop/bin"
    ".ai-loop/ledger.jsonl"
)

for pattern in "${IMMUTABLE_ROOT_PATTERNS[@]}"; do
    if [[ "$NORMALIZED_PATH" == *"$pattern"* ]]; then
        echo "[GUARD-VIOLATION] ПОПЫТКА МОДИФИКАЦИИ СУПЕРВИЗОРА/КОНСТИТУЦИИ! Путь: $NORMALIZED_PATH"
        exit 10
    fi
done

# Проверка вложенных политик проектов Project_*/
if [[ "$NORMALIZED_PATH" == *"Project_"*".ai-loop/policy"* || "$NORMALIZED_PATH" == *"Project/.ai-loop/policy"* ]]; then
    if [[ "$MODE" == "onboard" || "$MODE" == "--allow-project-onboarding" ]]; then
        echo "[GUARD] Онбординг локальной политики проекта разрешен: $NORMALIZED_PATH"
        exit 0
    else
        echo "[GUARD-PROJECT] Локальная политика проекта защищена от прямой модификации в runtime: $NORMALIZED_PATH"
        exit 10
    fi
fi

echo "[GUARD] Доступ разрешен: $NORMALIZED_PATH"
exit 0
