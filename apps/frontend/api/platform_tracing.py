"""
Админ-API просмотра spans (только активная компания system).
"""

from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query, Request

from apps.frontend.config import get_frontend_settings
from apps.frontend.dependencies import ContainerDep
from apps.frontend.models import PlatformTracingFacetsResponse, PlatformTracingSpansPageResponse
from core.identity.system_bootstrap import SYSTEM_COMPANY_ID
from core.tracing.repository import ADMIN_FACETS_MAX_LIMIT, ADMIN_SPANS_MAX_LIMIT
from core.tracing.span_tree import build_span_tree

router = APIRouter(prefix="/api/platform-tracing", tags=["platform-tracing"])


def _require_system(request: Request) -> None:
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Необходима авторизация")
    company = getattr(request.state, "company", None)
    if not company or company.company_id != SYSTEM_COMPANY_ID:
        raise HTTPException(status_code=403, detail="Доступно только для компании system")


def _require_tracing_db() -> None:
    settings = get_frontend_settings()
    if not settings.database.tracing_url or not settings.tracing.postgres_enabled:
        raise HTTPException(
            status_code=503,
            detail="Персистентный трейсинг в PostgreSQL выключен или не настроен (DATABASE__TRACING_URL).",
        )


@router.get("/facets/companies", response_model=PlatformTracingFacetsResponse)
async def facet_companies(
    request: Request,
    container: ContainerDep,
    q: Optional[str] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=ADMIN_FACETS_MAX_LIMIT),
) -> PlatformTracingFacetsResponse:
    _require_system(request)
    _require_tracing_db()
    items = await container.span_repository.admin_facet_distinct_company_ids(q=q, limit=limit)
    return PlatformTracingFacetsResponse(items=items)


@router.get("/facets/users", response_model=PlatformTracingFacetsResponse)
async def facet_users(
    request: Request,
    container: ContainerDep,
    q: Optional[str] = Query(default=None),
    company_id: Optional[str] = Query(default=None),
    namespace: Optional[str] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=ADMIN_FACETS_MAX_LIMIT),
) -> PlatformTracingFacetsResponse:
    _require_system(request)
    _require_tracing_db()
    items = await container.span_repository.admin_facet_distinct_user_ids(
        q=q,
        company_id=company_id,
        namespace=namespace,
        limit=limit,
    )
    return PlatformTracingFacetsResponse(items=items)


@router.get("/facets/services", response_model=PlatformTracingFacetsResponse)
async def facet_services(
    request: Request,
    container: ContainerDep,
    q: Optional[str] = Query(default=None),
    company_id: Optional[str] = Query(default=None),
    namespace: Optional[str] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=ADMIN_FACETS_MAX_LIMIT),
) -> PlatformTracingFacetsResponse:
    _require_system(request)
    _require_tracing_db()
    items = await container.span_repository.admin_facet_distinct_service_names(
        q=q,
        company_id=company_id,
        namespace=namespace,
        limit=limit,
    )
    return PlatformTracingFacetsResponse(items=items)


@router.get("/facets/event-types", response_model=PlatformTracingFacetsResponse)
async def facet_event_types(
    request: Request,
    container: ContainerDep,
    q: Optional[str] = Query(default=None),
    company_id: Optional[str] = Query(default=None),
    namespace: Optional[str] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=ADMIN_FACETS_MAX_LIMIT),
) -> PlatformTracingFacetsResponse:
    _require_system(request)
    _require_tracing_db()
    items = await container.span_repository.admin_facet_distinct_event_types(
        q=q,
        company_id=company_id,
        namespace=namespace,
        limit=limit,
    )
    return PlatformTracingFacetsResponse(items=items)


@router.get("/facets/namespaces", response_model=PlatformTracingFacetsResponse)
async def facet_namespaces(
    request: Request,
    container: ContainerDep,
    q: Optional[str] = Query(default=None),
    company_id: Optional[str] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=ADMIN_FACETS_MAX_LIMIT),
) -> PlatformTracingFacetsResponse:
    _require_system(request)
    _require_tracing_db()
    items = await container.span_repository.admin_facet_distinct_namespaces(
        q=q,
        company_id=company_id,
        limit=limit,
    )
    return PlatformTracingFacetsResponse(items=items)


@router.get("/facets/operations", response_model=PlatformTracingFacetsResponse)
async def facet_operations(
    request: Request,
    container: ContainerDep,
    q: Optional[str] = Query(default=None),
    company_id: Optional[str] = Query(default=None),
    namespace: Optional[str] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=ADMIN_FACETS_MAX_LIMIT),
) -> PlatformTracingFacetsResponse:
    _require_system(request)
    _require_tracing_db()
    items = await container.span_repository.admin_facet_distinct_operation_names(
        q=q,
        company_id=company_id,
        namespace=namespace,
        limit=limit,
    )
    return PlatformTracingFacetsResponse(items=items)


@router.get("/spans", response_model=PlatformTracingSpansPageResponse)
async def list_spans(
    request: Request,
    container: ContainerDep,
    service_name: Optional[str] = Query(default=None),
    company_id: Optional[str] = Query(default=None),
    user_id: Optional[str] = Query(default=None),
    namespace: Optional[str] = Query(default=None),
    from_time: Optional[datetime] = Query(default=None),
    to_time: Optional[datetime] = Query(default=None),
    company_id_query: Optional[str] = Query(default=None),
    user_id_query: Optional[str] = Query(default=None),
    operation_name_query: Optional[str] = Query(default=None),
    event_type_query: Optional[str] = Query(default=None),
    namespace_query: Optional[str] = Query(default=None),
    service_name_query: Optional[str] = Query(default=None),
    cursor: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=ADMIN_SPANS_MAX_LIMIT),
) -> PlatformTracingSpansPageResponse:
    _require_system(request)
    _require_tracing_db()
    try:
        items, next_cursor = await container.span_repository.admin_search_spans(
            service_name=service_name,
            company_id=company_id,
            user_id=user_id,
            namespace=namespace,
            from_time=from_time,
            to_time=to_time,
            company_id_query=company_id_query,
            user_id_query=user_id_query,
            operation_name_query=operation_name_query,
            event_type_query=event_type_query,
            namespace_query=namespace_query,
            service_name_query=service_name_query,
            limit=limit,
            cursor=cursor,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return PlatformTracingSpansPageResponse(items=items, next_cursor=next_cursor)


@router.get("/traces/{trace_id}")
async def get_trace_tree(
    trace_id: str,
    request: Request,
    container: ContainerDep,
) -> Dict[str, Any]:
    _require_system(request)
    _require_tracing_db()
    spans = await container.span_repository.get_trace(trace_id)
    tree = build_span_tree(spans)
    return {
        "trace_id": trace_id,
        "spans_count": len(spans),
        "tree": tree,
    }
