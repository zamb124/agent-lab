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
from collections.abc import Mapping
from typing import TYPE_CHECKING, cast

from pydantic import BaseModel

from core.types import JsonObject, JsonValue, require_json_object, require_json_value
from core.variables import VarResolver

if TYPE_CHECKING:
    from core.state import ExecutionState

_VAR_FULL_VAR = VarResolver.VAR_REF_PATTERN
type MappingState = ExecutionState | JsonObject


def _state_variables(state: MappingState) -> Mapping[str, JsonValue]:
    if isinstance(state, Mapping):
        variables = state.get("variables", {})
        if not isinstance(variables, Mapping):
            raise TypeError("state.variables must be a mapping")
        return require_json_object(variables, "state.variables")
    return state.variables


class MappingResolver:
    """Единая логика резолвинга @state:path и @var:name для всех нод."""

    @staticmethod
    def _as_mapping(value: object) -> Mapping[str, object] | None:
        if isinstance(value, Mapping):
            return cast(Mapping[str, object], value)
        if isinstance(value, BaseModel):
            return cast(
                Mapping[str, object],
                value.model_dump(mode="python", exclude_none=False),
            )
        return None

    @staticmethod
    def resolve_value(source: object, state: MappingState) -> object:
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
            variables = _state_variables(state)
            return VarResolver.resolve_ref(source, variables)

        return source

    @staticmethod
    def get_nested_value(data: MappingState, path: str) -> object | None:
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
        value: object = data

        for key in keys:
            mapping = MappingResolver._as_mapping(value)
            if mapping is None or key not in mapping:
                return None
            value = mapping[key]

        return value

    @staticmethod
    def resolve_vars_in_string(value: JsonValue, variables: Mapping[str, JsonValue]) -> JsonValue:
        """
        Заменяет все @var:path в строке на значения из variables.

        Поддерживает вложенные пути: @var:config.api_key

        Args:
            value: Строка с возможными @var: выражениями
            variables: Словарь переменных

        Returns:
            Строка с подставленными значениями
        """
        if not isinstance(value, str):
            return value
        if not value:
            return value
        return VarResolver.resolve_text(value, variables)

    @staticmethod
    def build_mapped_state(
        mapping: Mapping[str, object],
        state: MappingState,
    ) -> dict[str, object]:
        """
        Строит новый Dict на основе маппинга.

        Args:
            mapping: Маппинг {target_field: source}
            state: ExecutionState или Dict (для тестов)

        Returns:
            Новый Dict с замапленными полями
        """
        result: dict[str, object] = {}

        for target_field, source in mapping.items():
            result[target_field] = MappingResolver.resolve_value(source, state)

        return result

    @staticmethod
    def resolve_json_template_string(
        s: str,
        state: MappingState,
        variables: Mapping[str, JsonValue],
    ) -> JsonValue:
        """
        Резолвит одну строку внутри JSON-шаблона тела запроса external_api.

        - Полная строка @state:path или @var:path — значение любого типа из state / variables.
        - Иначе при наличии подстроки @state: — ошибка (смешанный текст запрещён).
        - Иначе подстановка токенов @var: через VarResolver.resolve_text.
        """
        if s.startswith("@state:"):
            return require_json_value(
                MappingResolver.resolve_value(s, state),
                "JSON body template @state value",
            )
        if _VAR_FULL_VAR.match(s):
            return require_json_value(
                MappingResolver.resolve_value(s, state),
                "JSON body template @var value",
            )
        if "@state:" in s:
            raise ValueError(
                "JSON body template: mixed text with @state: is not supported; "
                + "use a whole-string @state:path or @var:path reference"
            )
        if "@var:" in s:
            return VarResolver.resolve_text(s, variables)
        return s

    @staticmethod
    def resolve_json_template_tree(
        value: JsonValue,
        state: MappingState,
        variables: Mapping[str, JsonValue],
    ) -> JsonValue:
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
        state: MappingState,
        variables: Mapping[str, JsonValue],
    ) -> JsonValue:
        """Парсит JSON body_template и резолвит плейсхолдеры."""
        raw = body_template.strip()
        if not raw:
            return {}
        parsed = require_json_value(cast(object, json.loads(raw)), "body_template")
        return MappingResolver.resolve_json_template_tree(parsed, state, variables)

    @staticmethod
    def _coerce_to_header_string(value: object) -> str:
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
        value: str,
        state: MappingState,
        variables: Mapping[str, JsonValue],
    ) -> str:
        """
        Значение одного HTTP-заголовка: те же правила, что resolve_json_template_string, итог — str.
        """
        resolved = MappingResolver.resolve_json_template_string(value, state, variables)
        return MappingResolver._coerce_to_header_string(resolved)
