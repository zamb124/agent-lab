"""
Traces API — OTEL-трейсы flows через Grafana Tempo.

Читает данные из Tempo HTTP API (не из platform_tracing PostgreSQL).
Ответ совместим с platform-trace-viewer: { spans: [...] } где spans — дерево.
"""

from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query

from apps.flows.src.dependencies import ContainerDep
from core.clients.tempo_client import TempoClientError
from core.logging import get_logger
from core.tracing.span_tree import build_span_tree

logger = get_logger(__name__)

router = APIRouter(tags=["Traces"])

_ATTR_SESSION_AGENT = "platform.session.agent"
_ATTR_TASK_ID = "platform.task_id"


@router.get("/session/{session_id}")
async def get_traces_by_session(
    session_id: str,
    container: ContainerDep,
    limit: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    """
    Возвращает дерево spans для сессии выполнения flow из Tempo.

    session_id — строка вида «{flow_id}:{context_id}», как хранится
    в атрибуте platform.session.agent у spans.
    """
    if not session_id:
        raise HTTPException(status_code=422, detail="session_id обязателен")
    try:
        trace_ids = await container.tempo_client.search_trace_ids_by_attribute(
            _ATTR_SESSION_AGENT, session_id, limit=limit
        )
    except TempoClientError as exc:
        logger.warning(
            "traces.session.tempo_search_failed",
            session_id=session_id,
            error=str(exc),
        )
        raise HTTPException(status_code=503, detail="Tempo недоступен") from exc

    all_spans = await _collect_spans_for_trace_ids(container, trace_ids)
    return {
        "session_id": session_id,
        "spans_count": len(all_spans),
        "spans": build_span_tree(all_spans),
    }


@router.get("/task/{task_id}")
async def get_traces_by_task(
    task_id: str,
    container: ContainerDep,
    limit: int = Query(default=10, ge=1, le=50),
) -> dict[str, Any]:
    """
    Возвращает дерево spans для A2A task_id из Tempo.
    """
    if not task_id:
        raise HTTPException(status_code=422, detail="task_id обязателен")
    try:
        trace_ids = await container.tempo_client.search_trace_ids_by_attribute(
            _ATTR_TASK_ID, task_id, limit=limit
        )
    except TempoClientError as exc:
        logger.warning(
            "traces.task.tempo_search_failed",
            task_id=task_id,
            error=str(exc),
        )
        raise HTTPException(status_code=503, detail="Tempo недоступен") from exc

    all_spans = await _collect_spans_for_trace_ids(container, trace_ids)
    return {
        "task_id": task_id,
        "spans_count": len(all_spans),
        "spans": build_span_tree(all_spans),
    }


@router.get("/trace/{trace_id}")
async def get_trace(
    trace_id: str,
    container: ContainerDep,
) -> dict[str, Any]:
    """
    Возвращает дерево spans для конкретного trace_id из Tempo.
    """
    if not trace_id:
        raise HTTPException(status_code=422, detail="trace_id обязателен")
    try:
        spans = await container.tempo_client.get_trace(trace_id)
    except TempoClientError as exc:
        logger.warning(
            "traces.trace.tempo_get_failed",
            trace_id=trace_id,
            error=str(exc),
        )
        raise HTTPException(status_code=503, detail="Tempo недоступен") from exc

    return {
        "trace_id": trace_id,
        "spans_count": len(spans),
        "spans": build_span_tree(spans),
    }


async def _collect_spans_for_trace_ids(
    container: ContainerDep,
    trace_ids: list[str],
) -> list[dict[str, Any]]:
    """Загружает spans для каждого trace_id из Tempo и объединяет в один список."""
    all_spans: list[dict[str, Any]] = []
    seen_span_ids: set[str] = set()
    for tid in trace_ids:
        try:
            spans = await container.tempo_client.get_trace(tid)
        except TempoClientError as exc:
            logger.warning(
                "traces.collect.tempo_get_failed",
                trace_id=tid,
                error=str(exc),
            )
            continue
        for span in spans:
            sid = span.get("span_id", "")
            if sid and sid not in seen_span_ids:
                seen_span_ids.add(sid)
                all_spans.append(span)
    return all_spans
