"""
Универсальный deep merge для переопределения конфигов.

Используется для merge базовой сущности из БД с inline переопределениями из agent.json.
"""

import copy
from typing import Any, Dict, Optional, Set


def deep_merge(
    base: Dict[str, Any],
    override: Dict[str, Any],
    exclude: Optional[Set[str]] = None,
) -> Dict[str, Any]:
    """
    Deep merge override в base.

    Правила:
    - Dict + Dict = рекурсивный merge
    - List заменяется целиком
    - Scalar заменяется
    - None в override НЕ перезаписывает (пропускается)

    Args:
        base: Базовый конфиг (из БД)
        override: Переопределения (inline из agent.json)
        exclude: Ключи которые не переопределяются (node_id, tool_id, agent_id)

    Returns:
        Новый dict с объединенным конфигом
    """
    exclude = exclude or {"node_id", "tool_id", "agent_id"}
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

