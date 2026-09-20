"""Контракт durable time-travel: один payload на REST и WS."""

from __future__ import annotations

from pydantic import Field

from apps.flows.src.durable_execution.models import WorkflowBranchRecord, WorkflowEventRecord
from core.models.base import StrictBaseModel
from core.state import ExecutionState


class DurableSessionStatePayload(StrictBaseModel):
    session_id: str | None = Field(default=None, min_length=1)
    context_id: str | None = Field(default=None, min_length=1)
    flow_id: str | None = Field(default=None, min_length=1)


class DurableSessionStateUpdatePayload(DurableSessionStatePayload):
    state: ExecutionState


class DurableHistoryPayload(StrictBaseModel):
    session_id: str = Field(min_length=1)
    execution_branch_id: str | None = Field(default=None, min_length=1)
    limit: int = Field(default=200, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)


class DurableSessionIdPayload(StrictBaseModel):
    session_id: str = Field(min_length=1)


class DurableStateAtPayload(StrictBaseModel):
    session_id: str = ""
    sequence: int = Field(ge=0)
    execution_branch_id: str | None = Field(default=None, min_length=1)


class DurableForkPayload(StrictBaseModel):
    session_id: str = ""
    sequence: int = Field(ge=0)
    execution_branch_id: str | None = Field(default=None, min_length=1)
    activate: bool = False


class DurableRewindPayload(StrictBaseModel):
    session_id: str = ""
    sequence: int = Field(ge=0)
    execution_branch_id: str | None = Field(default=None, min_length=1)


class DurableManualPatchPayload(StrictBaseModel):
    session_id: str = ""
    sequence: int = Field(ge=0)
    state: ExecutionState
    execution_branch_id: str | None = Field(default=None, min_length=1)
    activate: bool = True


class DurableRetryPayload(StrictBaseModel):
    session_id: str = ""
    failed_sequence: int | None = Field(default=None, ge=1)
    execution_branch_id: str | None = Field(default=None, min_length=1)


class WorkflowBranchesResponse(StrictBaseModel):
    branches: list[WorkflowBranchRecord]


class WorkflowHistoryResponse(StrictBaseModel):
    events: list[WorkflowEventRecord]
    total: int
    limit: int
    offset: int
