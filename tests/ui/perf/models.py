"""Typed модели отчёта UI E2E perf-collector."""

from __future__ import annotations

from pydantic import BaseModel, Field


class UiPerfRequest(BaseModel):
    method: str
    url: str
    path: str
    service_prefix: str
    status: int | None
    resource_type: str
    duration_ms: float | None
    transfer_size: int | None
    failed: bool = False
    failure_text: str | None = None


class UiPerfNavigation(BaseModel):
    url: str
    response_start_ms: float | None
    dom_content_loaded_ms: float | None
    load_ms: float | None
    transfer_size: int | None


class UiPerfLongTask(BaseModel):
    duration_ms: float
    start_time_ms: float
    name: str


class UiPerfTestReport(BaseModel):
    nodeid: str
    worker_id: str
    wall_ms: float
    request_count: int
    unique_paths: int
    error_4xx_count: int
    error_5xx_count: int
    failed_request_count: int
    long_task_count: int
    long_task_total_ms: float
    long_task_max_ms: float
    requests: list[UiPerfRequest] = Field(default_factory=list)
    slowest_requests: list[UiPerfRequest] = Field(default_factory=list)
    navigations: list[UiPerfNavigation] = Field(default_factory=list)
    long_tasks: list[UiPerfLongTask] = Field(default_factory=list)
