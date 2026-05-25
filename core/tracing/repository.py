"""
SpanRepository — персистенция spans в platform_tracing.

Иерархия OTEL: trace_id + parent_span_id. Доменный журнал: event_type, resource_type, resource_id
(и дубли в attributes). Специфика flows остаётся в attributes (platform.flow_id и т.д.).
"""

from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from typing import TYPE_CHECKING
from typing import cast as type_cast

from sqlalchemy import Boolean, and_, cast, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm.attributes import InstrumentedAttribute
from sqlalchemy.sql.elements import ColumnElement

import core.tracing.attributes as trace_attr
from core.db.jsonb import jsonb_text
from core.db.models import Spans
from core.logging import get_logger
from core.tracing.models import (
    BillingSettlementSpan,
    TraceSearchResult,
    TraceSpanEvent,
    TraceSpanRecord,
    TraceSpanWrite,
)
from core.types import JsonArray, JsonObject, parse_json_object, require_json_object

if TYPE_CHECKING:
    from core.db import Storage

logger = get_logger(__name__)


def _span_attribute_text(key: str) -> ColumnElement[str | None]:
    return jsonb_text(Spans.attributes, key)


def _json_text_eq(key: str, value: str) -> ColumnElement[bool]:
    """attributes->>key = value (ключ целиком, например platform.flow_id)."""
    return _span_attribute_text(key) == value


def _encode_service_list_cursor(start_time: datetime, span_id: str) -> str:
    if start_time.tzinfo is None:
        raise ValueError("start_time обязан быть с timezone")
    payload = {"t": start_time.isoformat(), "s": span_id}
    raw = json.dumps(payload, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode_service_list_cursor(cursor: str) -> tuple[datetime, str]:
    pad = "=" * (-len(cursor) % 4)
    raw = base64.urlsafe_b64decode(cursor + pad)
    payload = parse_json_object(raw.decode(), "cursor")
    raw_time = payload.get("t")
    if not isinstance(raw_time, str):
        raise ValueError("cursor.t должен быть строкой")
    raw_span_id = payload.get("s")
    if not isinstance(raw_span_id, str):
        raise ValueError("cursor.s должен быть строкой")
    t = datetime.fromisoformat(raw_time)
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return t, raw_span_id


MIN_ADMIN_ILIKE_LEN = 2
ADMIN_SPANS_MAX_LIMIT = 100
ADMIN_FACETS_MAX_LIMIT = 20


def _escape_like_fragment(fragment: str) -> str:
    return fragment.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def admin_ilike(
    column: InstrumentedAttribute[str] | InstrumentedAttribute[str | None] | ColumnElement[str | None],
    fragment: str,
) -> ColumnElement[bool]:
    return type_cast(ColumnElement[bool], column.ilike(f"%{_escape_like_fragment(fragment)}%", escape="\\"))


def _admin_optional_ilike_param(param_name: str, value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    if stripped == "":
        return None
    if len(stripped) < MIN_ADMIN_ILIKE_LEN:
        message = (
            f"{param_name}: для поиска подстроки нужно минимум {MIN_ADMIN_ILIKE_LEN} "
            f"символа, получено {len(stripped)}"
        )
        raise ValueError(message)
    return stripped


def facet_query_fragment(q: str | None) -> str | None:
    if q is None:
        return None
    stripped = q.strip()
    if stripped == "":
        return None
    if len(stripped) < MIN_ADMIN_ILIKE_LEN:
        return None
    return stripped


def _admin_facet_scope_company(company_id: str | None) -> str | None:
    if company_id is None:
        return None
    stripped = company_id.strip()
    return stripped if stripped else None


def _admin_facet_scope_namespace(namespace: str | None) -> str | None:
    if namespace is None:
        return None
    stripped = namespace.strip()
    return stripped if stripped else None


def _optional_string_attribute(attributes: JsonObject, key: str, span_id: str) -> str | None:
    value = attributes.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"span {span_id}: {key} должен быть строкой")
    return value


def _optional_bool_attribute(attributes: JsonObject, key: str, span_id: str) -> bool | None:
    value = attributes.get(key)
    if value is None:
        return None
    if not isinstance(value, bool):
        raise ValueError(f"span {span_id}: {key} должен быть boolean")
    return value


def _span_user_groups(value: JsonArray | None, span_id: str) -> list[str] | None:
    if value is None:
        return None
    groups: list[str] = []
    for index, group in enumerate(value):
        if not isinstance(group, str):
            raise ValueError(f"span {span_id}: user_groups[{index}] должен быть строкой")
        groups.append(group)
    return groups


def _span_event_attributes(event_payload: JsonObject, span_id: str, index: int) -> JsonObject:
    raw_attributes = event_payload.get("attributes")
    if raw_attributes is None:
        return {}
    if not isinstance(raw_attributes, dict):
        raise ValueError(f"span {span_id}: events[{index}].attributes должен быть JSON object")
    return require_json_object(raw_attributes, f"spans[{span_id}].events[{index}].attributes")


def _span_events(value: JsonArray | None, span_id: str) -> list[TraceSpanEvent]:
    if value is None:
        return []
    events: list[TraceSpanEvent] = []
    for index, event in enumerate(value):
        if not isinstance(event, dict):
            raise ValueError(f"span {span_id}: events[{index}] должен быть JSON object")
        event_payload = require_json_object(event, f"spans[{span_id}].events[{index}]")
        raw_name = event_payload.get("name")
        if not isinstance(raw_name, str):
            raise ValueError(f"span {span_id}: events[{index}].name должен быть строкой")
        raw_timestamp = event_payload.get("timestamp")
        if raw_timestamp is not None and not isinstance(raw_timestamp, str):
            raise ValueError(f"span {span_id}: events[{index}].timestamp должен быть строкой или null")
        events.append(
            TraceSpanEvent(
                name=raw_name,
                timestamp=raw_timestamp,
                attributes=_span_event_attributes(event_payload, span_id, index),
            )
        )
    return events


class SpanRepository:
    def __init__(self, storage: "Storage"):
        self._storage: Storage = storage

    async def save_span(self, span: TraceSpanWrite) -> None:
        attrs: JsonObject = dict(span.attributes)

        if span.event_type is not None and trace_attr.ATTR_EVENT_TYPE not in attrs:
            attrs[trace_attr.ATTR_EVENT_TYPE] = span.event_type
        if span.resource_type is not None and trace_attr.ATTR_RESOURCE_TYPE not in attrs:
            attrs[trace_attr.ATTR_RESOURCE_TYPE] = span.resource_type
        if span.resource_id is not None and trace_attr.ATTR_RESOURCE_ID not in attrs:
            attrs[trace_attr.ATTR_RESOURCE_ID] = span.resource_id

        if not span.service_name:
            raise ValueError("span_data['service_name'] обязателен для сохранения span")

        async with self._storage.get_session() as session:
            stmt = (
                insert(Spans)
                .values(
                    span_id=span.span_id,
                    trace_id=span.trace_id,
                    parent_span_id=span.parent_span_id,
                    operation_name=span.operation_name,
                    kind=span.kind,
                    start_time=span.start_time,
                    end_time=span.end_time,
                    duration_ms=span.duration_ms,
                    status=span.status,
                    status_message=span.status_message,
                    service_name=span.service_name,
                    company_id=span.company_id,
                    namespace=span.namespace,
                    user_id=span.user_id,
                    user_name=span.user_name,
                    user_groups=span.user_groups,
                    session_auth=span.session_auth,
                    session_agent=span.session_agent,
                    channel=span.channel,
                    event_type=span.event_type,
                    resource_type=span.resource_type,
                    resource_id=span.resource_id,
                    attributes=attrs,
                    events=span.events_json_array(),
                )
                .on_conflict_do_nothing(index_elements=["span_id"])
            )
            _ = await session.execute(stmt)
            await session.commit()

    async def get_span_by_id(self, span_id: str) -> TraceSpanRecord | None:
        async with self._storage.get_session() as session:
            stmt = select(Spans).where(Spans.span_id == span_id)
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
            if row is None:
                return None
            return self._serialize_span(row)

    async def list_spans_for_service(
        self,
        *,
        service_name: str,
        company_id: str | None = None,
        namespace: str | None = None,
        operation_name: str | None = None,
        event_type: str | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> tuple[list[TraceSpanRecord], str | None]:
        """
        Список spans сервиса (фильтры по компании, операции, типу события).
        Сортировка: start_time DESC, span_id DESC. Курсор — непрозрачная строка из ответа.
        """
        if limit < 1:
            raise ValueError("limit должен быть >= 1")

        async with self._storage.get_session() as session:
            stmt = select(Spans).where(Spans.service_name == service_name)
            if company_id is not None:
                stmt = stmt.where(Spans.company_id == company_id)
            if namespace is not None:
                stmt = stmt.where(Spans.namespace == namespace)
            if operation_name is not None:
                stmt = stmt.where(Spans.operation_name == operation_name)
            if event_type is not None:
                stmt = stmt.where(Spans.event_type == event_type)
            if cursor is not None:
                try:
                    cursor_time, cursor_span_id = _decode_service_list_cursor(cursor)
                except (json.JSONDecodeError, KeyError, ValueError) as e:
                    raise ValueError(f"Некорректный cursor: {e}") from e
                stmt = stmt.where(
                    or_(
                        Spans.start_time < cursor_time,
                        and_(
                            Spans.start_time == cursor_time,
                            Spans.span_id < cursor_span_id,
                        ),
                    )
                )
            stmt = stmt.order_by(Spans.start_time.desc(), Spans.span_id.desc()).limit(limit)
            result = await session.execute(stmt)
            rows = result.scalars().all()
            items = [self._serialize_span(row) for row in rows]
            next_cursor: str | None = None
            if len(items) == limit:
                last = rows[-1]
                next_cursor = _encode_service_list_cursor(last.start_time, last.span_id)
            return items, next_cursor

    async def list_spans_for_resource(
        self,
        *,
        company_id: str,
        resource_type: str,
        resource_id: str,
        event_type: str | None = None,
        limit: int = 100,
    ) -> list[TraceSpanRecord]:
        """Хронология событий по сущности (чат, заметка, документ и т.д.)."""
        async with self._storage.get_session() as session:
            stmt = select(Spans).where(
                Spans.company_id == company_id,
                Spans.resource_type == resource_type,
                Spans.resource_id == resource_id,
            )
            if event_type:
                stmt = stmt.where(Spans.event_type == event_type)
            stmt = stmt.order_by(Spans.start_time.desc()).limit(limit)
            result = await session.execute(stmt)
            rows = result.scalars().all()
            return [self._serialize_span(row) for row in rows]

    async def get_trace(self, trace_id: str) -> list[TraceSpanRecord]:
        async with self._storage.get_session() as session:
            stmt = select(Spans).where(Spans.trace_id == trace_id).order_by(Spans.start_time.asc())
            result = await session.execute(stmt)
            rows = result.scalars().all()
            return [self._serialize_span(row) for row in rows]

    async def get_spans_by_task(self, task_id: str) -> list[TraceSpanRecord]:
        async with self._storage.get_session() as session:
            stmt = (
                select(Spans)
                .where(_json_text_eq(trace_attr.ATTR_TASK_ID, task_id))
                .order_by(Spans.start_time.asc())
            )
            result = await session.execute(stmt)
            rows = result.scalars().all()
            return [self._serialize_span(row) for row in rows]

    async def get_spans_by_session(
        self,
        session_agent: str,
        limit: int = 100,
    ) -> list[TraceSpanRecord]:
        async with self._storage.get_session() as session:
            stmt = (
                select(Spans)
                .where(Spans.session_agent == session_agent)
                .order_by(Spans.start_time.desc())
                .limit(limit)
            )
            result = await session.execute(stmt)
            rows = result.scalars().all()
            return [self._serialize_span(row) for row in rows]

    async def get_spans_by_user(
        self,
        user_id: str,
        from_time: datetime | None = None,
        to_time: datetime | None = None,
        limit: int = 100,
    ) -> list[TraceSpanRecord]:
        async with self._storage.get_session() as session:
            stmt = select(Spans).where(Spans.user_id == user_id)
            if from_time:
                stmt = stmt.where(Spans.start_time >= from_time)
            if to_time:
                stmt = stmt.where(Spans.start_time <= to_time)
            stmt = stmt.order_by(Spans.start_time.desc()).limit(limit)
            result = await session.execute(stmt)
            rows = result.scalars().all()
            return [self._serialize_span(row) for row in rows]

    async def get_spans_by_agent(
        self,
        flow_id: str,
        from_time: datetime | None = None,
        to_time: datetime | None = None,
        limit: int = 100,
    ) -> list[TraceSpanRecord]:
        async with self._storage.get_session() as session:
            stmt = select(Spans).where(
                _json_text_eq(trace_attr.ATTR_FLOW_ID, flow_id)
            )
            if from_time:
                stmt = stmt.where(Spans.start_time >= from_time)
            if to_time:
                stmt = stmt.where(Spans.start_time <= to_time)
            stmt = stmt.order_by(Spans.start_time.desc()).limit(limit)
            result = await session.execute(stmt)
            rows = result.scalars().all()
            return [self._serialize_span(row) for row in rows]

    async def get_spans_by_flow(
        self,
        flow_id: str,
        from_time: datetime | None = None,
        to_time: datetime | None = None,
        limit: int = 100,
    ) -> list[TraceSpanRecord]:
        return await self.get_spans_by_agent(flow_id, from_time, to_time, limit)

    async def search_traces(
        self,
        user_id: str | None = None,
        session_id: str | None = None,
        flow_id: str | None = None,
        task_id: str | None = None,
        from_time: datetime | None = None,
        to_time: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[TraceSearchResult], int]:
        async with self._storage.get_session() as session:
            stmt = select(Spans)
            count_stmt = select(func.count()).select_from(Spans)

            if user_id:
                stmt = stmt.where(Spans.user_id == user_id)
                count_stmt = count_stmt.where(Spans.user_id == user_id)
            if session_id:
                stmt = stmt.where(Spans.session_agent == session_id)
                count_stmt = count_stmt.where(Spans.session_agent == session_id)
            if flow_id:
                cond = _json_text_eq(trace_attr.ATTR_FLOW_ID, flow_id)
                stmt = stmt.where(cond)
                count_stmt = count_stmt.where(cond)
            if task_id:
                cond = _json_text_eq(trace_attr.ATTR_TASK_ID, task_id)
                stmt = stmt.where(cond)
                count_stmt = count_stmt.where(cond)
            if from_time:
                stmt = stmt.where(Spans.start_time >= from_time)
                count_stmt = count_stmt.where(Spans.start_time >= from_time)
            if to_time:
                stmt = stmt.where(Spans.start_time <= to_time)
                count_stmt = count_stmt.where(Spans.start_time <= to_time)

            count_result = await session.execute(count_stmt)
            total_count = count_result.scalar()

            stmt = stmt.order_by(Spans.start_time.desc()).limit(limit).offset(offset)
            result = await session.execute(stmt)
            rows = result.scalars().all()
            spans = [self._serialize_span(row) for row in rows]

            traces_dict: dict[str, list[TraceSpanRecord]] = {}
            for span in spans:
                if span.trace_id not in traces_dict:
                    traces_dict[span.trace_id] = []
                traces_dict[span.trace_id].append(span)

            return [
                TraceSearchResult(trace_id=trace_id, spans=trace_spans)
                for trace_id, trace_spans in traces_dict.items()
            ], total_count or 0

    async def admin_search_spans(
        self,
        *,
        service_name: str | None = None,
        company_id: str | None = None,
        user_id: str | None = None,
        namespace: str | None = None,
        from_time: datetime | None = None,
        to_time: datetime | None = None,
        company_id_query: str | None = None,
        user_id_query: str | None = None,
        operation_name_query: str | None = None,
        event_type_query: str | None = None,
        namespace_query: str | None = None,
        service_name_query: str | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> tuple[list[TraceSpanRecord], str | None]:
        if limit < 1:
            raise ValueError("limit должен быть >= 1")
        if limit > ADMIN_SPANS_MAX_LIMIT:
            raise ValueError(f"limit не больше {ADMIN_SPANS_MAX_LIMIT}")

        company_frag = _admin_optional_ilike_param("company_id_query", company_id_query)
        user_frag = _admin_optional_ilike_param("user_id_query", user_id_query)
        op_frag = _admin_optional_ilike_param("operation_name_query", operation_name_query)
        event_frag = _admin_optional_ilike_param("event_type_query", event_type_query)
        namespace_frag: str | None = None
        if namespace is None:
            namespace_frag = _admin_optional_ilike_param("namespace_query", namespace_query)
        service_name_frag: str | None = None
        if service_name is None:
            service_name_frag = _admin_optional_ilike_param("service_name_query", service_name_query)

        async with self._storage.get_session() as session:
            stmt = select(Spans)
            if service_name is not None:
                stmt = stmt.where(Spans.service_name == service_name)
            elif service_name_frag is not None:
                stmt = stmt.where(admin_ilike(Spans.service_name, service_name_frag))
            if company_id is not None:
                stmt = stmt.where(Spans.company_id == company_id)
            if user_id is not None:
                stmt = stmt.where(Spans.user_id == user_id)
            if namespace is not None:
                stmt = stmt.where(Spans.namespace == namespace)
            elif namespace_frag is not None:
                stmt = stmt.where(admin_ilike(Spans.namespace, namespace_frag))
            if from_time is not None:
                stmt = stmt.where(Spans.start_time >= from_time)
            if to_time is not None:
                stmt = stmt.where(Spans.start_time <= to_time)
            if company_frag is not None:
                stmt = stmt.where(admin_ilike(Spans.company_id, company_frag))
            if user_frag is not None:
                stmt = stmt.where(admin_ilike(Spans.user_id, user_frag))
            if op_frag is not None:
                stmt = stmt.where(admin_ilike(Spans.operation_name, op_frag))
            if event_frag is not None:
                stmt = stmt.where(admin_ilike(Spans.event_type, event_frag))
            if cursor is not None:
                try:
                    cursor_time, cursor_span_id = _decode_service_list_cursor(cursor)
                except (json.JSONDecodeError, KeyError, ValueError) as e:
                    raise ValueError(f"Некорректный cursor: {e}") from e
                stmt = stmt.where(
                    or_(
                        Spans.start_time < cursor_time,
                        and_(
                            Spans.start_time == cursor_time,
                            Spans.span_id < cursor_span_id,
                        ),
                    )
                )
            stmt = stmt.order_by(Spans.start_time.desc(), Spans.span_id.desc()).limit(limit)
            result = await session.execute(stmt)
            rows = result.scalars().all()
            items = [self._serialize_span(row) for row in rows]
            next_cursor: str | None = None
            if len(items) == limit:
                last = rows[-1]
                next_cursor = _encode_service_list_cursor(last.start_time, last.span_id)
            return items, next_cursor

    async def list_spans_pending_billing_settlement(
        self,
        *,
        from_time: datetime,
        to_time: datetime,
        limit: int,
    ) -> list[BillingSettlementSpan]:
        """
        Spans с platform.billing.resource_name и platform.billing.pending_settlement=true
        за полуинтервал [from_time, to_time), по возрастанию start_time (для джобы списания).
        """
        if limit < 1:
            raise ValueError("limit должен быть >= 1")
        if from_time.tzinfo is None or to_time.tzinfo is None:
            raise ValueError("from_time и to_time обязаны иметь timezone")

        res_txt = _span_attribute_text(trace_attr.ATTR_BILLING_RESOURCE_NAME)
        pend_txt = _span_attribute_text(trace_attr.ATTR_BILLING_PENDING_SETTLEMENT)

        async with self._storage.get_session() as session:
            stmt = (
                select(Spans)
                .where(
                    Spans.start_time >= from_time,
                    Spans.start_time < to_time,
                    res_txt.isnot(None),
                    res_txt != "",
                    or_(
                        pend_txt.in_(("true", "True", "1")),
                        cast(pend_txt, Boolean).is_(True),
                    ),
                )
                .order_by(Spans.start_time.asc(), Spans.span_id.asc())
                .limit(limit)
            )
            result = await session.execute(stmt)
            rows = result.scalars().all()
            return [self._billing_settlement_span(row) for row in rows]

    async def admin_facet_distinct_company_ids(
        self, *, q: str | None = None, limit: int = ADMIN_FACETS_MAX_LIMIT
    ) -> list[str]:
        if limit < 1 or limit > ADMIN_FACETS_MAX_LIMIT:
            raise ValueError(f"limit должен быть от 1 до {ADMIN_FACETS_MAX_LIMIT}")
        frag = facet_query_fragment(q)
        async with self._storage.get_session() as session:
            stmt = select(Spans.company_id).where(Spans.company_id.isnot(None))
            if frag is not None:
                stmt = stmt.where(admin_ilike(Spans.company_id, frag))
            stmt = stmt.distinct().order_by(Spans.company_id.asc()).limit(limit)
            result = await session.execute(stmt)
            return [row[0] for row in result.all() if row[0] is not None]

    async def admin_list_distinct_company_ids_in_spans(self, *, max_ids: int = 5000) -> list[str]:
        """
        Список distinct company_id, для которых есть spans, для пересечения
        с каталогом компаний (поиск по name/subdomain, не только по id в трейсах).
        """
        if max_ids < 1 or max_ids > 50_000:
            raise ValueError("max_ids должен быть от 1 до 50000")
        async with self._storage.get_session() as session:
            stmt = (
                select(Spans.company_id)
                .where(Spans.company_id.isnot(None))
                .distinct()
                .order_by(Spans.company_id.asc())
                .limit(max_ids)
            )
            result = await session.execute(stmt)
            return [row[0] for row in result.all() if row[0] is not None]

    async def admin_facet_distinct_user_ids(
        self,
        *,
        q: str | None = None,
        company_id: str | None = None,
        namespace: str | None = None,
        limit: int = ADMIN_FACETS_MAX_LIMIT,
    ) -> list[str]:
        if limit < 1 or limit > ADMIN_FACETS_MAX_LIMIT:
            raise ValueError(f"limit должен быть от 1 до {ADMIN_FACETS_MAX_LIMIT}")
        frag = facet_query_fragment(q)
        scope_co = _admin_facet_scope_company(company_id)
        scope_ns = _admin_facet_scope_namespace(namespace)
        async with self._storage.get_session() as session:
            stmt = select(Spans.user_id).where(Spans.user_id.isnot(None))
            if scope_co is not None:
                stmt = stmt.where(Spans.company_id == scope_co)
            if scope_ns is not None:
                stmt = stmt.where(Spans.namespace == scope_ns)
            if frag is not None:
                stmt = stmt.where(admin_ilike(Spans.user_id, frag))
            stmt = stmt.distinct().order_by(Spans.user_id.asc()).limit(limit)
            result = await session.execute(stmt)
            return [row[0] for row in result.all() if row[0] is not None]

    async def admin_list_distinct_user_ids_in_spans(
        self,
        *,
        max_ids: int = 5000,
        company_id: str | None = None,
        namespace: str | None = None,
    ) -> list[str]:
        """
        Список distinct user_id, для которых есть spans (с опциональным сужением),
        для пересечения с каталогом пользователей (поиск по email/имени).
        """
        if max_ids < 1 or max_ids > 50_000:
            raise ValueError("max_ids должен быть от 1 до 50000")
        scope_co = _admin_facet_scope_company(company_id)
        scope_ns = _admin_facet_scope_namespace(namespace)
        async with self._storage.get_session() as session:
            stmt = select(Spans.user_id).where(Spans.user_id.isnot(None))
            if scope_co is not None:
                stmt = stmt.where(Spans.company_id == scope_co)
            if scope_ns is not None:
                stmt = stmt.where(Spans.namespace == scope_ns)
            stmt = stmt.distinct().order_by(Spans.user_id.asc()).limit(max_ids)
            result = await session.execute(stmt)
            return [row[0] for row in result.all() if row[0] is not None]

    async def admin_facet_distinct_service_names(
        self,
        *,
        q: str | None = None,
        company_id: str | None = None,
        namespace: str | None = None,
        limit: int = ADMIN_FACETS_MAX_LIMIT,
    ) -> list[str]:
        if limit < 1 or limit > ADMIN_FACETS_MAX_LIMIT:
            raise ValueError(f"limit должен быть от 1 до {ADMIN_FACETS_MAX_LIMIT}")
        frag = facet_query_fragment(q)
        scope_co = _admin_facet_scope_company(company_id)
        scope_ns = _admin_facet_scope_namespace(namespace)
        async with self._storage.get_session() as session:
            stmt = select(Spans.service_name).where(Spans.service_name.isnot(None))
            if scope_co is not None:
                stmt = stmt.where(Spans.company_id == scope_co)
            if scope_ns is not None:
                stmt = stmt.where(Spans.namespace == scope_ns)
            if frag is not None:
                stmt = stmt.where(admin_ilike(Spans.service_name, frag))
            stmt = stmt.distinct().order_by(Spans.service_name.asc()).limit(limit)
            result = await session.execute(stmt)
            return [row[0] for row in result.all() if row[0] is not None]

    async def admin_facet_distinct_event_types(
        self,
        *,
        q: str | None = None,
        company_id: str | None = None,
        namespace: str | None = None,
        limit: int = ADMIN_FACETS_MAX_LIMIT,
    ) -> list[str]:
        if limit < 1 or limit > ADMIN_FACETS_MAX_LIMIT:
            raise ValueError(f"limit должен быть от 1 до {ADMIN_FACETS_MAX_LIMIT}")
        frag = facet_query_fragment(q)
        scope_co = _admin_facet_scope_company(company_id)
        scope_ns = _admin_facet_scope_namespace(namespace)
        async with self._storage.get_session() as session:
            stmt = select(Spans.event_type).where(Spans.event_type.isnot(None))
            if scope_co is not None:
                stmt = stmt.where(Spans.company_id == scope_co)
            if scope_ns is not None:
                stmt = stmt.where(Spans.namespace == scope_ns)
            if frag is not None:
                stmt = stmt.where(admin_ilike(Spans.event_type, frag))
            stmt = stmt.distinct().order_by(Spans.event_type.asc()).limit(limit)
            result = await session.execute(stmt)
            return [row[0] for row in result.all() if row[0] is not None]

    async def admin_facet_distinct_namespaces(
        self,
        *,
        q: str | None = None,
        company_id: str | None = None,
        limit: int = ADMIN_FACETS_MAX_LIMIT,
    ) -> list[str]:
        if limit < 1 or limit > ADMIN_FACETS_MAX_LIMIT:
            raise ValueError(f"limit должен быть от 1 до {ADMIN_FACETS_MAX_LIMIT}")
        frag = facet_query_fragment(q)
        scope_co = _admin_facet_scope_company(company_id)
        async with self._storage.get_session() as session:
            stmt = select(Spans.namespace).where(Spans.namespace.isnot(None))
            if scope_co is not None:
                stmt = stmt.where(Spans.company_id == scope_co)
            if frag is not None:
                stmt = stmt.where(admin_ilike(Spans.namespace, frag))
            stmt = stmt.distinct().order_by(Spans.namespace.asc()).limit(limit)
            result = await session.execute(stmt)
            return [row[0] for row in result.all() if row[0] is not None]

    async def admin_facet_distinct_operation_names(
        self,
        *,
        q: str | None = None,
        company_id: str | None = None,
        namespace: str | None = None,
        limit: int = ADMIN_FACETS_MAX_LIMIT,
    ) -> list[str]:
        if limit < 1 or limit > ADMIN_FACETS_MAX_LIMIT:
            raise ValueError(f"limit должен быть от 1 до {ADMIN_FACETS_MAX_LIMIT}")
        frag = facet_query_fragment(q)
        scope_co = _admin_facet_scope_company(company_id)
        scope_ns = _admin_facet_scope_namespace(namespace)
        async with self._storage.get_session() as session:
            stmt = select(Spans.operation_name).where(Spans.operation_name.isnot(None))
            if scope_co is not None:
                stmt = stmt.where(Spans.company_id == scope_co)
            if scope_ns is not None:
                stmt = stmt.where(Spans.namespace == scope_ns)
            if frag is not None:
                stmt = stmt.where(admin_ilike(Spans.operation_name, frag))
            stmt = stmt.distinct().order_by(Spans.operation_name.asc()).limit(limit)
            result = await session.execute(stmt)
            return [row[0] for row in result.all() if row[0] is not None]

    def _serialize_span(self, row: Spans) -> TraceSpanRecord:
        raw_attrs: JsonObject = dict(row.attributes) if row.attributes is not None else {}
        return TraceSpanRecord(
            span_id=row.span_id,
            trace_id=row.trace_id,
            parent_span_id=row.parent_span_id,
            operation_name=row.operation_name,
            kind=row.kind,
            start_time=row.start_time,
            end_time=row.end_time,
            duration_ms=row.duration_ms,
            status=row.status,
            status_message=row.status_message,
            service_name=row.service_name,
            company_id=row.company_id,
            namespace=row.namespace,
            user_id=row.user_id,
            user_name=row.user_name,
            user_groups=_span_user_groups(row.user_groups, row.span_id),
            session_auth=row.session_auth,
            session_agent=row.session_agent,
            channel=row.channel,
            event_type=row.event_type,
            resource_type=row.resource_type,
            resource_id=row.resource_id,
            flow_id=_optional_string_attribute(raw_attrs, trace_attr.ATTR_FLOW_ID, row.span_id),
            task_id=_optional_string_attribute(raw_attrs, trace_attr.ATTR_TASK_ID, row.span_id),
            context_id=_optional_string_attribute(raw_attrs, trace_attr.ATTR_CONTEXT_ID, row.span_id),
            branch_id=_optional_string_attribute(raw_attrs, trace_attr.ATTR_BRANCH_ID, row.span_id),
            node_id=_optional_string_attribute(raw_attrs, trace_attr.ATTR_NODE_ID, row.span_id),
            agent_name=_optional_string_attribute(raw_attrs, trace_attr.ATTR_AGENT_NAME, row.span_id),
            is_resume=_optional_bool_attribute(raw_attrs, trace_attr.ATTR_IS_RESUME, row.span_id),
            attributes=raw_attrs,
            events=_span_events(row.events, row.span_id),
        )

    def _billing_settlement_span(self, row: Spans) -> BillingSettlementSpan:
        attributes: JsonObject = dict(row.attributes) if row.attributes is not None else {}
        return BillingSettlementSpan(
            span_id=row.span_id,
            trace_id=row.trace_id,
            operation_name=row.operation_name,
            service_name=row.service_name,
            company_id=row.company_id,
            user_id=row.user_id,
            event_type=row.event_type,
            attributes=attributes,
        )
