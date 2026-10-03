"""Канонические контракты branch API."""

from __future__ import annotations

from pydantic import Field, model_validator

from core.flow_ui.document import FlowUIDocument
from core.models import StrictBaseModel
from core.types import JsonObject, JsonValue

from .enums import MergeMode
from .flow_config import (
    BranchConfig,
    Edge,
    FlowVariableConfig,
    normalize_flow_variables_payload,
)
from .flow_speech_settings import FlowSpeechSettings
from .resource import ResourceReference


class BranchPayload(StrictBaseModel):
    """Канонический payload ветки для create/update API."""

    name: str = Field(..., min_length=1)
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    permission: list[str] = Field(default_factory=list)
    entry: str | None = None
    nodes: dict[str, JsonObject] | None = None
    nodes_mode: MergeMode = MergeMode.REPLACE
    edges: list[Edge] | None = None
    edges_mode: MergeMode = MergeMode.REPLACE
    variables: dict[str, FlowVariableConfig] = Field(default_factory=dict)
    variables_mode: MergeMode = MergeMode.MERGE
    resources: dict[str, ResourceReference] = Field(default_factory=dict)
    resources_mode: MergeMode = MergeMode.MERGE
    speech: FlowSpeechSettings | None = None
    interface: FlowUIDocument | None = Field(
        default=None,
        description="Интерфейс ветки; None — интерфейс flow",
    )

    @model_validator(mode="before")
    @classmethod
    def _normalize_variables(
        cls, data: JsonValue
    ) -> JsonValue | dict[str, JsonValue | dict[str, FlowVariableConfig]]:
        """Нормализует variables: простые значения -> FlowVariableConfig."""
        return normalize_flow_variables_payload(data)


class BranchCreateRequest(BranchPayload):
    """Запрос на создание ветки. REST копирует `flow_id` из path."""

    flow_id: str = ""
    branch_id: str = Field(..., min_length=1)


class BranchUpdateRequest(BranchPayload):
    """Запрос на полную замену ветки. REST копирует `flow_id`/`branch_id` из path."""

    flow_id: str = ""
    branch_id: str = ""


class BranchMutationResponse(StrictBaseModel):
    """Результат мутации ветки."""

    status: str
    message: str
    branch_id: str


def branch_payload_to_config(payload: BranchPayload) -> BranchConfig:
    """Преобразует канонический payload ветки в сохранённый branch config."""
    return BranchConfig(
        name=payload.name,
        description=payload.description,
        tags=payload.tags,
        permission=payload.permission,
        entry=payload.entry,
        nodes=payload.nodes,
        nodes_mode=payload.nodes_mode,
        edges=payload.edges,
        edges_mode=payload.edges_mode,
        variables=payload.variables,
        variables_mode=payload.variables_mode,
        resources=payload.resources,
        resources_mode=payload.resources_mode,
        speech=payload.speech,
        interface=payload.interface,
    )
