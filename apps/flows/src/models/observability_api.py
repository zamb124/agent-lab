"""Контракт Loki/Tempo observability: один payload на REST и WS."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from core.clients.loki_client import LokiLogEntry
from core.models.base import StrictBaseModel
from core.tracing.models import TraceSearchResult
from core.types import JsonObject


class ObservabilityLogsQueryPayload(StrictBaseModel):
    limit: int = Field(default=200, ge=1, le=500)
    time_from: datetime | None = None
    time_to: datetime | None = None
    trace_id: str = ""
    session_id: str = ""
    request_id: str = ""
    span_id: str = ""
    user_id: str = ""


class ObservabilityLogsResponse(StrictBaseModel):
    count: int
    entries: list[LokiLogEntry]
    trace_id: str = ""
    session_id: str = ""
    request_id: str = ""
    span_id: str = ""
    user_id: str = ""


class ObservabilityTraceSearchPayload(StrictBaseModel):
    flow_id: str | None = None
    task_id: str | None = None
    limit: int = Field(default=20, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class ObservabilityTraceSearchResponse(StrictBaseModel):
    traces_count: int
    traces: list[TraceSearchResult]


class ObservabilityTraceQueryPayload(StrictBaseModel):
    session_id: str = ""
    task_id: str = ""
    trace_id: str = ""
    parent_session_id: str = ""
    limit: int = Field(default=20, ge=1, le=100)


class ObservabilityTraceTreeResponse(StrictBaseModel):
    spans_count: int
    spans: list[JsonObject]
    session_id: str = ""
    task_id: str = ""
    trace_id: str = ""
    parent_session_id: str = ""
    handoff_depth: int | None = None
