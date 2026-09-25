"""Контракт фермы code_agent: GuestRuntime 1:1 с (flow_id, node_id), GuestLease, дерево файлов."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import ClassVar, Self, override

from oxyde import Field as DbField
from pydantic import ConfigDict, Field, field_validator

from core.documents.placement_paths import validate_relative_dir
from core.errors.boundary import PlatformConflictError
from core.guest_runtime.env import (
    GUEST_IDLE_TTL_MAX,
    GUEST_IDLE_TTL_MIN,
    validate_guest_env,
)
from core.models.base import StrictBaseModel
from core.models.platform_model import PlatformModel


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


def guest_runtime_id(flow_id: str, node_id: str) -> str:
    return f"{flow_id}:{node_id}"


class GuestRuntime(PlatformModel):
    """Слот code_agent. Глобальная таблица ``guest_runtimes`` в ``platform_shared``.

    Адрес — ``guest_runtime_id`` = ``{flow_id}:{node_id}``. ``company_id`` — колонка.
    Живой контейнер — ``GuestLease`` в Redis, не эта таблица.
    """

    __database_alias__: ClassVar[str | None] = "shared"
    __global_model__: ClassVar[bool] = True
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", validate_assignment=True)

    guest_runtime_id: str = DbField(db_pk=True, min_length=1)

    class Meta:
        is_table: bool = True
        table_name: str = "guest_runtimes"
        unique_together: list[tuple[str, str]] = [("flow_id", "node_id")]

    flow_id: str = DbField(min_length=1, db_index=True)
    node_id: str = DbField(min_length=1, db_index=True)
    company_id: str = DbField(min_length=1, db_index=True)
    catalog_id: str = DbField(min_length=1)
    language: GuestLanguage
    invoke_kind: GuestInvokeKind
    invoke_argv: list[str] = DbField(default_factory=list)
    invoke_listen_port: int | None = DbField(default=None, ge=1, le=65535)
    egress_hosts: list[str] = DbField(default_factory=list)
    git_url: str | None = DbField(default=None, db_type="TEXT")
    source_sha: str | None = DbField(default=None)
    image_digest: str | None = DbField(default=None, db_type="TEXT")
    image_bytes: int | None = DbField(default=None, ge=0)
    build_status: GuestBuildStatus = DbField(default=GuestBuildStatus.NONE, db_index=True)
    build_error: str | None = DbField(default=None, db_type="TEXT")
    updated_at: datetime = DbField(default_factory=lambda: datetime.now(timezone.utc))

    @override
    async def pre_save(self, *, is_create: bool, update_fields: set[str] | None = None) -> None:
        _ = is_create, update_fields
        self.updated_at = datetime.now(timezone.utc)

    @classmethod
    async def company_guest_runtimes(cls, company_id: str) -> list[Self]:
        return await cls.objects.filter(company_id=company_id).all()


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
    idle_ttl_seconds: int | None = Field(default=None, ge=GUEST_IDLE_TTL_MIN, le=GUEST_IDLE_TTL_MAX)
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


class GuestLeaseCapError(PlatformConflictError):
    """Company or cluster lease cap exceeded."""


class GuestBuildBusyError(PlatformConflictError):
    """Cluster already has a guest image build in progress."""


class GuestRuntimeUnavailableError(Exception):
    """Farm HTTP is unreachable (guest_runtime process down)."""


class CodeAgentEnsureSourceResponse(StrictBaseModel):
    catalog_id: str
    flow_id: str
    node_id: str
    catalog_path: list[str]


class CodeAgentNodeRefPayload(StrictBaseModel):
    flow_id: str = ""
    node_id: str = ""
    branch_id: str = "default"


class CodeAgentLogsPayload(CodeAgentNodeRefPayload):
    task_id: str | None = None
    session_id: str | None = None
    context_id: str | None = None


class CodeAgentDeletePayload(CodeAgentNodeRefPayload):
    catalog_id: str | None = None


class CodeAgentImportGitRequest(CodeAgentNodeRefPayload):
    git_url: str
    source_sha: str


class CodeAgentImportArchiveRequest(CodeAgentNodeRefPayload):
    file_id: str = Field(..., min_length=1)


class CodeAgentCopyTreeRequest(CodeAgentNodeRefPayload):
    from_catalog_id: str = Field(..., min_length=1)


class CodeAgentRebuildRequest(CodeAgentNodeRefPayload):
    language: GuestLanguage
    invoke_kind: GuestInvokeKind
    invoke_argv: list[str]
    invoke_listen_port: int | None = None
    egress_hosts: list[str] = Field(default_factory=list)
    git_url: str | None = None
    source_sha: str | None = None

    @field_validator("git_url", "source_sha", mode="before")
    @classmethod
    def _blank_git_field(cls, value: object) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("git_url/source_sha must be string or null")
        if value == "":
            return None
        return value


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
    "CodeAgentDeletePayload",
    "CodeAgentEnsureSourceResponse",
    "CodeAgentImportArchiveRequest",
    "CodeAgentImportGitRequest",
    "CodeAgentLogsPayload",
    "CodeAgentNodeRefPayload",
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
    "GuestRuntimeUnavailableError",
]
