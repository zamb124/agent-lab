"""
MappingResolver - единая логика резолвинга @state:path и @var:name.

Используется в:
- LlmNode (input_mapping)
- FlowNode (input_mapping)
- RemoteFlowNode (input_mapping, auth_headers, url)
- ExternalAPINode (параметры с source)
- ExternalAPIClient (auth_headers, URL, headers)

Синтаксис:
- "@state:field" -> state.field
- "@state:user.profile.name" -> state.user.profile.name
- "@var:name" -> state.variables["name"]
- "@var:nested.path" -> state.variables["nested"]["path"]
- "constant" -> "constant" (любое значение без префикса)

Zero-Guess: работает с ExecutionState напрямую (но может принимать dict для тестов).
"""

from __future__ import annotations

import re
from typing import Any, Dict, Union, TYPE_CHECKING

if TYPE_CHECKING:
    from core.state import ExecutionState


class MappingResolver:
    """Единая логика резолвинга @state:path и @var:name для всех нод."""

    @staticmethod
    def resolve_value(source: Any, state: Union["ExecutionState", Dict[str, Any]]) -> Any:
        """
        Резолвит значение из маппинга.

        Args:
            source: Источник значения (@state:path, @var:name или константа)
            state: ExecutionState или Dict (для тестов)

        Returns:
            Значение из state по пути, из переменных или константа
        """
        if not isinstance(source, str):
            return source

        if source.startswith("@state:"):
            path = source[7:]
            return MappingResolver.get_nested_value(state, path)

        if source.startswith("@var:"):
            var_path = source[5:]
            # Получаем variables - либо из ExecutionState, либо из dict
            if isinstance(state, dict):
                variables = state.get("variables", {})
            else:
                variables = state.variables
            return MappingResolver.get_nested_value(variables, var_path)

        return source

    @staticmethod
    def get_nested_value(data: Any, path: str) -> Any:
        """
        Получает значение по вложенному пути из любого объекта.
        
        Работает с ExecutionState (через атрибуты) и с dict (через ключи).

        Args:
            data: Объект (ExecutionState, dict, или любой другой)
            path: Путь вида "user.profile.name"

        Returns:
            Значение по пути или None если путь не найден
        """
        if not path:
            return None

        keys = path.split(".")
        value = data

        for key in keys:
            # Сначала пробуем как dict (чтобы избежать .items(), .keys() и т.д.)
            if isinstance(value, dict) and key in value:
                value = value[key]
            # Потом пробуем атрибут (для ExecutionState и других объектов)
            elif hasattr(value, key):
                value = getattr(value, key)
            else:
                return None

        return value

    @staticmethod
    def resolve_vars_in_string(value: str, variables: Dict[str, Any]) -> str:
        """
        Заменяет все @var:path в строке на значения из variables.

        Поддерживает вложенные пути: @var:config.api_key

        Args:
            value: Строка с возможными @var: выражениями
            variables: Словарь переменных

        Returns:
            Строка с подставленными значениями
        """
        if not value or not isinstance(value, str):
            return value

        # Паттерн для @var:path.to.value (поддерживает точки)
        pattern = r"@var:([a-zA-Z_][a-zA-Z0-9_.]*)"

        def replace_var(match: re.Match) -> str:
            var_path = match.group(1)
            resolved = MappingResolver.get_nested_value(variables, var_path)
            if resolved is None:
                return match.group(0)  # Оставляем как есть если не найдено
            return str(resolved)

        return re.sub(pattern, replace_var, value)

    @staticmethod
    def build_mapped_state(
        mapping: Dict[str, Any],
        state: Union["ExecutionState", Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Строит новый Dict на основе маппинга.

        Args:
            mapping: Маппинг {target_field: source}
            state: ExecutionState или Dict (для тестов)

        Returns:
            Новый Dict с замапленными полями
        """
        result: Dict[str, Any] = {}

        for target_field, source in mapping.items():
            result[target_field] = MappingResolver.resolve_value(source, state)

        return result

