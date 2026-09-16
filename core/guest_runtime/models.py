"""Контракт фермы code_agent: GuestRuntime 1:1 с (flow_id, node_id), GuestLease, дерево файлов."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field, field_validator

from core.documents.placement_paths import validate_relative_dir
from core.guest_runtime.env import (
    GUEST_IDLE_TTL_MAX,
    GUEST_IDLE_TTL_MIN,
    validate_guest_env,
)
from core.models.base import StrictBaseModel


class GuestInvokeKind(StrEnum):
    CLI = "cli"
    A2A = "a2a"


class GuestLanguage(StrEnum):
    PYTHON = "python"
    NODE = "node"


class GuestBuildStatus(StrEnum):
    NONE = "none"
    BUILDING = "building"
    READY = "ready"
    FAILED = "failed"


class GuestExecutorKind(StrEnum):
    DOCKER = "docker"
    INPROCESS = "inprocess"


class CodeAgentSourceFile(StrictBaseModel):
    file_id: str = Field(..., min_length=1)
    relative_path: str = Field(..., min_length=1)
    file_size: int = Field(..., ge=0)

    @field_validator("relative_path")
    @classmethod
    def _validate_relative_path(cls, value: str) -> str:
        parts = value.split("/")
        if not parts or parts[-1] == "":
            raise ValueError("relative_path must include a filename")
        parent = "/".join(parts[:-1])
        if parent:
            _ = validate_relative_dir(parent)
        filename = parts[-1]
        if filename in {".", ".."} or "/" in filename:
            raise ValueError("relative_path filename is invalid")
        return value


class GuestRuntime(StrictBaseModel):
    guest_runtime_id: str = Field(..., min_length=1)
    flow_id: str = Field(..., min_length=1)
    node_id: str = Field(..., min_length=1)
    company_id: str = Field(..., min_length=1)
    catalog_id: str = Field(..., min_length=1)
    language: GuestLanguage
    invoke_kind: GuestInvokeKind
    invoke_argv: list[str] = Field(default_factory=list)
    invoke_listen_port: int | None = Field(default=None, ge=1, le=65535)
    egress_hosts: list[str] = Field(default_factory=list)
    git_url: str | None = None
    source_sha: str | None = None
    image_digest: str | None = None
    image_bytes: int | None = Field(default=None, ge=0)
    build_status: GuestBuildStatus = GuestBuildStatus.NONE
    build_error: str | None = None
    updated_at: datetime


class GuestLease(StrictBaseModel):
    guest_lease_id: str = Field(..., min_length=1)
    company_id: str = Field(..., min_length=1)
    user_id: str = Field(..., min_length=1)
    flow_id: str = Field(..., min_length=1)
    node_id: str = Field(..., min_length=1)
    image_digest: str = Field(..., min_length=1)
    invoke_kind: GuestInvokeKind
    invoke_argv: list[str]
    invoke_listen_port: int | None = None
    started_at: datetime
    last_completed_at: datetime | None = None
    in_flight: int = Field(..., ge=0)
    idle_ttl_seconds: int = Field(..., ge=GUEST_IDLE_TTL_MIN, le=GUEST_IDLE_TTL_MAX)
    executor: GuestExecutorKind
    shim_url: str = Field(..., min_length=1)
    process_id: int | None = None
    container_id: str | None = None


class GuestEnsureLeaseRequest(StrictBaseModel):
    flow_id: str = Field(..., min_length=1)
    node_id: str = Field(..., min_length=1)
    company_id: str = Field(..., min_length=1)
    user_id: str = Field(..., min_length=1)
    catalog_id: str = Field(..., min_length=1)
    language: GuestLanguage
    invoke_kind: GuestInvokeKind
    invoke_argv: list[str]
    invoke_listen_port: int | None = None
    egress_hosts: list[str] = Field(default_factory=list)
    files: list[CodeAgentSourceFile]
    execution_token: str = Field(..., min_length=1)
    llm_proxy_base_url: str = Field(..., min_length=1)
    capability_gateway_base_url: str = Field(..., min_length=1)
    session_id: str = Field(..., min_length=1)
    task_id: str = Field(..., min_length=1)
    context_id: str = Field(..., min_length=1)
    branch_id: str = Field(..., min_length=1)
    channel: str = Field(..., min_length=1)
    source_node_id: str = Field(..., min_length=1)
    request_id: str = Field(..., min_length=1)
    trace_id: str = Field(..., min_length=1)
    namespace: str | None = None
    durable_execution_branch_id: str | None = Field(default=None, min_length=1)
    durable_node_schedule_sequence: int | None = Field(default=None, ge=0)
    durable_superstep_sequence: int | None = Field(default=None, ge=0)
    idle_ttl_seconds: int | None = Field(
        default=None, ge=GUEST_IDLE_TTL_MIN, le=GUEST_IDLE_TTL_MAX
    )
    guest_env: dict[str, str] = Field(default_factory=dict)

    @field_validator("guest_env")
    @classmethod
    def _validate_guest_env(cls, value: dict[str, str]) -> dict[str, str]:
        return validate_guest_env(value)


class GuestEnsureLeaseResponse(StrictBaseModel):
    guest_lease_id: str
    a2a_url: str
    image_digest: str


class GuestRebuildRequest(StrictBaseModel):
    flow_id: str = Field(..., min_length=1)
    node_id: str = Field(..., min_length=1)
    company_id: str = Field(..., min_length=1)
    user_id: str = Field(..., min_length=1)
    catalog_id: str = Field(..., min_length=1)
    language: GuestLanguage
    invoke_kind: GuestInvokeKind
    invoke_argv: list[str]
    invoke_listen_port: int | None = None
    egress_hosts: list[str] = Field(default_factory=list)
    files: list[CodeAgentSourceFile]
    git_url: str | None = None
    source_sha: str | None = None


class GuestRebuildResponse(StrictBaseModel):
    guest_runtime_id: str
    image_digest: str
    image_bytes: int
    build_status: GuestBuildStatus


class GuestRuntimeStatusResponse(StrictBaseModel):
    runtime: GuestRuntime | None = None
    lease: GuestLease | None = None


class GuestLogLine(StrictBaseModel):
    ts: datetime
    event: str = Field(..., min_length=1)
    line: str
    request_id: str | None = None
    trace_id: str | None = None
    task_id: str | None = None
    session_id: str | None = None
    context_id: str | None = None


class GuestRuntimeLogsResponse(StrictBaseModel):
    items: list[GuestLogLine] = Field(default_factory=list)


class GuestLeaseCapError(Exception):
    """Company or cluster lease cap exceeded."""


class GuestBuildBusyError(Exception):
    """Cluster already has a guest image build in progress."""


class CodeAgentEnsureSourceResponse(StrictBaseModel):
    catalog_id: str
    flow_id: str
    node_id: str
    catalog_path: list[str]


class CodeAgentImportGitRequest(StrictBaseModel):
    git_url: str
    source_sha: str


class CodeAgentImportArchiveRequest(StrictBaseModel):
    file_id: str = Field(..., min_length=1)


class CodeAgentCopyTreeRequest(StrictBaseModel):
    from_catalog_id: str = Field(..., min_length=1)


class CodeAgentRebuildRequest(StrictBaseModel):
    language: GuestLanguage
    invoke_kind: GuestInvokeKind
    invoke_argv: list[str]
    invoke_listen_port: int | None = None
    egress_hosts: list[str] = Field(default_factory=list)
    git_url: str | None = None
    source_sha: str | None = None


class CodeAgentNodeStatusResponse(StrictBaseModel):
    catalog_id: str
    git_url: str | None = None
    source_sha: str | None = None
    image_digest: str | None = None
    build_status: GuestBuildStatus = GuestBuildStatus.NONE
    build_error: str | None = None
    files: list[CodeAgentSourceFile] = Field(default_factory=list)


__all__ = [
    "CodeAgentCopyTreeRequest",
    "CodeAgentEnsureSourceResponse",
    "CodeAgentImportArchiveRequest",
    "CodeAgentImportGitRequest",
    "CodeAgentNodeStatusResponse",
    "CodeAgentRebuildRequest",
    "CodeAgentSourceFile",
    "GuestBuildBusyError",
    "GuestBuildStatus",
    "GuestEnsureLeaseRequest",
    "GuestEnsureLeaseResponse",
    "GuestExecutorKind",
    "GuestInvokeKind",
    "GuestLanguage",
    "GuestLease",
    "GuestLeaseCapError",
    "GuestLogLine",
    "GuestRebuildRequest",
    "GuestRebuildResponse",
    "GuestRuntime",
    "GuestRuntimeLogsResponse",
    "GuestRuntimeStatusResponse",
]
