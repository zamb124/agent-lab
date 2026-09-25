"""Команды админки трейсинга (только компания system): фасеты, поиск spans, дерево trace."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from apps.frontend.config import get_frontend_settings
from apps.frontend.di import Di
from apps.frontend.models import (
    PlatformTracingFacetItem,
    PlatformTracingFacetItemsResponse,
    PlatformTracingFacetsResponse,
    PlatformTracingSpanItem,
)
from apps.frontend.realtime.platform_billing_operations import (
    BILLING_COMPANY_LIST_CAP,
    company_matches_billing_facet_query,
)
from core.errors.boundary import PlatformUnavailableError
from core.models import StrictBaseModel
from core.models.identity_models import Company, User
from core.pagination import CursorPage
from core.request_scope import require_system_admin
from core.tracing.facet_query import ADMIN_FACETS_MAX_LIMIT
from core.tracing.models import ADMIN_SPANS_MAX_LIMIT, Span
from core.tracing.span_tree import build_span_tree
from core.types import JsonObject
from core.websocket import raise_invalid

_ID_SHORT_LEN = 8


class TracingFacetPayload(StrictBaseModel):
    q: str | None = None
    company_id: str | None = None
    namespace: str | None = None
    limit: int = Field(default=20, ge=1, le=ADMIN_FACETS_MAX_LIMIT)


class TracingSpansPayload(StrictBaseModel):
    service_name: str | None = None
    company_id: str | None = None
    user_id: str | None = None
    namespace: str | None = None
    from_time: datetime | None = None
    to_time: datetime | None = None
    company_id_query: str | None = None
    user_id_query: str | None = None
    operation_name_query: str | None = None
    event_type_query: str | None = None
    namespace_query: str | None = None
    service_name_query: str | None = None
    cursor: str | None = None
    limit: int = Field(default=50, ge=1, le=ADMIN_SPANS_MAX_LIMIT)


class TracingTraceIdPayload(StrictBaseModel):
    trace_id: str = Field(min_length=1)


class TracingTraceTree(StrictBaseModel):
    trace_id: str
    spans_count: int
    tree: list[JsonObject]


async def _require_tracing_admin(di: Di) -> None:
    _ = await require_system_admin(di.authz_service)
    settings = get_frontend_settings()
    if not settings.database.tracing_url or not settings.tracing.postgres_enabled:
        raise PlatformUnavailableError(
            "Persistent tracing in PostgreSQL is disabled or not configured (DATABASE__TRACING_URL).", error_code='unavailable'
        )


def _short_id_fragment(entity_id: str) -> str:
    if len(entity_id) <= _ID_SHORT_LEN:
        return entity_id
    return f"{entity_id[:_ID_SHORT_LEN]}..."


def _company_facet_label(company_id: str, name: str | None) -> str:
    if name:
        return f"{name} ({_short_id_fragment(company_id)})"
    return company_id


async def _companies_for_facet_query(
    frag: str,
) -> list[Company]:
    found: list[Company] = []
    by_subdomain = await Company.by_subdomain(frag)
    if by_subdomain is not None:
        found.append(by_subdomain)
    by_id = await Company.get(frag)
    if by_id is not None and all(item.company_id != by_id.company_id for item in found):
        found.append(by_id)
    return found


def _user_facet_item_label(user: User | None, user_id: str) -> str:
    if user is None:
        return user_id
    if user.emails:
        return f"{user.name} · {user.emails[0]}"
    return f"{user.name} ({_short_id_fragment(user_id)})"


def _user_facet_match_sort_key(frag: str, user: User) -> tuple[int, str]:
    frag_lower = frag.strip().lower()
    name_lower = (user.name or "").lower()
    if not frag_lower:
        return (0, name_lower)
    emails = [email.strip().lower() for email in user.emails if email and email.strip()]
    if any(email == frag_lower for email in emails):
        return (0, name_lower)
    if any(frag_lower in email for email in emails):
        return (1, name_lower)
    if frag_lower in name_lower:
        return (2, name_lower)
    if frag_lower in user.user_id.lower():
        return (3, name_lower)
    return (4, name_lower)


def _tracing_company_facet_sort_key(company: Company, frag: str) -> tuple[int, str]:
    name_lower = (company.name or "").lower()
    if not frag:
        return (0, name_lower)
    sub = (company.subdomain or "").lower()
    if frag == company.company_id.lower() or (sub and frag == sub):
        return (0, name_lower)
    return (1, name_lower)


async def _resolve_company_id_query_to_exact_match(
    company_id_query: str | None
) -> str | None:
    """Однозначный company_id для точного фильтра: id, subdomain или единственное совпадение по фасету."""
    if company_id_query is None:
        return None
    stripped = company_id_query.strip()
    if len(stripped) < 2:
        return None
    direct = await Company.get(stripped)
    if direct is not None:
        return direct.company_id
    q_lower = stripped.lower()
    mapped = await Company.by_subdomain(q_lower)
    if mapped is not None:
        return mapped.company_id
    companies = await Company.list(limit=BILLING_COMPANY_LIST_CAP, offset=0)
    matched = [company for company in companies if company_matches_billing_facet_query(company, q_lower)]
    if len(matched) == 1:
        return matched[0].company_id
    return None


async def _resolve_user_id_query_to_exact_match(
    user_id_query: str | None
) -> str | None:
    """Один user_id для точного фильтра: id, полный email или единственное совпадение по email."""
    if user_id_query is None:
        return None
    stripped = user_id_query.strip()
    if len(stripped) < 2:
        return None
    user = await User.get(stripped)
    if user is not None:
        return user.user_id
    if "@" in stripped:
        one = await User.find_by_email(stripped)
        if one is not None:
            return one.user_id
        many = await User.find_all_by_email_ci(stripped)
        if len(many) == 1:
            return many[0].user_id
    return None


async def _enrich_span_items(
    items: list[Span],
) -> list[PlatformTracingSpanItem]:
    company_ids = {span.company_id for span in items if span.company_id is not None}
    user_ids = {span.user_id for span in items if span.user_id is not None}
    companies = await Company.get_many(list(company_ids)) if company_ids else {}
    users = await User.get_many(list(user_ids)) if user_ids else {}
    enriched: list[PlatformTracingSpanItem] = []
    for span in items:
        company = companies.get(span.company_id) if span.company_id is not None else None
        user = users.get(span.user_id) if span.user_id is not None else None
        enriched.append(
            PlatformTracingSpanItem.from_trace_span(
                span,
                company_name=company.name if company is not None else None,
                user_display_name=user.name if user is not None else span.user_name,
            )
        )
    return enriched


async def op_platform_tracing_facet_companies(
    payload: TracingFacetPayload, *, user: User, di: Di
) -> PlatformTracingFacetItemsResponse:
    _ = user
    await _require_tracing_admin(di)
    frag = (payload.q or "").strip().lower()
    if not frag:
        ids = await Span.admin_facet_distinct_company_ids(q=payload.q, limit=payload.limit)
        companies = await Company.get_many(ids) if ids else {}
        return PlatformTracingFacetItemsResponse(
            items=[
                PlatformTracingFacetItem(
                    value=cid,
                    label=_company_facet_label(cid, companies[cid].name if cid in companies else None),
                )
                for cid in ids
            ]
        )
    ids_by_span_column = await Span.admin_facet_distinct_company_ids(
        q=payload.q, limit=payload.limit
    )
    in_tracing = set(await Span.admin_list_distinct_company_ids_in_spans(max_ids=5000))
    all_companies = await Company.list(limit=BILLING_COMPANY_LIST_CAP, offset=0)
    looked_up = await _companies_for_facet_query(frag)
    meta_matched = [
        company
        for company in all_companies
        if company.company_id in in_tracing and company_matches_billing_facet_query(company, frag)
    ]
    seen = {company.company_id for company in meta_matched}
    for company in looked_up:
        if company.company_id in seen or not company_matches_billing_facet_query(company, frag):
            continue
        in_spans = company.company_id in in_tracing or await Span.company_has_spans(
            company.company_id
        )
        if not in_spans:
            continue
        meta_matched.append(company)
        seen.add(company.company_id)
    meta_matched.sort(key=lambda company: _tracing_company_facet_sort_key(company, frag))
    ordered_ids: list[str] = []
    for cid in [*ids_by_span_column, *(company.company_id for company in meta_matched)]:
        if cid not in ordered_ids and len(ordered_ids) < payload.limit:
            ordered_ids.append(cid)
    companies_map = await Company.get_many(ordered_ids) if ordered_ids else {}
    return PlatformTracingFacetItemsResponse(
        items=[
            PlatformTracingFacetItem(
                value=cid,
                label=_company_facet_label(cid, companies_map[cid].name if cid in companies_map else None),
            )
            for cid in ordered_ids
        ]
    )


async def op_platform_tracing_facet_users(
    payload: TracingFacetPayload, *, user: User, di: Di
) -> PlatformTracingFacetItemsResponse:
    _ = user
    await _require_tracing_admin(di)
    frag = (payload.q or "").strip().lower()
    ids_by_span = await Span.admin_facet_distinct_user_ids(
        q=payload.q, company_id=payload.company_id, namespace=payload.namespace, limit=payload.limit
    )
    ordered_ids: list[str] = list(ids_by_span)
    if frag:
        in_tracing = set(
            await Span.admin_list_distinct_user_ids_in_spans(
                max_ids=5000, company_id=payload.company_id, namespace=payload.namespace
            )
        )
        search_hits = await User.search_by_query(frag, limit=200)
        meta = [hit for hit in search_hits if hit.user_id in in_tracing]
        meta.sort(key=lambda hit: _user_facet_match_sort_key(frag, hit))
        ordered_ids = []
        for uid in [*(hit.user_id for hit in meta), *ids_by_span]:
            if uid not in ordered_ids and len(ordered_ids) < payload.limit:
                ordered_ids.append(uid)
    users_map = await User.get_many(ordered_ids) if ordered_ids else {}
    return PlatformTracingFacetItemsResponse(
        items=[
            PlatformTracingFacetItem(value=uid, label=_user_facet_item_label(users_map.get(uid), uid))
            for uid in ordered_ids
        ]
    )


async def op_platform_tracing_facet_services(
    payload: TracingFacetPayload, *, user: User, di: Di
) -> PlatformTracingFacetsResponse:
    _ = user
    await _require_tracing_admin(di)
    items = await Span.admin_facet_distinct_service_names(
        q=payload.q, company_id=payload.company_id, namespace=payload.namespace, limit=payload.limit
    )
    return PlatformTracingFacetsResponse(items=items)


async def op_platform_tracing_facet_event_types(
    payload: TracingFacetPayload, *, user: User, di: Di
) -> PlatformTracingFacetsResponse:
    _ = user
    await _require_tracing_admin(di)
    items = await Span.admin_facet_distinct_event_types(
        q=payload.q, company_id=payload.company_id, namespace=payload.namespace, limit=payload.limit
    )
    return PlatformTracingFacetsResponse(items=items)


async def op_platform_tracing_facet_namespaces(
    payload: TracingFacetPayload, *, user: User, di: Di
) -> PlatformTracingFacetsResponse:
    _ = user
    await _require_tracing_admin(di)
    items = await Span.admin_facet_distinct_namespaces(
        q=payload.q, company_id=payload.company_id, limit=payload.limit
    )
    return PlatformTracingFacetsResponse(items=items)


async def op_platform_tracing_facet_operations(
    payload: TracingFacetPayload, *, user: User, di: Di
) -> PlatformTracingFacetsResponse:
    _ = user
    await _require_tracing_admin(di)
    items = await Span.admin_facet_distinct_operation_names(
        q=payload.q, company_id=payload.company_id, namespace=payload.namespace, limit=payload.limit
    )
    return PlatformTracingFacetsResponse(items=items)


async def op_platform_tracing_spans(
    payload: TracingSpansPayload, *, user: User, di: Di
) -> CursorPage[PlatformTracingSpanItem]:
    _ = user
    await _require_tracing_admin(di)
    company_id_for_search = payload.company_id
    company_id_query_for_search = payload.company_id_query
    if payload.company_id is None and payload.company_id_query is not None:
        resolved = await _resolve_company_id_query_to_exact_match(payload.company_id_query)
        if resolved is not None:
            company_id_for_search = resolved
            company_id_query_for_search = None
    user_id_for_search = payload.user_id
    user_id_query_for_search = payload.user_id_query
    if payload.user_id is None and payload.user_id_query is not None:
        resolved_user = await _resolve_user_id_query_to_exact_match(payload.user_id_query)
        if resolved_user is not None:
            user_id_for_search = resolved_user
            user_id_query_for_search = None
    try:
        items, next_cursor = await Span.admin_search_spans(
            service_name=payload.service_name,
            company_id=company_id_for_search,
            user_id=user_id_for_search,
            namespace=payload.namespace,
            from_time=payload.from_time,
            to_time=payload.to_time,
            company_id_query=company_id_query_for_search,
            user_id_query=user_id_query_for_search,
            operation_name_query=payload.operation_name_query,
            event_type_query=payload.event_type_query,
            namespace_query=payload.namespace_query,
            service_name_query=payload.service_name_query,
            limit=payload.limit,
            cursor=payload.cursor,
        )
    except ValueError as exc:
        raise_invalid(exc)
    enriched = await _enrich_span_items(items)
    return CursorPage[PlatformTracingSpanItem](items=enriched, next_cursor=next_cursor, has_more=next_cursor is not None)


async def op_platform_tracing_trace_tree(
    payload: TracingTraceIdPayload, *, user: User, di: Di
) -> TracingTraceTree:
    _ = user
    await _require_tracing_admin(di)
    spans = await Span.list_for_trace(payload.trace_id)
    enriched = await _enrich_span_items(spans)
    return TracingTraceTree(trace_id=payload.trace_id, spans_count=len(spans), tree=build_span_tree(enriched))
