"""
Logs API — поиск логов flows из Grafana Loki.

Поддерживает только whitelist-шаблоны: trace_id, session_id (session_agent),
request_id, span_id, user_id. Произвольный LogQL от клиента не принимается.
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from apps.flows.src.dependencies import ContainerDep
from core.clients.loki_client import LokiClient, LokiClientError, LokiLogEntry
from core.logging import get_logger
from core.types import JsonObject, parse_json_object

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


def _require_loki(container: ContainerDep) -> LokiClient:
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


def _entry_to_json(entry: LokiLogEntry) -> JsonObject:
    return parse_json_object(entry.model_dump_json(), "loki.entry")


def _logs_response(key: str, value: str, entries: list[LokiLogEntry]) -> JsonObject:
    return {
        key: value,
        "count": len(entries),
        "entries": [_entry_to_json(entry) for entry in entries],
    }


@router.get("/by-trace/{trace_id}")
async def get_logs_by_trace_id(
    trace_id: str,
    container: ContainerDep,
    limit: Annotated[int, Query(ge=1, le=_MAX_LIMIT)] = _DEFAULT_LIMIT,
    time_from: Annotated[datetime | None, Query(description="Начало интервала (UTC ISO 8601)")] = None,
    time_to: Annotated[datetime | None, Query(description="Конец интервала (UTC ISO 8601)")] = None,
) -> JsonObject:
    """
    Возвращает записи логов для trace_id из flows/flows_worker.

    Поиск выполняется в Loki с фильтром trace_id по whitelist LogQL-шаблону.
    """
    if not trace_id:
        raise HTTPException(status_code=422, detail="trace_id обязателен")
    limit = _validate_limit(limit)
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

    return _logs_response("trace_id", trace_id, entries)


@router.get("/by-session/{session_id}")
async def get_logs_by_session_id(
    session_id: str,
    container: ContainerDep,
    limit: Annotated[int, Query(ge=1, le=_MAX_LIMIT)] = _DEFAULT_LIMIT,
    time_from: Annotated[datetime | None, Query(description="Начало интервала (UTC ISO 8601)")] = None,
    time_to: Annotated[datetime | None, Query(description="Конец интервала (UTC ISO 8601)")] = None,
) -> JsonObject:
    """
    Возвращает записи логов для session_id из flows/flows_worker.

    Поиск выполняется в Loki с фильтром session_agent (flow_id:context_id), см. LOG_SESSION_AGENT.
    """
    if not session_id:
        raise HTTPException(status_code=422, detail="session_id обязателен")
    limit = _validate_limit(limit)
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

    return _logs_response("session_id", session_id, entries)


@router.get("/by-request/{request_id}")
async def get_logs_by_request_id(
    request_id: str,
    container: ContainerDep,
    limit: Annotated[int, Query(ge=1, le=_MAX_LIMIT)] = _DEFAULT_LIMIT,
    time_from: Annotated[datetime | None, Query(description="Начало интервала (UTC ISO 8601)")] = None,
    time_to: Annotated[datetime | None, Query(description="Конец интервала (UTC ISO 8601)")] = None,
) -> JsonObject:
    """
    Возвращает записи логов для request_id из flows/flows_worker (поле request_id в JSON).
    """
    if not request_id:
        raise HTTPException(status_code=422, detail="request_id обязателен")
    limit = _validate_limit(limit)
    loki = _require_loki(container)
    try:
        entries = await loki.query_by_request_id(
            request_id, time_from=time_from, time_to=time_to, limit=limit
        )
    except LokiClientError as exc:
        logger.warning(
            "observability_logs.by_request.loki_error",
            request_id=request_id,
            error=str(exc),
        )
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return _logs_response("request_id", request_id, entries)


@router.get("/by-span/{span_id}")
async def get_logs_by_span_id(
    span_id: str,
    container: ContainerDep,
    limit: Annotated[int, Query(ge=1, le=_MAX_LIMIT)] = _DEFAULT_LIMIT,
    time_from: Annotated[datetime | None, Query(description="Начало интервала (UTC ISO 8601)")] = None,
    time_to: Annotated[datetime | None, Query(description="Конец интервала (UTC ISO 8601)")] = None,
) -> JsonObject:
    """
    Возвращает записи логов для span_id из flows/flows_worker (поле span_id в JSON).
    """
    if not span_id:
        raise HTTPException(status_code=422, detail="span_id обязателен")
    limit = _validate_limit(limit)
    loki = _require_loki(container)
    try:
        entries = await loki.query_by_span_id(
            span_id, time_from=time_from, time_to=time_to, limit=limit
        )
    except LokiClientError as exc:
        logger.warning(
            "observability_logs.by_span.loki_error",
            span_id=span_id,
            error=str(exc),
        )
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return _logs_response("span_id", span_id, entries)


@router.get("/by-user/{user_id}")
async def get_logs_by_user_id(
    user_id: str,
    container: ContainerDep,
    limit: Annotated[int, Query(ge=1, le=_MAX_LIMIT)] = _DEFAULT_LIMIT,
    time_from: Annotated[datetime | None, Query(description="Начало интервала (UTC ISO 8601)")] = None,
    time_to: Annotated[datetime | None, Query(description="Конец интервала (UTC ISO 8601)")] = None,
) -> JsonObject:
    """
    Возвращает записи логов для user_id из flows/flows_worker (поле user_id в JSON).
    """
    if not user_id:
        raise HTTPException(status_code=422, detail="user_id обязателен")
    limit = _validate_limit(limit)
    loki = _require_loki(container)
    try:
        entries = await loki.query_by_user_id(
            user_id, time_from=time_from, time_to=time_to, limit=limit
        )
    except LokiClientError as exc:
        logger.warning(
            "observability_logs.by_user.loki_error",
            user_id=user_id,
            error=str(exc),
        )
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return _logs_response("user_id", user_id, entries)
