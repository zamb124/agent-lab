"""
Условия для output_actions триггера: одна реализация для рантайма и тестов.

Формат строки `condition` (как в OutputAction):
- пусто — выполнять;
- выражение без `==` и `!=` — truthiness через `MappingResolver.resolve_value`;
- сравнение: `left == right` или `left != right`, где слева — выражение для MappingResolver
  (например `@state:variables.flag`), справа — литерал (строка в кавычках, true/false, число).
"""

from typing import Any, Dict

from apps.flows.src.mapping import MappingResolver


def parse_output_condition_literal(value: str) -> Any:
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

    try:
        return int(value)
    except ValueError:
        pass

    try:
        return float(value)
    except ValueError:
        pass

    return value


def evaluate_output_action_condition(condition: str, state: Dict[str, Any]) -> bool:
    """
    Проверяет условие из `OutputAction.condition` относительно `state` (и резолвера @state: / @var:).
    """
    if not condition:
        return True

    if "==" not in condition and "!=" not in condition:
        value = MappingResolver.resolve_value(condition, state)
        return bool(value)

    for op in ("==", "!="):
        if op in condition:
            parts = condition.split(op, 1)
            if len(parts) != 2:
                return True

            left = MappingResolver.resolve_value(parts[0].strip(), state)
            right = parse_output_condition_literal(parts[1].strip())

            if op == "==":
                return left == right
            return left != right

    return True


__all__ = ["evaluate_output_action_condition", "parse_output_condition_literal"]
