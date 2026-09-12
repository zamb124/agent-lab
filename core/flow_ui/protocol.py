"""Flow UI поверх A2A 1.0: mediaType, artifactId и payload-модели без расширений.

Вниз (agent → client) идут Artifacts со стабильными ``artifactId``:
``state`` (snapshot ``application/json`` + патчи ``application/json-patch+json``),
``response``/``reasoning`` (текст), ``ui`` (``application/vnd.platform.ui+json``).
Вверх (client → agent) — обычное Message: ``text`` Part или один ``data`` Part
``application/vnd.platform.ui-action+json``.
"""

from __future__ import annotations

from typing import Annotated, Literal, cast

from pydantic import Field, SerializerFunctionWrapHandler, model_serializer

from core.flow_ui.document import (
    FlowUIActionName,
    FlowUIBlock,
    FlowUIBlockId,
    FlowUIPageId,
)
from core.models.base import StrictBaseModel
from core.types import JsonObject, JsonValue, require_json_object

JSON_MEDIA_TYPE = "application/json"
JSON_PATCH_MEDIA_TYPE = "application/json-patch+json"
FLOW_UI_MEDIA_TYPE = "application/vnd.platform.ui+json"
FLOW_UI_ACTION_MEDIA_TYPE = "application/vnd.platform.ui-action+json"
TEXT_MEDIA_TYPE = "text/plain"

FLOW_UI_OUTPUT_MEDIA_TYPES: tuple[str, ...] = (
    TEXT_MEDIA_TYPE,
    JSON_MEDIA_TYPE,
    JSON_PATCH_MEDIA_TYPE,
    FLOW_UI_MEDIA_TYPE,
)

STATE_ARTIFACT_ID = "state"
UI_ARTIFACT_ID = "ui"
# Текстовые артефакты различаются по name: у каждого потока текста свой artifact_id.
RESPONSE_ARTIFACT_NAME = "response"
REASONING_ARTIFACT_NAME = "reasoning"

CONVERSATION_SLOT_ID = "conversation"


class FlowUIAction(StrictBaseModel):
    """Событие хода от интерактивного блока; живёт в ``ExecutionState.ui_action``."""

    name: FlowUIActionName
    source: FlowUIBlockId
    payload: JsonObject = Field(default_factory=dict)


class FlowUIActionMessage(StrictBaseModel):
    """Payload входящего Part ``application/vnd.platform.ui-action+json``."""

    action: FlowUIActionName
    source: FlowUIBlockId
    fields: JsonObject = Field(
        default_factory=dict, description="Значения input-блоков по их field"
    )
    payload: JsonObject = Field(default_factory=dict)

    def to_state_action(self) -> FlowUIAction:
        return FlowUIAction(name=self.action, source=self.source, payload=self.payload)


class FlowUIRender(StrictBaseModel):
    """Агент показывает блоки в цели рендера (``slot`` заменяется, ``conversation`` дополняется)."""

    kind: Literal["render"] = "render"
    slot_id: FlowUIBlockId
    blocks: list[FlowUIBlock] = Field(min_length=1)


class FlowUINavigate(StrictBaseModel):
    kind: Literal["navigate"] = "navigate"
    page_id: FlowUIPageId


FlowUIEvent = Annotated[FlowUIRender | FlowUINavigate, Field(discriminator="kind")]


class JsonPatchOperation(StrictBaseModel):
    """RFC 6902 операция; платформа порождает только add/replace/remove."""

    op: Literal["add", "replace", "remove"]
    path: str = Field(pattern=r"^(/.*)?$")
    value: JsonValue = None

    @model_serializer(mode="wrap")
    def _without_removed_value(self, handler: SerializerFunctionWrapHandler) -> JsonObject:
        payload = require_json_object(cast(object, handler(self)), "JsonPatchOperation")
        if self.op == "remove" and "value" in payload:
            del payload["value"]
        return payload


__all__ = [
    "CONVERSATION_SLOT_ID",
    "FLOW_UI_ACTION_MEDIA_TYPE",
    "FLOW_UI_MEDIA_TYPE",
    "FLOW_UI_OUTPUT_MEDIA_TYPES",
    "JSON_MEDIA_TYPE",
    "JSON_PATCH_MEDIA_TYPE",
    "REASONING_ARTIFACT_NAME",
    "RESPONSE_ARTIFACT_NAME",
    "STATE_ARTIFACT_ID",
    "TEXT_MEDIA_TYPE",
    "UI_ARTIFACT_ID",
    "FlowUIAction",
    "FlowUIActionMessage",
    "FlowUIEvent",
    "FlowUINavigate",
    "FlowUIRender",
    "JsonPatchOperation",
]
