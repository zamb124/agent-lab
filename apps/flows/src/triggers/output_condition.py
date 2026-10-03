"""
Условия для output_actions триггера: одна реализация для рантайма и тестов.

Формат строки `condition` (как в OutputAction):
- пусто — выполнять;
- выражение без `==` и `!=` — truthiness через `MappingResolver.resolve_value`;
- сравнение: `left == right` или `left != right`, где слева — выражение для MappingResolver
  (например `@state:triggers.my_id.context.flag`), справа — литерал (строка в кавычках, true/false, число).
"""

import re

from apps.flows.src.mapping import MappingResolver
from core.types import JsonObject, JsonValue, require_json_value

_INT_LITERAL = re.compile(r"[+-]?\d(?:_?\d)*\Z")
_FLOAT_LITERAL = re.compile(
    r"[+-]?(?:\d(?:_?\d)*)?\.\d(?:_?\d)*(?:[eE][+-]?\d(?:_?\d)*)?\Z"
    + r"|[+-]?\d(?:_?\d)*\.(?:[eE][+-]?\d(?:_?\d)*)?\Z"
    + r"|[+-]?\d(?:_?\d)*[eE][+-]?\d(?:_?\d)*\Z"
    + r"|[+-]?(?:inf(?:inity)?|nan)\Z",
    re.IGNORECASE,
)


def parse_output_condition_literal(value: str) -> JsonValue:
    """Парсит правую часть сравнения: bool, null, кавычки, int, float, иначе строка."""
    value = value.strip()

    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    if value.lower() in ("null", "none"):
        return None

    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]

    number = parse_numeric_literal(value)
    if number is not None:
        return number
    return value


def parse_numeric_literal(value: str) -> int | float | None:
    if _INT_LITERAL.fullmatch(value) is not None:
        return int(value)
    if _FLOAT_LITERAL.fullmatch(value) is not None:
        return float(value)
    return None


def evaluate_output_action_condition(condition: str, state: JsonObject) -> bool:
    """
    Проверяет условие из `OutputAction.condition` относительно `state` (и резолвера @state: / @var:).
    """
    if not condition:
        return True

    if "==" not in condition and "!=" not in condition:
        value = require_json_value(
            MappingResolver.resolve_value(condition, state),
            "output_action.condition",
        )
        return bool(value)

    for op in ("==", "!="):
        if op in condition:
            parts = condition.split(op, 1)
            if len(parts) != 2:
                return True

            left = require_json_value(
                MappingResolver.resolve_value(parts[0].strip(), state),
                "output_action.condition.left",
            )
            right = parse_output_condition_literal(parts[1].strip())

            if op == "==":
                return left == right
            return left != right

    return True


__all__ = [
    "evaluate_output_action_condition",
    "parse_numeric_literal",
    "parse_output_condition_literal",
]
