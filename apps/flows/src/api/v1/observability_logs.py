"""
Logs API — поиск логов flows из Grafana Loki.

Поддерживает только whitelist-шаблоны (по trace_id и session_id).
Произвольный LogQL от клиента не принимается.
"""

from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query

from apps.flows.src.dependencies import ContainerDep
from core.clients.loki_client import LokiClientError
from core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["ObservabilityLogs"])

_MAX_LIMIT = 500
_DEFAULT_LIMIT = 200


def _validate_limit(limit: int) -> int:
    if limit < 1:
        raise HTTPException(status_code=422, detail="limit должен быть >= 1")
    if limit > _MAX_LIMIT:
        raise HTTPException(status_code=422, detail=f"limit не может превышать {_MAX_LIMIT}")
    return limit


def _require_loki(container: ContainerDep) -> Any:
    client = container.loki_client
    if client is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "Loki query API не настроен: задайте logging.loki_query_url "
                "или logging.loki_url (push; база для query берётся из scheme://netloc)"
            ),
        )
    return client


@router.get("/by-trace/{trace_id}")
async def get_logs_by_trace_id(
    trace_id: str,
    container: ContainerDep,
    limit: int = Query(default=_DEFAULT_LIMIT, ge=1, le=_MAX_LIMIT),
    time_from: Optional[datetime] = Query(default=None, description="Начало интервала (UTC ISO 8601)"),
    time_to: Optional[datetime] = Query(default=None, description="Конец интервала (UTC ISO 8601)"),
) -> dict[str, Any]:
    """
    Возвращает записи логов для trace_id из flows/flows_worker.

    Поиск выполняется в Loki с фильтром trace_id по whitelist LogQL-шаблону.
    """
    if not trace_id:
        raise HTTPException(status_code=422, detail="trace_id обязателен")
    _validate_limit(limit)
    loki = _require_loki(container)
    try:
        entries = await loki.query_by_trace_id(
            trace_id, time_from=time_from, time_to=time_to, limit=limit
        )
    except LokiClientError as exc:
        logger.warning(
            "observability_logs.by_trace.loki_error",
            trace_id=trace_id,
            error=str(exc),
        )
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return {
        "trace_id": trace_id,
        "count": len(entries),
        "entries": entries,
    }


@router.get("/by-session/{session_id}")
async def get_logs_by_session_id(
    session_id: str,
    container: ContainerDep,
    limit: int = Query(default=_DEFAULT_LIMIT, ge=1, le=_MAX_LIMIT),
    time_from: Optional[datetime] = Query(default=None, description="Начало интервала (UTC ISO 8601)"),
    time_to: Optional[datetime] = Query(default=None, description="Конец интервала (UTC ISO 8601)"),
) -> dict[str, Any]:
    """
    Возвращает записи логов для session_id из flows/flows_worker.

    Поиск выполняется в Loki с фильтром session_agent (flow_id:context_id), см. LOG_SESSION_AGENT.
    """
    if not session_id:
        raise HTTPException(status_code=422, detail="session_id обязателен")
    _validate_limit(limit)
    loki = _require_loki(container)
    try:
        entries = await loki.query_by_session_id(
            session_id, time_from=time_from, time_to=time_to, limit=limit
        )
    except LokiClientError as exc:
        logger.warning(
            "observability_logs.by_session.loki_error",
            session_id=session_id,
            error=str(exc),
        )
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return {
        "session_id": session_id,
        "count": len(entries),
        "entries": entries,
    }
