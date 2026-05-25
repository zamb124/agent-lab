"""Canonical branch API contracts."""

from __future__ import annotations

from pydantic import Field, model_validator

from core.models import StrictBaseModel
from core.types import JsonObject, require_json_object

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
    """Canonical branch payload used by create/update APIs."""

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

    @model_validator(mode="before")
    @classmethod
    def _normalize_variables(cls, data: object) -> object:
        """Нормализует variables: простые значения -> FlowVariableConfig."""
        return normalize_flow_variables_payload(data)


class BranchCreateRequest(BranchPayload):
    """Create branch request."""

    branch_id: str = Field(..., min_length=1)


class BranchUpdateRequest(BranchPayload):
    """Full branch replacement request."""


class BranchSummaryResponse(StrictBaseModel):
    """Branch list item."""

    id: str
    name: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)


class BranchDetailResponse(StrictBaseModel):
    """Canonical branch read response."""

    id: str
    name: str
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


class BranchMutationResponse(StrictBaseModel):
    """Branch mutation result."""

    status: str
    message: str
    branch_id: str


def branch_payload_to_config(payload: BranchPayload) -> BranchConfig:
    """Convert canonical branch payload to stored branch config."""
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
    )


def branch_summary_response(branch_id: str, branch_cfg: BranchConfig) -> BranchSummaryResponse:
    """Build canonical branch list item."""
    return BranchSummaryResponse(
        id=branch_id,
        name=branch_cfg.name,
        description=branch_cfg.description,
        tags=branch_cfg.tags,
    )


def branch_detail_response(branch_id: str, branch_cfg: BranchConfig) -> BranchDetailResponse:
    """Build canonical branch read response."""
    return BranchDetailResponse(
        id=branch_id,
        name=branch_cfg.name,
        description=branch_cfg.description,
        tags=branch_cfg.tags,
        permission=branch_cfg.permission,
        entry=branch_cfg.entry,
        nodes=branch_cfg.nodes,
        nodes_mode=branch_cfg.nodes_mode,
        edges=branch_cfg.edges,
        edges_mode=branch_cfg.edges_mode,
        variables=branch_cfg.variables,
        variables_mode=branch_cfg.variables_mode,
        resources=branch_cfg.resources,
        resources_mode=branch_cfg.resources_mode,
        speech=branch_cfg.speech,
    )


def branch_model_dump(model: StrictBaseModel) -> JsonObject:
    """Dump branch DTO as a strict JSON object."""
    return require_json_object(model.model_dump(mode="json"), type(model).__name__)
