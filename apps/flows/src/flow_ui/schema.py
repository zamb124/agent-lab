"""JSON Schema грамматики Flow UI для редактора и structured output."""

from __future__ import annotations

from core.flow_ui.document import FlowUIDocument
from core.state.mutation_policy import FROZEN_STATE_FIELDS
from core.types import JsonObject, require_json_object


def flow_ui_schema() -> JsonObject:
    """JSON Schema документа интерфейса; Pydantic-грамматика — единственный источник.

    ``x-flow-ui-frozen-state-fields`` — системные поля state, на которые редактор
    запрещает ссылаться в ``field`` и шаблонах.
    """
    schema = require_json_object(FlowUIDocument.model_json_schema(), "FlowUIDocument schema")
    schema["x-flow-ui-frozen-state-fields"] = sorted(FROZEN_STATE_FIELDS)
    return schema
