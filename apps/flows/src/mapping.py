"""
MappingResolver - единая логика резолвинга @state:path и @var:name.

Используется в:
- LlmNode (input_mapping)
- FlowNode (input_mapping)
- RemoteFlowNode (input_mapping, headers, url)
- ExternalAPIClient (URL, headers; body_template через resolve_json_template_tree)

Синтаксис:
- "@state:field" -> state.field
- "@state:user.profile.name" -> state.user.profile.name
- "@var:name" -> state.variables["name"]
- "@var:nested.path" -> state.variables["nested"]["path"]
- "constant" -> "constant" (любое значение без префикса)

Zero-Guess: работает с ExecutionState напрямую (но может принимать dict для тестов).
"""

from __future__ import annotations

import json
from typing import Any, Dict, Union, TYPE_CHECKING

from core.variables import VarResolver

if TYPE_CHECKING:
    from core.state import ExecutionState

_VAR_FULL_VAR = VarResolver._VAR_REF_PATTERN


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
            # Получаем variables - либо из ExecutionState, либо из dict
            if isinstance(state, dict):
                variables = state.get("variables", {})
            else:
                variables = state.variables
            return VarResolver.resolve_ref(source, variables)

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
        return VarResolver.resolve_text(value, variables)

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

    @staticmethod
    def resolve_json_template_string(
        s: str,
        state: Union["ExecutionState", Dict[str, Any]],
        variables: Dict[str, Any],
    ) -> Any:
        """
        Резолвит одну строку внутри JSON-шаблона тела запроса external_api.

        - Полная строка @state:path или @var:path — значение любого типа из state / variables.
        - Иначе при наличии подстроки @state: — ошибка (смешанный текст запрещён).
        - Иначе подстановка токенов @var: через VarResolver.resolve_text.
        """
        if not isinstance(s, str):
            raise TypeError("resolve_json_template_string expects str")
        if s.startswith("@state:"):
            return MappingResolver.resolve_value(s, state)
        if _VAR_FULL_VAR.match(s):
            return MappingResolver.resolve_value(s, state)
        if "@state:" in s:
            raise ValueError(
                "JSON body template: mixed text with @state: is not supported; "
                "use a whole-string @state:path or @var:path reference"
            )
        if "@var:" in s:
            return VarResolver.resolve_text(s, variables)
        return s

    @staticmethod
    def resolve_json_template_tree(
        value: Any,
        state: Union["ExecutionState", Dict[str, Any]],
        variables: Dict[str, Any],
    ) -> Any:
        """
        Рекурсивно резолвит JSON-дерево после json.loads (тело external_api).
        """
        if isinstance(value, dict):
            return {
                str(k): MappingResolver.resolve_json_template_tree(v, state, variables)
                for k, v in value.items()
            }
        if isinstance(value, list):
            return [
                MappingResolver.resolve_json_template_tree(item, state, variables)
                for item in value
            ]
        if isinstance(value, str):
            return MappingResolver.resolve_json_template_string(value, state, variables)
        return value

    @staticmethod
    def parse_and_resolve_body_template(
        body_template: str,
        state: Union["ExecutionState", Dict[str, Any]],
        variables: Dict[str, Any],
    ) -> Any:
        """Парсит JSON body_template и резолвит плейсхолдеры."""
        raw = body_template.strip() if isinstance(body_template, str) else ""
        if not raw:
            return {}
        parsed = json.loads(raw)
        return MappingResolver.resolve_json_template_tree(parsed, state, variables)

    @staticmethod
    def _coerce_to_header_string(value: Any) -> str:
        """Скаляр или JSON в одну строку для HTTP-заголовка."""
        if value is None:
            raise ValueError("header template resolved to None")
        if isinstance(value, str):
            return value
        if isinstance(value, (bool, int, float)):
            return str(value)
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        return str(value)

    @staticmethod
    def resolve_http_header_value(
        value: Any,
        state: Union["ExecutionState", Dict[str, Any]],
        variables: Dict[str, Any],
    ) -> str:
        """
        Значение одного HTTP-заголовка: те же правила, что resolve_json_template_string, итог — str.
        """
        if not isinstance(value, str):
            raise TypeError("header value must be str")
        resolved = MappingResolver.resolve_json_template_string(value, state, variables)
        return MappingResolver._coerce_to_header_string(resolved)

