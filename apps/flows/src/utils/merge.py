"""
Глубокое слияние для переопределения flow-конфигов.

Используется для слияния базового конфига из БД с inline-переопределениями из flow.json.
"""

import copy

from core.types import JsonObject, require_json_object, require_json_value

_DEFAULT_EXCLUDED_KEYS = frozenset({"node_id", "tool_id", "flow_id"})


def deep_merge(
    base: JsonObject,
    override: JsonObject,
    exclude: set[str] | None = None,
) -> JsonObject:
    """
    Deep merge override в base.

    Правила:
    - Dict + Dict = рекурсивный merge
    - List заменяется целиком
    - Scalar заменяется
    - None в override НЕ перезаписывает (пропускается)

    Аргументы:
        base: Базовый конфиг (из БД)
        override: Переопределения (inline из flow.json или API)
        exclude: Ключи которые не переопределяются (node_id, tool_id, flow_id)

    Возвращает:
        Новый dict с объединенным конфигом
    """
    excluded_keys = _DEFAULT_EXCLUDED_KEYS if exclude is None else exclude
    result: JsonObject = copy.deepcopy(base)

    for key, value in override.items():
        if key in excluded_keys:
            continue
        if value is None:
            continue
        current_value = result.get(key)
        if isinstance(current_value, dict) and isinstance(value, dict):
            result[key] = deep_merge(
                require_json_object(current_value, f"deep_merge.base.{key}"),
                require_json_object(value, f"deep_merge.override.{key}"),
                exclude,
            )
        else:
            result[key] = require_json_value(
                copy.deepcopy(value),
                f"deep_merge.override.{key}",
            )

    return result
