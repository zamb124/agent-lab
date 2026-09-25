"""REST-зеркало команд `frontend/platform_tracing/*` (админка spans, только компания system)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query

from apps.frontend.di import Di
from apps.frontend.models import (
    PlatformTracingFacetItemsResponse,
    PlatformTracingFacetsResponse,
    PlatformTracingSpanItem,
)
from apps.frontend.realtime.platform_tracing_operations import (
    TracingFacetPayload,
    TracingSpansPayload,
    TracingTraceIdPayload,
    TracingTraceTree,
    op_platform_tracing_facet_companies,
    op_platform_tracing_facet_event_types,
    op_platform_tracing_facet_namespaces,
    op_platform_tracing_facet_operations,
    op_platform_tracing_facet_services,
    op_platform_tracing_facet_users,
    op_platform_tracing_spans,
    op_platform_tracing_trace_tree,
)
from core.context import require_context
from core.pagination import CursorPage
from core.tracing.facet_query import ADMIN_FACETS_MAX_LIMIT
from core.tracing.models import ADMIN_SPANS_MAX_LIMIT

router = APIRouter(prefix="/api/platform-tracing", tags=["platform-tracing"])

FacetQuery = Annotated[str | None, Query()]
FacetLimit = Annotated[int, Query(ge=1, le=ADMIN_FACETS_MAX_LIMIT)]


@router.get("/facets/companies", response_model=PlatformTracingFacetItemsResponse)
async def facet_companies(
    di: Di, q: FacetQuery = None, limit: FacetLimit = 20
) -> PlatformTracingFacetItemsResponse:
    return await op_platform_tracing_facet_companies(
        TracingFacetPayload(q=q, limit=limit), user=require_context().user, di=di
    )


@router.get("/facets/users", response_model=PlatformTracingFacetItemsResponse)
async def facet_users(
    di: Di,
    q: FacetQuery = None,
    company_id: FacetQuery = None,
    namespace: FacetQuery = None,
    limit: FacetLimit = 20,
) -> PlatformTracingFacetItemsResponse:
    return await op_platform_tracing_facet_users(
        TracingFacetPayload(q=q, company_id=company_id, namespace=namespace, limit=limit),
        user=require_context().user,
        di=di,
    )


@router.get("/facets/services", response_model=PlatformTracingFacetsResponse)
async def facet_services(
    di: Di,
    q: FacetQuery = None,
    company_id: FacetQuery = None,
    namespace: FacetQuery = None,
    limit: FacetLimit = 20,
) -> PlatformTracingFacetsResponse:
    return await op_platform_tracing_facet_services(
        TracingFacetPayload(q=q, company_id=company_id, namespace=namespace, limit=limit),
        user=require_context().user,
        di=di,
    )


@router.get("/facets/event-types", response_model=PlatformTracingFacetsResponse)
async def facet_event_types(
    di: Di,
    q: FacetQuery = None,
    company_id: FacetQuery = None,
    namespace: FacetQuery = None,
    limit: FacetLimit = 20,
) -> PlatformTracingFacetsResponse:
    return await op_platform_tracing_facet_event_types(
        TracingFacetPayload(q=q, company_id=company_id, namespace=namespace, limit=limit),
        user=require_context().user,
        di=di,
    )


@router.get("/facets/namespaces", response_model=PlatformTracingFacetsResponse)
async def facet_namespaces(
    di: Di, q: FacetQuery = None, company_id: FacetQuery = None, limit: FacetLimit = 20
) -> PlatformTracingFacetsResponse:
    return await op_platform_tracing_facet_namespaces(
        TracingFacetPayload(q=q, company_id=company_id, limit=limit),
        user=require_context().user,
        di=di,
    )


@router.get("/facets/operations", response_model=PlatformTracingFacetsResponse)
async def facet_operations(
    di: Di,
    q: FacetQuery = None,
    company_id: FacetQuery = None,
    namespace: FacetQuery = None,
    limit: FacetLimit = 20,
) -> PlatformTracingFacetsResponse:
    return await op_platform_tracing_facet_operations(
        TracingFacetPayload(q=q, company_id=company_id, namespace=namespace, limit=limit),
        user=require_context().user,
        di=di,
    )


@router.get("/spans", response_model=CursorPage[PlatformTracingSpanItem])
async def list_spans(
    di: Di,
    service_name: FacetQuery = None,
    company_id: FacetQuery = None,
    user_id: FacetQuery = None,
    namespace: FacetQuery = None,
    from_time: Annotated[datetime | None, Query()] = None,
    to_time: Annotated[datetime | None, Query()] = None,
    company_id_query: FacetQuery = None,
    user_id_query: FacetQuery = None,
    operation_name_query: FacetQuery = None,
    event_type_query: FacetQuery = None,
    namespace_query: FacetQuery = None,
    service_name_query: FacetQuery = None,
    cursor: FacetQuery = None,
    limit: Annotated[int, Query(ge=1, le=ADMIN_SPANS_MAX_LIMIT)] = 50,
) -> CursorPage[PlatformTracingSpanItem]:
    return await op_platform_tracing_spans(
        TracingSpansPayload(
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
            cursor=cursor,
            limit=limit,
        ),
        user=require_context().user,
        di=di,
    )


@router.get("/traces/{trace_id}", response_model=TracingTraceTree)
async def get_trace_tree(trace_id: str, di: Di) -> TracingTraceTree:
    return await op_platform_tracing_trace_tree(
        TracingTraceIdPayload(trace_id=trace_id), user=require_context().user, di=di
    )
