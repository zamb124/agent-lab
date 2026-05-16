"""
Универсальный deep merge для переопределения конфигов.

Используется для merge базового конфига из БД с inline переопределениями из flow.json.
"""

import copy
from typing import Any


def deep_merge(
    base: dict[str, Any],
    override: dict[str, Any],
    exclude: set[str] | None = None,
) -> dict[str, Any]:
    """
    Deep merge override в base.

    Правила:
    - Dict + Dict = рекурсивный merge
    - List заменяется целиком
    - Scalar заменяется
    - None в override НЕ перезаписывает (пропускается)

    Args:
        base: Базовый конфиг (из БД)
        override: Переопределения (inline из flow.json или API)
        exclude: Ключи которые не переопределяются (node_id, tool_id, flow_id)

    Returns:
        Новый dict с объединенным конфигом
    """
    exclude = exclude or {"node_id", "tool_id", "flow_id"}
    result = copy.deepcopy(base)

    for key, value in override.items():
        if key in exclude:
            continue
        if value is None:
            continue
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value, exclude)
        else:
            result[key] = copy.deepcopy(value)

    return result

