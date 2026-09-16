"""
MappingResolver - единая логика резолвинга @state:path и @var:name.

Используется в:
- LlmNode / FlowNode / RemoteFlowNode / CodeAgentNode (input_mapping)
- ExternalAPIClient / SMS (URL, headers, body_template)
- RemoteFlowNode / CodeAgentNode (metadata_template → A2A params.metadata)
- CodeAgentNode (guest_env → контейнер; @platform:KEY из platform env)
- HitlNode (handoff_task_title / handoff_user_message)

Свободные строки (headers, URL, HITL): resolve_interpolated_string.
JSON-ячейки body (typed whole-ref): resolve_json_template_string / tree.
input_mapping ячейки: resolve_value / build_mapped_state.

Синтаксис:
- "@state:field" -> state.field
- "@state:user.profile.name" -> state.user.profile.name
- "@state" -> весь state (model_dump JSON)
- "@var:name" -> state.variables["name"] (или overlay variables=)
- "@var:nested.path" -> вложенный путь
- в свободной строке: токены @state: / @var: в тексте
- "constant" -> "constant"

Zero-Guess: работает с ExecutionState напрямую (но может принимать dict для тестов).
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import TYPE_CHECKING, ClassVar, cast

from pydantic import BaseModel

from core.guest_runtime.env import validate_guest_env
from core.types import JsonObject, JsonValue, require_json_object, require_json_value
from core.variables import VarResolver

PLATFORM_ENV_PREFIX = "@platform:"

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

    _STATE_TOKEN_PATTERN: ClassVar[re.Pattern[str]] = re.compile(
        r"@state:([a-zA-Z_][a-zA-Z0-9_.]*)"
    )

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

        Аргументы:
            source: Источник значения (@state:path, @var:name или константа)
            state: ExecutionState или Dict (для тестов)

        Возвращает:
            Значение из state по пути, из переменных или константа
        """
        if not isinstance(source, str):
            return source

        if source == "@state":
            return MappingResolver.dump_state(state)

        if source.startswith("@state:"):
            path = source[7:]
            return MappingResolver.get_nested_value(state, path)

        if source.startswith("@var:"):
            variables = _state_variables(state)
            return VarResolver.resolve_ref(source, variables)

        return source

    @staticmethod
    def dump_state(state: MappingState) -> JsonObject:
        if isinstance(state, BaseModel):
            dumped = state.model_dump(mode="json", exclude_none=False)
            return require_json_object(dumped, "mapping.state")
        return require_json_object(dict(state), "mapping.state")

    @staticmethod
    def get_nested_value(data: MappingState, path: str) -> object | None:
        """
        Получает значение по вложенному пути из любого объекта.

        Работает с ExecutionState (через атрибуты) и с dict (через ключи).

        Аргументы:
            data: Объект (ExecutionState, dict, или любой другой)
            path: Путь вида "user.profile.name"

        Возвращает:
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

        Аргументы:
            value: Строка с возможными @var: выражениями
            variables: Словарь переменных

        Возвращает:
            Строка с подставленными значениями
        """
        if not isinstance(value, str):
            return value
        if not value:
            return value
        return VarResolver.resolve_text(value, variables)

    @classmethod
    def resolve_state_text(cls, value: str, state: MappingState) -> str:
        """
        Заменяет все @state:path токены в строке на значения из state.

        Отсутствующий путь или None → ValueError (Zero-Guess).
        """
        if not value or "@state:" not in value:
            return value

        def replace_state(match: re.Match[str]) -> str:
            path = match.group(1)
            resolved = MappingResolver.get_nested_value(state, path)
            if resolved is None:
                raise ValueError(f"@state:{path} resolved to None")
            return MappingResolver.stringify_mapping_value(resolved)

        return cls._STATE_TOKEN_PATTERN.sub(replace_state, value)

    @classmethod
    def resolve_interpolated_string(
        cls,
        value: str,
        state: MappingState,
        *,
        variables: Mapping[str, JsonValue] | None = None,
    ) -> str:
        """
        Свободная строка: @state: / @var: (целая ссылка или токены в тексте) → str.

        Канон для HITL title/message, HTTP headers, URL.
        Brace {var} не резолвится (только VariableResolver для LLM prompts).
        variables — overlay поверх state.variables для @var:.
        """
        raw = value.strip()
        if not raw:
            return raw

        effective_vars: JsonObject = dict(_state_variables(state))
        if variables is not None:
            effective_vars.update(dict(variables))

        if raw.startswith("@state:"):
            resolved = MappingResolver.resolve_value(raw, state)
            if resolved is None:
                raise ValueError(f"{raw!r} resolved to None")
            return cls.stringify_mapping_value(resolved).strip()

        if _VAR_FULL_VAR.match(raw) is not None:
            resolved = VarResolver.resolve_ref(raw, effective_vars)
            return cls.stringify_mapping_value(resolved).strip()

        text = raw
        if "@state:" in text:
            text = cls.resolve_state_text(text, state)
        if "@var:" in text:
            text = VarResolver.resolve_text(text, effective_vars)
        return text.strip()

    @staticmethod
    def build_mapped_state(
        mapping: Mapping[str, object],
        state: MappingState,
    ) -> dict[str, object]:
        """
        Строит новый Dict на основе маппинга.

        Аргументы:
            mapping: Маппинг {target_field: source}
            state: ExecutionState или Dict (для тестов)

        Возвращает:
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
        - Иначе при наличии подстроки @state: — ошибка (смешанный текст запрещён;
          для свободного текста используйте resolve_interpolated_string).
        - Иначе подстановка токенов @var: через resolve_interpolated_string.
        """
        if s == "@state" or s.startswith("@state:"):
            return require_json_value(
                MappingResolver.resolve_value(s, state),
                "JSON body template @state value",
            )
        if _VAR_FULL_VAR.match(s):
            effective_vars: JsonObject = dict(_state_variables(state))
            effective_vars.update(dict(variables))
            resolved = VarResolver.resolve_ref(s, effective_vars)
            return require_json_value(resolved, "JSON body template @var value")
        if "@state:" in s:
            raise ValueError(
                "JSON body template: mixed text with @state: is not supported; "
                + "use a whole-string @state:path or @var:path reference"
            )
        if "@var:" in s:
            return MappingResolver.resolve_interpolated_string(
                s, state, variables=variables
            )
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
    def stringify_mapping_value(value: object) -> str:
        """Скаляр или JSON в одну строку для HTTP-заголовка / interpolated string."""
        if value is None:
            raise ValueError("template resolved to None")
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
        """HTTP-заголовок / URL: resolve_interpolated_string (включая mixed @state:)."""
        return MappingResolver.resolve_interpolated_string(
            value, state, variables=variables
        )

    @staticmethod
    def resolve_env_mapping(
        mapping: Mapping[str, str],
        state: MappingState,
        *,
        platform: Mapping[str, str],
    ) -> dict[str, str]:
        resolved: dict[str, str] = {}
        for key, source in mapping.items():
            if source.startswith(PLATFORM_ENV_PREFIX):
                platform_key = source[len(PLATFORM_ENV_PREFIX) :]
                if platform_key not in platform:
                    raise ValueError(f"guest_env {key}: unknown {PLATFORM_ENV_PREFIX}{platform_key}")
                text = platform[platform_key]
            else:
                value = MappingResolver.resolve_value(source, state)
                text = MappingResolver.stringify_mapping_value(value)
            if text.strip() == "":
                raise ValueError(f"guest_env {key} resolved to an empty string")
            resolved[key] = text
        return validate_guest_env(resolved)
