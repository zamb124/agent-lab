"""
Канонический payload переменных платформы (flow, branch, WorkItem, company).

Симметричен company Variable { value, secret } с опциональными метаданными UI.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from pydantic import Field

from core.models import StrictBaseModel
from core.types import JsonValue, require_json_object, require_json_value


class VariableEntry(StrictBaseModel):
    value: JsonValue = Field(..., description="Значение переменной")
    secret: bool = Field(default=False, description="Скрывать значение в UI")
    public: bool = Field(default=False, description="Публичная переменная для agent-card (A2A)")
    title: str | None = Field(default=None, description="Заголовок переменной")
    description: str | None = Field(default=None, description="Описание переменной")
    order: int | None = Field(default=None, description="Порядок отображения")


VariableMap = dict[str, VariableEntry]


def normalize_variables_map(raw: Mapping[str, object]) -> VariableMap:
    """Нормализует scalar/wrapped JSON в строгий VariableMap."""
    result: VariableMap = {}
    for key, entry_raw in raw.items():
        if isinstance(entry_raw, VariableEntry):
            result[key] = entry_raw
            continue
        if isinstance(entry_raw, Mapping):
            entry_mapping = cast(Mapping[str, object], entry_raw)
            if "value" in entry_mapping:
                result[key] = VariableEntry.model_validate(dict(entry_mapping))
            else:
                entry_object = require_json_object(entry_mapping, f"variables.{key}")
                result[key] = VariableEntry(
                    value=require_json_value(entry_object, f"variables.{key}"),
                    public=False,
                )
            continue
        result[key] = VariableEntry(
            value=require_json_value(entry_raw, f"variables.{key}"),
            public=False,
        )
    return result


def variable_map_to_prompt_values(variables: VariableMap) -> dict[str, JsonValue]:
    """Plain map для prompt-editor: unwrap VariableEntry.value."""
    prompt_values: dict[str, JsonValue] = {}
    for key, entry in variables.items():
        prompt_values[key] = entry.value
    return prompt_values
