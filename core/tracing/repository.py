"""
SpanRepository — персистенция spans в platform_tracing.

Иерархия OTEL: trace_id + parent_span_id. Доменный журнал: event_type, resource_type, resource_id
(и дубли в attributes). Специфика flows остаётся в attributes (platform.flow_id и т.д.).
"""

import base64
import json
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from sqlalchemy import Boolean, and_, cast, func, or_, select
from sqlalchemy.dialects.postgresql import insert

from core.logging import get_logger
from . import attributes as trace_attr

if TYPE_CHECKING:
    from core.db import Storage

logger = get_logger(__name__)


def _json_text_eq(json_col, key: str, value: str):
    """attributes->>key = value (ключ целиком, например platform.flow_id)."""
    return json_col[key].astext == value


def _encode_service_list_cursor(start_time: datetime, span_id: str) -> str:
    if start_time.tzinfo is None:
        raise ValueError("start_time обязан быть с timezone")
    payload = {"t": start_time.isoformat(), "s": span_id}
    raw = json.dumps(payload, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode_service_list_cursor(cursor: str) -> Tuple[datetime, str]:
    pad = "=" * (-len(cursor) % 4)
    raw = base64.urlsafe_b64decode(cursor + pad)
    payload = json.loads(raw.decode())
    t = datetime.fromisoformat(payload["t"])
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return t, payload["s"]


MIN_ADMIN_ILIKE_LEN = 2
ADMIN_SPANS_MAX_LIMIT = 100
ADMIN_FACETS_MAX_LIMIT = 20


def _escape_like_fragment(fragment: str) -> str:
    return fragment.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _admin_ilike(column, fragment: str):
    return column.ilike(f"%{_escape_like_fragment(fragment)}%", escape="\\")


def _admin_optional_ilike_param(param_name: str, value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    stripped = value.strip()
    if stripped == "":
        return None
    if len(stripped) < MIN_ADMIN_ILIKE_LEN:
        raise ValueError(
            f"{param_name}: для поиска подстроки нужно минимум {MIN_ADMIN_ILIKE_LEN} символа, "
            f"получено {len(stripped)}"
        )
    return stripped


def _facet_query_fragment(q: Optional[str]) -> Optional[str]:
    if q is None:
        return None
    stripped = q.strip()
    if stripped == "":
        return None
    if len(stripped) < MIN_ADMIN_ILIKE_LEN:
        return None
    return stripped


def _admin_facet_scope_company(company_id: Optional[str]) -> Optional[str]:
    if company_id is None:
        return None
    stripped = company_id.strip()
    return stripped if stripped else None


def _admin_facet_scope_namespace(namespace: Optional[str]) -> Optional[str]:
    if namespace is None:
        return None
    stripped = namespace.strip()
    return stripped if stripped else None


class SpanRepository:
    def __init__(self, storage: "Storage"):
        self._storage = storage

    async def save_span(self, span_data: Dict[str, Any]) -> None:
        from core.db.models import Spans

        attrs: Dict[str, Any] = dict(span_data.get("attributes") or {})

        domain_pairs = [
            ("flow_id", trace_attr.ATTR_FLOW_ID),
            ("task_id", trace_attr.ATTR_TASK_ID),
            ("context_id", trace_attr.ATTR_CONTEXT_ID),
            ("skill_id", trace_attr.ATTR_SKILL_ID),
            ("node_id", trace_attr.ATTR_NODE_ID),
            ("agent_name", trace_attr.ATTR_AGENT_NAME),
            ("is_resume", trace_attr.ATTR_IS_RESUME),
        ]
        for legacy_key, attr_key in domain_pairs:
            val = span_data.get(legacy_key)
            if val is not None and attr_key not in attrs:
                attrs[attr_key] = val

        for col in ("event_type", "resource_type", "resource_id"):
            v = span_data.get(col)
            if v is not None:
                attr_map = {
                    "event_type": trace_attr.ATTR_EVENT_TYPE,
                    "resource_type": trace_attr.ATTR_RESOURCE_TYPE,
                    "resource_id": trace_attr.ATTR_RESOURCE_ID,
                }
                ak = attr_map[col]
                if ak not in attrs:
                    attrs[ak] = v

        service_name = span_data.get("service_name")
        if not service_name:
            raise ValueError("span_data['service_name'] обязателен для сохранения span")

        async with self._storage._get_session() as session:
            stmt = (
                insert(Spans)
                .values(
                    span_id=span_data["span_id"],
                    trace_id=span_data["trace_id"],
                    parent_span_id=span_data.get("parent_span_id"),
                    operation_name=span_data["operation_name"],
                    kind=span_data.get("kind"),
                    start_time=span_data["start_time"],
                    end_time=span_data.get("end_time"),
                    duration_ms=span_data.get("duration_ms"),
                    status=span_data.get("status"),
                    status_message=span_data.get("status_message"),
                    service_name=service_name,
                    company_id=span_data.get("company_id"),
                    namespace=span_data.get("namespace"),
                    user_id=span_data.get("user_id"),
                    user_name=span_data.get("user_name"),
                    user_groups=span_data.get("user_groups"),
                    session_auth=span_data.get("session_auth"),
                    session_agent=span_data.get("session_agent"),
                    channel=span_data.get("channel"),
                    event_type=span_data.get("event_type"),
                    resource_type=span_data.get("resource_type"),
                    resource_id=span_data.get("resource_id"),
                    attributes=attrs,
                    events=span_data.get("events") or [],
                )
                .on_conflict_do_nothing(index_elements=["span_id"])
            )
            await session.execute(stmt)
            await session.commit()

    async def get_span_by_id(self, span_id: str) -> Optional[Dict[str, Any]]:
        from core.db.models import Spans

        async with self._storage._get_session() as session:
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
        company_id: Optional[str] = None,
        namespace: Optional[str] = None,
        operation_name: Optional[str] = None,
        event_type: Optional[str] = None,
        limit: int = 50,
        cursor: Optional[str] = None,
    ) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """
        Список spans сервиса (фильтры по компании, операции, типу события).
        Сортировка: start_time DESC, span_id DESC. Курсор — непрозрачная строка из ответа.
        """
        from core.db.models import Spans

        if limit < 1:
            raise ValueError("limit должен быть >= 1")

        async with self._storage._get_session() as session:
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
            next_cursor: Optional[str] = None
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
        event_type: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Хронология событий по сущности (чат, заметка, документ и т.д.)."""
        from core.db.models import Spans

        async with self._storage._get_session() as session:
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

    async def get_trace(self, trace_id: str) -> List[Dict[str, Any]]:
        from core.db.models import Spans

        async with self._storage._get_session() as session:
            stmt = select(Spans).where(Spans.trace_id == trace_id).order_by(Spans.start_time.asc())
            result = await session.execute(stmt)
            rows = result.scalars().all()
            return [self._serialize_span(row) for row in rows]

    async def get_spans_by_task(self, task_id: str) -> List[Dict[str, Any]]:
        from core.db.models import Spans

        async with self._storage._get_session() as session:
            stmt = (
                select(Spans)
                .where(_json_text_eq(Spans.attributes, trace_attr.ATTR_TASK_ID, task_id))
                .order_by(Spans.start_time.asc())
            )
            result = await session.execute(stmt)
            rows = result.scalars().all()
            return [self._serialize_span(row) for row in rows]

    async def get_spans_by_session(
        self,
        session_agent: str,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        from core.db.models import Spans

        async with self._storage._get_session() as session:
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
        from_time: Optional[datetime] = None,
        to_time: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        from core.db.models import Spans

        async with self._storage._get_session() as session:
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
        from_time: Optional[datetime] = None,
        to_time: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        from core.db.models import Spans

        async with self._storage._get_session() as session:
            stmt = select(Spans).where(
                _json_text_eq(Spans.attributes, trace_attr.ATTR_FLOW_ID, flow_id)
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
        from_time: Optional[datetime] = None,
        to_time: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        return await self.get_spans_by_agent(flow_id, from_time, to_time, limit)

    async def search_traces(
        self,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        flow_id: Optional[str] = None,
        from_time: Optional[datetime] = None,
        to_time: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Tuple[List[Dict[str, Any]], int]:
        from core.db.models import Spans

        async with self._storage._get_session() as session:
            stmt = select(Spans)
            count_stmt = select(func.count()).select_from(Spans)

            if user_id:
                stmt = stmt.where(Spans.user_id == user_id)
                count_stmt = count_stmt.where(Spans.user_id == user_id)
            if session_id:
                stmt = stmt.where(Spans.session_agent == session_id)
                count_stmt = count_stmt.where(Spans.session_agent == session_id)
            if flow_id:
                cond = _json_text_eq(Spans.attributes, trace_attr.ATTR_FLOW_ID, flow_id)
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

            traces_dict: Dict[str, Dict[str, Any]] = {}
            for span in spans:
                tid = span["trace_id"]
                if tid not in traces_dict:
                    traces_dict[tid] = {"trace_id": tid, "spans": []}
                traces_dict[tid]["spans"].append(span)

            return list(traces_dict.values()), total_count or 0

    async def admin_search_spans(
        self,
        *,
        service_name: Optional[str] = None,
        company_id: Optional[str] = None,
        user_id: Optional[str] = None,
        namespace: Optional[str] = None,
        from_time: Optional[datetime] = None,
        to_time: Optional[datetime] = None,
        company_id_query: Optional[str] = None,
        user_id_query: Optional[str] = None,
        operation_name_query: Optional[str] = None,
        event_type_query: Optional[str] = None,
        namespace_query: Optional[str] = None,
        service_name_query: Optional[str] = None,
        limit: int = 50,
        cursor: Optional[str] = None,
    ) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        from core.db.models import Spans

        if limit < 1:
            raise ValueError("limit должен быть >= 1")
        if limit > ADMIN_SPANS_MAX_LIMIT:
            raise ValueError(f"limit не больше {ADMIN_SPANS_MAX_LIMIT}")

        company_frag = _admin_optional_ilike_param("company_id_query", company_id_query)
        user_frag = _admin_optional_ilike_param("user_id_query", user_id_query)
        op_frag = _admin_optional_ilike_param("operation_name_query", operation_name_query)
        event_frag = _admin_optional_ilike_param("event_type_query", event_type_query)
        namespace_frag: Optional[str] = None
        if namespace is None:
            namespace_frag = _admin_optional_ilike_param("namespace_query", namespace_query)
        service_name_frag: Optional[str] = None
        if service_name is None:
            service_name_frag = _admin_optional_ilike_param("service_name_query", service_name_query)

        async with self._storage._get_session() as session:
            stmt = select(Spans)
            if service_name is not None:
                stmt = stmt.where(Spans.service_name == service_name)
            elif service_name_frag is not None:
                stmt = stmt.where(_admin_ilike(Spans.service_name, service_name_frag))
            if company_id is not None:
                stmt = stmt.where(Spans.company_id == company_id)
            if user_id is not None:
                stmt = stmt.where(Spans.user_id == user_id)
            if namespace is not None:
                stmt = stmt.where(Spans.namespace == namespace)
            elif namespace_frag is not None:
                stmt = stmt.where(_admin_ilike(Spans.namespace, namespace_frag))
            if from_time is not None:
                stmt = stmt.where(Spans.start_time >= from_time)
            if to_time is not None:
                stmt = stmt.where(Spans.start_time <= to_time)
            if company_frag is not None:
                stmt = stmt.where(_admin_ilike(Spans.company_id, company_frag))
            if user_frag is not None:
                stmt = stmt.where(_admin_ilike(Spans.user_id, user_frag))
            if op_frag is not None:
                stmt = stmt.where(_admin_ilike(Spans.operation_name, op_frag))
            if event_frag is not None:
                stmt = stmt.where(_admin_ilike(Spans.event_type, event_frag))
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
            next_cursor: Optional[str] = None
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
    ) -> List[Dict[str, Any]]:
        """
        Spans с platform.billing.resource_name и platform.billing.pending_settlement=true
        за полуинтервал [from_time, to_time), по возрастанию start_time (для джобы списания).
        """
        from core.db.models import Spans

        if limit < 1:
            raise ValueError("limit должен быть >= 1")
        if from_time.tzinfo is None or to_time.tzinfo is None:
            raise ValueError("from_time и to_time обязаны иметь timezone")

        res_txt = Spans.attributes[trace_attr.ATTR_BILLING_RESOURCE_NAME].astext
        pend_txt = Spans.attributes[trace_attr.ATTR_BILLING_PENDING_SETTLEMENT].astext

        async with self._storage._get_session() as session:
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
            return [self._serialize_span(row) for row in rows]

    async def admin_facet_distinct_company_ids(
        self, *, q: Optional[str] = None, limit: int = ADMIN_FACETS_MAX_LIMIT
    ) -> List[str]:
        from core.db.models import Spans

        if limit < 1 or limit > ADMIN_FACETS_MAX_LIMIT:
            raise ValueError(f"limit должен быть от 1 до {ADMIN_FACETS_MAX_LIMIT}")
        frag = _facet_query_fragment(q)
        async with self._storage._get_session() as session:
            stmt = select(Spans.company_id).where(Spans.company_id.isnot(None))
            if frag is not None:
                stmt = stmt.where(_admin_ilike(Spans.company_id, frag))
            stmt = stmt.distinct().order_by(Spans.company_id.asc()).limit(limit)
            result = await session.execute(stmt)
            return [row[0] for row in result.all() if row[0] is not None]

    async def admin_facet_distinct_user_ids(
        self,
        *,
        q: Optional[str] = None,
        company_id: Optional[str] = None,
        namespace: Optional[str] = None,
        limit: int = ADMIN_FACETS_MAX_LIMIT,
    ) -> List[str]:
        from core.db.models import Spans

        if limit < 1 or limit > ADMIN_FACETS_MAX_LIMIT:
            raise ValueError(f"limit должен быть от 1 до {ADMIN_FACETS_MAX_LIMIT}")
        frag = _facet_query_fragment(q)
        scope_co = _admin_facet_scope_company(company_id)
        scope_ns = _admin_facet_scope_namespace(namespace)
        async with self._storage._get_session() as session:
            stmt = select(Spans.user_id).where(Spans.user_id.isnot(None))
            if scope_co is not None:
                stmt = stmt.where(Spans.company_id == scope_co)
            if scope_ns is not None:
                stmt = stmt.where(Spans.namespace == scope_ns)
            if frag is not None:
                stmt = stmt.where(_admin_ilike(Spans.user_id, frag))
            stmt = stmt.distinct().order_by(Spans.user_id.asc()).limit(limit)
            result = await session.execute(stmt)
            return [row[0] for row in result.all() if row[0] is not None]

    async def admin_facet_distinct_service_names(
        self,
        *,
        q: Optional[str] = None,
        company_id: Optional[str] = None,
        namespace: Optional[str] = None,
        limit: int = ADMIN_FACETS_MAX_LIMIT,
    ) -> List[str]:
        from core.db.models import Spans

        if limit < 1 or limit > ADMIN_FACETS_MAX_LIMIT:
            raise ValueError(f"limit должен быть от 1 до {ADMIN_FACETS_MAX_LIMIT}")
        frag = _facet_query_fragment(q)
        scope_co = _admin_facet_scope_company(company_id)
        scope_ns = _admin_facet_scope_namespace(namespace)
        async with self._storage._get_session() as session:
            stmt = select(Spans.service_name).where(Spans.service_name.isnot(None))
            if scope_co is not None:
                stmt = stmt.where(Spans.company_id == scope_co)
            if scope_ns is not None:
                stmt = stmt.where(Spans.namespace == scope_ns)
            if frag is not None:
                stmt = stmt.where(_admin_ilike(Spans.service_name, frag))
            stmt = stmt.distinct().order_by(Spans.service_name.asc()).limit(limit)
            result = await session.execute(stmt)
            return [row[0] for row in result.all() if row[0] is not None]

    async def admin_facet_distinct_event_types(
        self,
        *,
        q: Optional[str] = None,
        company_id: Optional[str] = None,
        namespace: Optional[str] = None,
        limit: int = ADMIN_FACETS_MAX_LIMIT,
    ) -> List[str]:
        from core.db.models import Spans

        if limit < 1 or limit > ADMIN_FACETS_MAX_LIMIT:
            raise ValueError(f"limit должен быть от 1 до {ADMIN_FACETS_MAX_LIMIT}")
        frag = _facet_query_fragment(q)
        scope_co = _admin_facet_scope_company(company_id)
        scope_ns = _admin_facet_scope_namespace(namespace)
        async with self._storage._get_session() as session:
            stmt = select(Spans.event_type).where(Spans.event_type.isnot(None))
            if scope_co is not None:
                stmt = stmt.where(Spans.company_id == scope_co)
            if scope_ns is not None:
                stmt = stmt.where(Spans.namespace == scope_ns)
            if frag is not None:
                stmt = stmt.where(_admin_ilike(Spans.event_type, frag))
            stmt = stmt.distinct().order_by(Spans.event_type.asc()).limit(limit)
            result = await session.execute(stmt)
            return [row[0] for row in result.all() if row[0] is not None]

    async def admin_facet_distinct_namespaces(
        self,
        *,
        q: Optional[str] = None,
        company_id: Optional[str] = None,
        limit: int = ADMIN_FACETS_MAX_LIMIT,
    ) -> List[str]:
        from core.db.models import Spans

        if limit < 1 or limit > ADMIN_FACETS_MAX_LIMIT:
            raise ValueError(f"limit должен быть от 1 до {ADMIN_FACETS_MAX_LIMIT}")
        frag = _facet_query_fragment(q)
        scope_co = _admin_facet_scope_company(company_id)
        async with self._storage._get_session() as session:
            stmt = select(Spans.namespace).where(Spans.namespace.isnot(None))
            if scope_co is not None:
                stmt = stmt.where(Spans.company_id == scope_co)
            if frag is not None:
                stmt = stmt.where(_admin_ilike(Spans.namespace, frag))
            stmt = stmt.distinct().order_by(Spans.namespace.asc()).limit(limit)
            result = await session.execute(stmt)
            return [row[0] for row in result.all() if row[0] is not None]

    async def admin_facet_distinct_operation_names(
        self,
        *,
        q: Optional[str] = None,
        company_id: Optional[str] = None,
        namespace: Optional[str] = None,
        limit: int = ADMIN_FACETS_MAX_LIMIT,
    ) -> List[str]:
        from core.db.models import Spans

        if limit < 1 or limit > ADMIN_FACETS_MAX_LIMIT:
            raise ValueError(f"limit должен быть от 1 до {ADMIN_FACETS_MAX_LIMIT}")
        frag = _facet_query_fragment(q)
        scope_co = _admin_facet_scope_company(company_id)
        scope_ns = _admin_facet_scope_namespace(namespace)
        async with self._storage._get_session() as session:
            stmt = select(Spans.operation_name).where(Spans.operation_name.isnot(None))
            if scope_co is not None:
                stmt = stmt.where(Spans.company_id == scope_co)
            if scope_ns is not None:
                stmt = stmt.where(Spans.namespace == scope_ns)
            if frag is not None:
                stmt = stmt.where(_admin_ilike(Spans.operation_name, frag))
            stmt = stmt.distinct().order_by(Spans.operation_name.asc()).limit(limit)
            result = await session.execute(stmt)
            return [row[0] for row in result.all() if row[0] is not None]

    def _serialize_span(self, row: Any) -> Dict[str, Any]:
        raw_attrs = row.attributes or {}
        return {
            "span_id": row.span_id,
            "trace_id": row.trace_id,
            "parent_span_id": row.parent_span_id,
            "operation_name": row.operation_name,
            "kind": row.kind,
            "start_time": row.start_time.isoformat() if row.start_time else None,
            "end_time": row.end_time.isoformat() if row.end_time else None,
            "duration_ms": row.duration_ms,
            "status": row.status,
            "status_message": row.status_message,
            "service_name": row.service_name,
            "company_id": row.company_id,
            "namespace": row.namespace,
            "user_id": row.user_id,
            "user_name": row.user_name,
            "user_groups": row.user_groups,
            "session_auth": row.session_auth,
            "session_agent": row.session_agent,
            "channel": row.channel,
            "event_type": row.event_type,
            "resource_type": row.resource_type,
            "resource_id": row.resource_id,
            "flow_id": raw_attrs.get(trace_attr.ATTR_FLOW_ID),
            "task_id": raw_attrs.get(trace_attr.ATTR_TASK_ID),
            "context_id": raw_attrs.get(trace_attr.ATTR_CONTEXT_ID),
            "skill_id": raw_attrs.get(trace_attr.ATTR_SKILL_ID),
            "node_id": raw_attrs.get(trace_attr.ATTR_NODE_ID),
            "agent_name": raw_attrs.get(trace_attr.ATTR_AGENT_NAME),
            "is_resume": raw_attrs.get(trace_attr.ATTR_IS_RESUME),
            "attributes": raw_attrs,
            "events": row.events or [],
        }
