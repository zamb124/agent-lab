"""Pydantic contracts for static flow data-flow inspection."""

from __future__ import annotations

from typing import Literal, TypeAlias

from pydantic import Field

from core.models import StrictBaseModel
from core.types import JsonValue

DataflowStatus: TypeAlias = Literal["ok", "missing"]
DataflowSeverity: TypeAlias = Literal["info", "warning", "error"]
DataflowAvailability: TypeAlias = Literal["guaranteed", "maybe", "observed"]
DataflowConfidence: TypeAlias = Literal[
    "runtime_contract",
    "sample",
    "declared",
    "inferred_code",
    "dynamic",
    "observed",
    "nested_static",
]
DataflowSource: TypeAlias = str | list[str]


class DataflowStateDescriptor(StrictBaseModel):
    path: str
    type: str
    source: DataflowSource
    availability: DataflowAvailability
    confidence: DataflowConfidence
    producers: list[str] = Field(default_factory=list)
    sample_value: JsonValue = None
    protected: bool = False
    join_contribution: Literal["non_join"] | None = None


class DataflowIssue(StrictBaseModel):
    code: str
    severity: DataflowSeverity
    message: str
    path: str | None = None
    target: str | None = None


class DataflowMappingSource(StrictBaseModel):
    kind: Literal["state", "var", "const"]
    path: str | None = None


class DataflowConfigRef(StrictBaseModel):
    kind: Literal["state", "var"]
    path: str
    config_path: str


class DataflowInputMappingRow(StrictBaseModel):
    target: str
    source: str
    source_kind: Literal["state", "var", "const"]
    source_path: str | None = None
    status: DataflowStatus
    type: str
    producers: list[str] = Field(default_factory=list)
    sample_value: JsonValue = None


class DataflowConfigRead(StrictBaseModel):
    source_kind: Literal["state", "var"]
    source_path: str
    config_path: str
    status: DataflowStatus
    type: str


class DataflowCanvasChip(StrictBaseModel):
    label: str
    target: str | None = None
    status: DataflowStatus
    type: str | None = None


class DataflowCanvasOutputChip(StrictBaseModel):
    label: str
    type: str
    status: Literal["ok"] = "ok"


class DataflowCanvasSummary(StrictBaseModel):
    inputs: list[DataflowCanvasChip] = Field(default_factory=list)
    outputs: list[DataflowCanvasOutputChip] = Field(default_factory=list)
    has_issues: bool = False


class DataflowNodeInfo(StrictBaseModel):
    node_id: str
    node_type: str
    input_mapping: list[DataflowInputMappingRow] = Field(default_factory=list)
    reads: list[DataflowConfigRead] = Field(default_factory=list)
    writes: list[DataflowStateDescriptor] = Field(default_factory=list)
    observed_writes: list[DataflowStateDescriptor] = Field(default_factory=list)
    observed_at: JsonValue = None
    result_keys: list[str] = Field(default_factory=list)
    issues: list[DataflowIssue] = Field(default_factory=list)
    incoming_state: list[DataflowStateDescriptor] = Field(default_factory=list)
    output_state: list[DataflowStateDescriptor] = Field(default_factory=list)
    canvas: DataflowCanvasSummary = Field(default_factory=DataflowCanvasSummary)


class DataflowInspectResult(StrictBaseModel):
    flow_id: str | None = None
    branch_id: str
    entry: str | None = None
    nodes: dict[str, DataflowNodeInfo] = Field(default_factory=dict)
    variables: list[DataflowStateDescriptor] = Field(default_factory=list)
    issues: list[DataflowIssue] = Field(default_factory=list)


__all__ = [
    "DataflowAvailability",
    "DataflowCanvasChip",
    "DataflowCanvasOutputChip",
    "DataflowCanvasSummary",
    "DataflowConfidence",
    "DataflowConfigRead",
    "DataflowConfigRef",
    "DataflowInspectResult",
    "DataflowInputMappingRow",
    "DataflowIssue",
    "DataflowMappingSource",
    "DataflowNodeInfo",
    "DataflowSeverity",
    "DataflowSource",
    "DataflowStateDescriptor",
    "DataflowStatus",
]
