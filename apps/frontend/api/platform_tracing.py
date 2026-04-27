"""
Админ-API просмотра spans (только активная компания system).
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request

from apps.frontend.api.platform_billing import (
    _BILLING_COMPANY_LIST_CAP,
    _company_matches_billing_facet_query,
)
from apps.frontend.config import get_frontend_settings
from apps.frontend.dependencies import ContainerDep
from apps.frontend.models import (
    PlatformTracingFacetItem,
    PlatformTracingFacetItemsResponse,
    PlatformTracingFacetsResponse,
)
from core.db.repositories.company_repository import CompanyRepository
from core.db.repositories.user_repository import UserRepository
from core.identity.system_bootstrap import SYSTEM_COMPANY_ID
from core.models.identity_models import Company, User
from core.pagination import CursorPage
from core.tracing.repository import ADMIN_FACETS_MAX_LIMIT, ADMIN_SPANS_MAX_LIMIT
from core.tracing.span_tree import build_span_tree

if TYPE_CHECKING:
    from apps.frontend.container import FrontendContainer

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


_ID_SHORT_LEN = 8


def _short_id_fragment(entity_id: str) -> str:
    if len(entity_id) <= _ID_SHORT_LEN:
        return entity_id
    return f"{entity_id[:_ID_SHORT_LEN]}..."


def _company_facet_label(company_id: str, name: Optional[str]) -> str:
    if name:
        return f"{name} ({_short_id_fragment(company_id)})"
    return company_id


def _user_facet_item_label(u: Optional[User], user_id: str) -> str:
    if u is None:
        return user_id
    if u.emails:
        return f"{u.name} · {u.emails[0]}"
    return f"{u.name} ({_short_id_fragment(user_id)})"


def _user_facet_match_sort_key(frag: str, u: User) -> tuple[int, str]:
    fl = frag.strip().lower()
    if not fl:
        return (0, (u.name or "").lower())
    emails = [e.strip().lower() for e in u.emails if e and e.strip()]
    for e in emails:
        if e == fl:
            return (0, (u.name or "").lower())
    for e in emails:
        if fl in e:
            return (1, (u.name or "").lower())
    name_l = (u.name or "").lower()
    if fl in name_l:
        return (2, name_l)
    if fl in u.user_id.lower():
        return (3, name_l)
    return (4, name_l)


def _tracing_company_facet_sort_key(c: Company, frag: str) -> tuple[int, str]:
    if not frag:
        return (0, (c.name or "").lower())
    fl = frag
    cid = c.company_id.lower()
    sub = (c.subdomain or "").lower()
    if fl == cid or (sub and fl == sub):
        return (0, (c.name or "").lower())
    return (1, (c.name or "").lower())


async def _resolve_company_id_query_to_exact_match(
    container: "FrontendContainer",
    company_id_query: Optional[str],
) -> Optional[str]:
    """
    Один однозначный company_id для точного фильтра по spans: id, subdomain (хранилище),
    единственная компания по правилам billing-фасета. Иначе None — остаётся ILIKE по company_id в spans.
    """
    if company_id_query is None:
        return None
    stripped = company_id_query.strip()
    if len(stripped) < 2:
        return None
    direct = await container.company_repository.get(stripped)
    if direct is not None:
        return direct.company_id
    q_lower = stripped.lower()
    mapped_id = await container.subdomain_repository.get_company_id(q_lower)
    if mapped_id:
        return mapped_id
    companies = await container.company_repository.list(limit=_BILLING_COMPANY_LIST_CAP, offset=0)
    frag = q_lower
    matched = [c for c in companies if _company_matches_billing_facet_query(c, frag)]
    if len(matched) == 1:
        return matched[0].company_id
    return None


async def _resolve_user_id_query_to_exact_match(
    container: "FrontendContainer",
    user_id_query: Optional[str],
) -> Optional[str]:
    """
    Один user_id для точного фильтра: совпадение с id, полный email, единственный find_all_by_email_ci.
    """
    if user_id_query is None:
        return None
    stripped = user_id_query.strip()
    if len(stripped) < 2:
        return None
    u = await container.user_repository.get(stripped)
    if u is not None:
        return u.user_id
    if "@" in stripped:
        one = await container.user_repository.find_by_email(stripped)
        if one is not None:
            return one.user_id
        many = await container.user_repository.find_all_by_email_ci(stripped)
        if len(many) == 1:
            return many[0].user_id
    return None


async def _enrich_span_items(
    items: List[Dict[str, Any]],
    company_repository: CompanyRepository,
    user_repository: UserRepository,
) -> None:
    company_ids = {s["company_id"] for s in items if s.get("company_id")}
    user_ids = {s["user_id"] for s in items if s.get("user_id")}
    companies = (
        await company_repository.get_many(list(company_ids)) if company_ids else {}
    )
    users = await user_repository.get_many(list(user_ids)) if user_ids else {}
    for item in items:
        co = companies.get(item.get("company_id"))
        item["company_name"] = co.name if co else None
        u = users.get(item.get("user_id"))
        item["user_display_name"] = u.name if u else item.get("user_name")


@router.get("/facets/companies", response_model=PlatformTracingFacetItemsResponse)
async def facet_companies(
    request: Request,
    container: ContainerDep,
    q: Optional[str] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=ADMIN_FACETS_MAX_LIMIT),
) -> PlatformTracingFacetItemsResponse:
    _require_system(request)
    _require_tracing_db()
    frag = (q or "").strip().lower()

    if not frag:
        ids = await container.span_repository.admin_facet_distinct_company_ids(q=q, limit=limit)
        companies = await container.company_repository.get_many(ids) if ids else {}
        items = []
        for cid in ids:
            co = companies.get(cid)
            items.append(
                PlatformTracingFacetItem(
                    value=cid,
                    label=_company_facet_label(cid, co.name if co else None),
                )
            )
        return PlatformTracingFacetItemsResponse(items=items)

    ids_by_span_column = await container.span_repository.admin_facet_distinct_company_ids(q=q, limit=limit)
    in_tracing = set(await container.span_repository.admin_list_distinct_company_ids_in_spans(max_ids=5000))
    all_companies = await container.company_repository.list(limit=_BILLING_COMPANY_LIST_CAP, offset=0)
    meta_matched = [
        c for c in all_companies
        if c.company_id in in_tracing and _company_matches_billing_facet_query(c, frag)
    ]
    meta_matched.sort(key=lambda c: _tracing_company_facet_sort_key(c, frag))

    seen: set[str] = set()
    ordered_ids: List[str] = []
    for cid in ids_by_span_column:
        if cid not in seen and len(ordered_ids) < limit:
            seen.add(cid)
            ordered_ids.append(cid)
    for c in meta_matched:
        if c.company_id not in seen and len(ordered_ids) < limit:
            seen.add(c.company_id)
            ordered_ids.append(c.company_id)

    companies_map = await container.company_repository.get_many(ordered_ids) if ordered_ids else {}
    items = []
    for cid in ordered_ids:
        mco = companies_map.get(cid)
        items.append(
            PlatformTracingFacetItem(
                value=cid,
                label=_company_facet_label(cid, mco.name if mco else None),
            )
        )
    return PlatformTracingFacetItemsResponse(items=items)


@router.get("/facets/users", response_model=PlatformTracingFacetItemsResponse)
async def facet_users(
    request: Request,
    container: ContainerDep,
    q: Optional[str] = Query(default=None),
    company_id: Optional[str] = Query(default=None),
    namespace: Optional[str] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=ADMIN_FACETS_MAX_LIMIT),
) -> PlatformTracingFacetItemsResponse:
    _require_system(request)
    _require_tracing_db()
    frag = (q or "").strip().lower()

    if not frag:
        ids = await container.span_repository.admin_facet_distinct_user_ids(
            q=q,
            company_id=company_id,
            namespace=namespace,
            limit=limit,
        )
        users_map = await container.user_repository.get_many(ids) if ids else {}
        items = [
            PlatformTracingFacetItem(
                value=uid,
                label=_user_facet_item_label(users_map.get(uid), uid),
            )
            for uid in ids
        ]
        return PlatformTracingFacetItemsResponse(items=items)

    ids_by_span = await container.span_repository.admin_facet_distinct_user_ids(
        q=q,
        company_id=company_id,
        namespace=namespace,
        limit=limit,
    )
    in_tracing = set(
        await container.span_repository.admin_list_distinct_user_ids_in_spans(
            max_ids=5000,
            company_id=company_id,
            namespace=namespace,
        )
    )
    search_hits = await container.user_repository.search_by_query(frag, limit=200)
    meta = [u for u in search_hits if u.user_id in in_tracing]
    meta.sort(key=lambda u: _user_facet_match_sort_key(frag, u))

    seen: set[str] = set()
    ordered_ids: List[str] = []
    for u in meta:
        if u.user_id not in seen and len(ordered_ids) < limit:
            seen.add(u.user_id)
            ordered_ids.append(u.user_id)
    for uid in ids_by_span:
        if uid not in seen and len(ordered_ids) < limit:
            seen.add(uid)
            ordered_ids.append(uid)

    users_map = await container.user_repository.get_many(ordered_ids) if ordered_ids else {}
    items = [
        PlatformTracingFacetItem(
            value=uid,
            label=_user_facet_item_label(users_map.get(uid), uid),
        )
        for uid in ordered_ids
    ]
    return PlatformTracingFacetItemsResponse(items=items)


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


@router.get("/spans", response_model=CursorPage[dict])
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
) -> CursorPage[dict]:
    _require_system(request)
    _require_tracing_db()
    company_id_for_search = company_id
    company_id_query_for_search = company_id_query
    if company_id is None and company_id_query is not None:
        resolved = await _resolve_company_id_query_to_exact_match(container, company_id_query)
        if resolved is not None:
            company_id_for_search = resolved
            company_id_query_for_search = None
    user_id_for_search = user_id
    user_id_query_for_search = user_id_query
    if user_id is None and user_id_query is not None:
        resolved_u = await _resolve_user_id_query_to_exact_match(container, user_id_query)
        if resolved_u is not None:
            user_id_for_search = resolved_u
            user_id_query_for_search = None
    try:
        items, next_cursor = await container.span_repository.admin_search_spans(
            service_name=service_name,
            company_id=company_id_for_search,
            user_id=user_id_for_search,
            namespace=namespace,
            from_time=from_time,
            to_time=to_time,
            company_id_query=company_id_query_for_search,
            user_id_query=user_id_query_for_search,
            operation_name_query=operation_name_query,
            event_type_query=event_type_query,
            namespace_query=namespace_query,
            service_name_query=service_name_query,
            limit=limit,
            cursor=cursor,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    await _enrich_span_items(items, container.company_repository, container.user_repository)
    return CursorPage[dict](items=items, next_cursor=next_cursor, has_more=next_cursor is not None)


@router.get("/traces/{trace_id}")
async def get_trace_tree(
    trace_id: str,
    request: Request,
    container: ContainerDep,
) -> Dict[str, Any]:
    _require_system(request)
    _require_tracing_db()
    spans = await container.span_repository.get_trace(trace_id)
    await _enrich_span_items(spans, container.company_repository, container.user_repository)
    tree = build_span_tree(spans)
    return {
        "trace_id": trace_id,
        "spans_count": len(spans),
        "tree": tree,
    }
