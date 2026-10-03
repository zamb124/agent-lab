"""Доменные модели platform tracing."""

from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from typing import ClassVar, Literal

from oxyde import Field as DbField
from oxyde import Index, Query, execute_raw
from oxyde.exceptions import IntegrityError
from pydantic import BaseModel, ConfigDict, Field, computed_field

import core.tracing.attributes as trace_attr
from core.models.billing_models import BillingCostOrigin, UsageType
from core.models.platform_model import PlatformModel
from core.tracing.facet_query import (
    ADMIN_FACETS_MAX_LIMIT,
    MIN_ADMIN_ILIKE_LEN,
    facet_query_fragment,
)
from core.types import JsonObject, JsonValue, parse_json_object, require_json_object


class TraceSpanEvent(BaseModel):
    """OpenTelemetry event внутри сохраненного span."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", strict=True)

    name: str
    timestamp: str | None = None
    attributes: JsonObject = Field(default_factory=dict)

    def to_json_object(self) -> JsonObject:
        return {
            "name": self.name,
            "timestamp": self.timestamp,
            "attributes": self.attributes,
        }


ADMIN_SPANS_MAX_LIMIT = 100

_STATUS_MESSAGE_MAX_LEN = 255

_FacetColumn = Literal[
    "company_id",
    "user_id",
    "service_name",
    "event_type",
    "namespace",
    "operation_name",
]
_SearchParam = str | datetime | int


def _encode_service_list_cursor(start_time: datetime, span_id: str) -> str:
    if start_time.tzinfo is None:
        start_time = start_time.replace(tzinfo=timezone.utc)
    payload = {"t": start_time.isoformat(), "s": span_id}
    raw = json.dumps(payload, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode_service_list_cursor(cursor: str) -> tuple[datetime, str]:
    pad = "=" * (-len(cursor) % 4)
    raw = base64.urlsafe_b64decode(cursor + pad)
    payload = parse_json_object(raw.decode(), "cursor")
    raw_time = payload.get("t")
    if not isinstance(raw_time, str):
        raise ValueError("cursor.t must be a string")
    raw_span_id = payload.get("s")
    if not isinstance(raw_span_id, str):
        raise ValueError("cursor.s must be a string")
    t = datetime.fromisoformat(raw_time)
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return t, raw_span_id


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


def _admin_facet_scope(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    if stripped == "":
        return None
    return stripped


def _like_fragment(fragment: str) -> str:
    escaped = fragment.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


async def _page_older_than(query: Query[Span], cursor: str | None, limit: int) -> list[Span]:
    if cursor is None:
        return await query.order_by("-start_time", "-span_id").limit(limit).all()
    try:
        cursor_time, cursor_span_id = _decode_service_list_cursor(cursor)
    except (json.JSONDecodeError, KeyError, ValueError) as exc:
        raise ValueError(f"Invalid cursor: {exc}") from exc
    same_time = await query.filter(start_time=cursor_time).order_by("-span_id").all()
    tie = [row for row in same_time if row.span_id < cursor_span_id]
    if len(tie) >= limit:
        return tie[:limit]
    older = await (
        query.filter(start_time__lt=cursor_time)
        .order_by("-start_time", "-span_id")
        .limit(limit - len(tie))
        .all()
    )
    return [*tie, *older]


def _next_cursor(rows: list[Span], limit: int) -> str | None:
    if len(rows) != limit:
        return None
    last = rows[-1]
    return _encode_service_list_cursor(last.start_time, last.span_id)


def _span_from_row(row: JsonObject) -> Span:
    raw_span = row["span"]
    if isinstance(raw_span, str):
        payload = parse_json_object(raw_span, "span")
    else:
        payload = require_json_object(raw_span, "span")
    return Span.model_validate(payload)






def _json_value_to_non_negative_int(value: JsonValue, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be an integer")
    if isinstance(value, int):
        quantity = value
    elif isinstance(value, float):
        if not value.is_integer():
            raise ValueError(f"{field_name} must be an integer")
        quantity = int(value)
    elif isinstance(value, str):
        quantity = int(value)
    else:
        raise ValueError(f"{field_name} must be an integer")
    if quantity < 0:
        raise ValueError(f"{field_name} must be >= 0")
    return quantity


class Span(PlatformModel):
    """OpenTelemetry Span для хранения в platform_tracing.spans."""

    __database_alias__: ClassVar[str | None] = "tracing"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "spans"
        indexes: list[Index] = [
            Index(["company_id", "resource_type", "resource_id", "start_time"]),
            Index(["trace_id"]),
            Index(["start_time"]),
            Index(["service_name"]),
            Index(["parent_span_id"]),
            Index(["company_id"]),
            Index(["namespace"]),
            Index(["user_id"]),
            Index(["session_auth"]),
            Index(["session_agent"]),
            Index(["event_type"]),
            Index(["resource_type"]),
            Index(["resource_id"]),
        ]

    span_id: str = DbField(db_pk=True)
    trace_id: str = DbField()
    operation_name: str = DbField()
    start_time: datetime = DbField()
    service_name: str = DbField()
    parent_span_id: str | None = DbField(default=None)
    kind: str | None = DbField(default=None)
    end_time: datetime | None = DbField(default=None)
    duration_ms: int | None = DbField(default=None)
    status: str | None = DbField(default=None)
    status_message: str | None = DbField(default=None)
    company_id: str | None = DbField(default=None)
    namespace: str | None = DbField(default=None)
    user_id: str | None = DbField(default=None)
    user_name: str | None = DbField(default=None)
    user_groups: list[str] | None = DbField(default=None, db_type="JSONB")
    session_auth: str | None = DbField(default=None)
    session_agent: str | None = DbField(default=None)
    channel: str | None = DbField(default=None)
    event_type: str | None = DbField(default=None)
    resource_type: str | None = DbField(default=None)
    resource_id: str | None = DbField(default=None)
    attributes: JsonObject = DbField(default_factory=dict, db_type="JSONB")
    events: list[TraceSpanEvent] = DbField(default_factory=list, db_type="JSONB")

    def _attribute_text(self, key: str) -> str | None:
        value = self.attributes.get(key)
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError(f"span {self.span_id}: {key} must be a string")
        return value

    @computed_field
    @property
    def flow_id(self) -> str | None:
        return self._attribute_text(trace_attr.ATTR_FLOW_ID)

    @computed_field
    @property
    def task_id(self) -> str | None:
        return self._attribute_text(trace_attr.ATTR_TASK_ID)

    @computed_field
    @property
    def context_id(self) -> str | None:
        return self._attribute_text(trace_attr.ATTR_CONTEXT_ID)

    @computed_field
    @property
    def branch_id(self) -> str | None:
        return self._attribute_text(trace_attr.ATTR_BRANCH_ID)

    @computed_field
    @property
    def node_id(self) -> str | None:
        return self._attribute_text(trace_attr.ATTR_NODE_ID)

    @computed_field
    @property
    def agent_name(self) -> str | None:
        return self._attribute_text(trace_attr.ATTR_AGENT_NAME)

    @computed_field
    @property
    def is_resume(self) -> bool | None:
        value = self.attributes.get(trace_attr.ATTR_IS_RESUME)
        if value is None:
            return None
        if isinstance(value, bool):
            return value
        raise ValueError(f"span {self.span_id}: {trace_attr.ATTR_IS_RESUME} must be a bool")

    def to_json_object(self) -> JsonObject:
        return {
            "span_id": self.span_id,
            "trace_id": self.trace_id,
            "parent_span_id": self.parent_span_id,
            "operation_name": self.operation_name,
            "kind": self.kind,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time is not None else None,
            "duration_ms": self.duration_ms,
            "status": self.status,
            "status_message": self.status_message,
            "service_name": self.service_name,
            "company_id": self.company_id,
            "namespace": self.namespace,
            "user_id": self.user_id,
            "user_name": self.user_name,
            "user_groups": self.user_groups,
            "session_auth": self.session_auth,
            "session_agent": self.session_agent,
            "channel": self.channel,
            "event_type": self.event_type,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "flow_id": self.flow_id,
            "task_id": self.task_id,
            "context_id": self.context_id,
            "branch_id": self.branch_id,
            "node_id": self.node_id,
            "agent_name": self.agent_name,
            "is_resume": self.is_resume,
            "attributes": self.attributes,
            "events": [event.to_json_object() for event in self.events],
        }

    def required_billing_resource_name(self) -> str:
        value = self.attributes.get(trace_attr.ATTR_BILLING_RESOURCE_NAME)
        if not isinstance(value, str) or not value:
            raise ValueError(f"span {self.span_id}: missing {trace_attr.ATTR_BILLING_RESOURCE_NAME}")
        return value

    def billing_usage_type_or_default(self) -> UsageType:
        value = self.attributes.get(trace_attr.ATTR_BILLING_USAGE_TYPE)
        if value is None or value == "":
            return UsageType.TOOL_CALL
        if not isinstance(value, str):
            raise ValueError(f"span {self.span_id}: {trace_attr.ATTR_BILLING_USAGE_TYPE} must be a string")
        try:
            return UsageType(value)
        except ValueError as exc:
            raise ValueError(f"span {self.span_id}: unknown UsageType {value!r}") from exc

    def billing_quantity_or_default(self) -> int:
        value = self.attributes.get(trace_attr.ATTR_BILLING_QUANTITY)
        if value is None:
            return 1
        quantity = _json_value_to_non_negative_int(value, trace_attr.ATTR_BILLING_QUANTITY)
        if quantity < 1:
            raise ValueError(f"span {self.span_id}: platform.billing.quantity must be >= 1")
        return quantity

    def billing_cost_origin_or_default(self) -> BillingCostOrigin:
        value = self.attributes.get(trace_attr.ATTR_BILLING_COST_ORIGIN)
        if value is None or value == "":
            return "platform"
        if not isinstance(value, str):
            raise ValueError(f"span {self.span_id}: unknown cost_origin {value!r}")
        if value == "platform":
            return "platform"
        if value == "company":
            return "company"
        raise ValueError(f"span {self.span_id}: unknown cost_origin {value!r}")

    def billing_custom_provider_id(self) -> str | None:
        value = self.attributes.get(trace_attr.ATTR_BILLING_CUSTOM_PROVIDER_ID)
        if value is None:
            return None
        if not isinstance(value, str) or not value:
            raise ValueError(f"span {self.span_id}: {trace_attr.ATTR_BILLING_CUSTOM_PROVIDER_ID} must be a string")
        return value

    @classmethod
    async def insert_once(cls, span: Span) -> None:
        if span.service_name == "":
            raise ValueError("span.service_name is required to persist the span")
        attributes: JsonObject = dict(span.attributes)
        if span.event_type is not None and trace_attr.ATTR_EVENT_TYPE not in attributes:
            attributes[trace_attr.ATTR_EVENT_TYPE] = span.event_type
        if span.resource_type is not None and trace_attr.ATTR_RESOURCE_TYPE not in attributes:
            attributes[trace_attr.ATTR_RESOURCE_TYPE] = span.resource_type
        if span.resource_id is not None and trace_attr.ATTR_RESOURCE_ID not in attributes:
            attributes[trace_attr.ATTR_RESOURCE_ID] = span.resource_id
        status_message = span.status_message
        if status_message is not None and len(status_message) > _STATUS_MESSAGE_MAX_LEN:
            status_message = status_message[: _STATUS_MESSAGE_MAX_LEN]
        stored = span.model_copy(
            update={"attributes": attributes, "status_message": status_message}
        )
        try:
            _ = await Span.objects.create(instance=stored)
        except IntegrityError:
            existing = await Span.objects.filter(span_id=span.span_id).first()
            if existing is None:
                raise

    @classmethod
    async def list_spans_for_service(
        cls,
        *,
        service_name: str,
        company_id: str | None = None,
        namespace: str | None = None,
        operation_name: str | None = None,
        event_type: str | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> tuple[list[Span], str | None]:
        """Список spans сервиса. Сортировка: start_time DESC, span_id DESC."""
        if limit < 1:
            raise ValueError("limit must be >= 1")
        query = Span.objects.filter(service_name=service_name)
        if company_id is not None:
            query = query.filter(company_id=company_id)
        if namespace is not None:
            query = query.filter(namespace=namespace)
        if operation_name is not None:
            query = query.filter(operation_name=operation_name)
        if event_type is not None:
            query = query.filter(event_type=event_type)
        rows = await _page_older_than(query, cursor, limit)
        return rows, _next_cursor(rows, limit)

    @classmethod
    async def list_spans_for_resource(
        cls,
        *,
        company_id: str,
        resource_type: str,
        resource_id: str,
        event_type: str | None = None,
        limit: int = 100,
    ) -> list[Span]:
        """Хронология событий по сущности (чат, заметка, документ и т.д.)."""
        query = Span.objects.filter(
            company_id=company_id,
            resource_type=resource_type,
            resource_id=resource_id,
        )
        if event_type is not None:
            query = query.filter(event_type=event_type)
        return await query.order_by("-start_time").limit(limit).all()

    @classmethod
    async def list_for_trace(cls, trace_id: str) -> list[Span]:
        return await Span.objects.filter(trace_id=trace_id).order_by("start_time").all()

    @classmethod
    async def list_by_task_id(cls, task_id: str) -> list[Span]:
        return await Span._load_spans(
            """
            SELECT row_to_json(spans) AS span
            FROM spans
            WHERE attributes->>$1 = $2
            ORDER BY start_time ASC
            """,
            [trace_attr.ATTR_TASK_ID, task_id],
        )

    @classmethod
    async def list_by_session_agent(
        cls,
        session_agent: str,
        limit: int = 100,
    ) -> list[Span]:
        return await (
            Span.objects.filter(session_agent=session_agent)
            .order_by("-start_time")
            .limit(limit)
            .all()
        )

    @classmethod
    async def list_by_user_id(
        cls,
        user_id: str,
        from_time: datetime | None = None,
        to_time: datetime | None = None,
        limit: int = 100,
    ) -> list[Span]:
        query = Span.objects.filter(user_id=user_id)
        if from_time is not None:
            query = query.filter(start_time__gte=from_time)
        if to_time is not None:
            query = query.filter(start_time__lte=to_time)
        return await query.order_by("-start_time").limit(limit).all()

    @classmethod
    async def list_by_flow_id(
        cls,
        flow_id: str,
        from_time: datetime | None = None,
        to_time: datetime | None = None,
        limit: int = 100,
    ) -> list[Span]:
        clauses = ["attributes->>$1 = $2"]
        params: list[_SearchParam] = [trace_attr.ATTR_FLOW_ID, flow_id]
        if from_time is not None:
            params.append(from_time)
            clauses.append(f"start_time >= ${len(params)}")
        if to_time is not None:
            params.append(to_time)
            clauses.append(f"start_time <= ${len(params)}")
        params.append(limit)
        return await Span._load_spans(
            f"""
            SELECT row_to_json(spans) AS span
            FROM spans
            WHERE {' AND '.join(clauses)}
            ORDER BY start_time DESC
            LIMIT ${len(params)}
            """,
            params,
        )

    @classmethod
    async def search_traces(
        cls,
        user_id: str | None = None,
        session_id: str | None = None,
        flow_id: str | None = None,
        task_id: str | None = None,
        from_time: datetime | None = None,
        to_time: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[TraceSearchResult], int]:
        clauses = ["TRUE"]
        params: list[_SearchParam] = []
        if user_id is not None:
            params.append(user_id)
            clauses.append(f"user_id = ${len(params)}")
        if session_id is not None:
            params.append(session_id)
            clauses.append(f"session_agent = ${len(params)}")
        if flow_id is not None:
            params.append(trace_attr.ATTR_FLOW_ID)
            key_index = len(params)
            params.append(flow_id)
            clauses.append(f"attributes->>${key_index} = ${len(params)}")
        if task_id is not None:
            params.append(trace_attr.ATTR_TASK_ID)
            key_index = len(params)
            params.append(task_id)
            clauses.append(f"attributes->>${key_index} = ${len(params)}")
        if from_time is not None:
            params.append(from_time)
            clauses.append(f"start_time >= ${len(params)}")
        if to_time is not None:
            params.append(to_time)
            clauses.append(f"start_time <= ${len(params)}")
        where = " AND ".join(clauses)
        count_rows = await execute_raw(
            f"SELECT COUNT(*) AS total FROM spans WHERE {where}",
            params,
            using="tracing",
        )
        if len(count_rows) != 1:
            raise RuntimeError("span search count must return one row")
        total_cell = require_json_object(count_rows[0], "span_count")["total"]
        if isinstance(total_cell, bool) or not isinstance(total_cell, int):
            raise TypeError("span search count must be an integer")
        page_params = [*params, limit, offset]
        spans = await Span._load_spans(
            f"""
            SELECT row_to_json(spans) AS span
            FROM spans
            WHERE {where}
            ORDER BY start_time DESC
            LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}
            """,
            page_params,
        )
        grouped: dict[str, list[Span]] = {}
        for span in spans:
            grouped.setdefault(span.trace_id, []).append(span)
        return [
            TraceSearchResult(trace_id=trace_id, spans=trace_spans)
            for trace_id, trace_spans in grouped.items()
        ], total_cell

    @classmethod
    async def admin_search_spans(
        cls,
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
    ) -> tuple[list[Span], str | None]:
        if limit < 1:
            raise ValueError("limit must be >= 1")
        if limit > ADMIN_SPANS_MAX_LIMIT:
            raise ValueError(f"limit must not exceed {ADMIN_SPANS_MAX_LIMIT}")
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
        query = Span.objects.filter()
        if service_name is not None:
            query = query.filter(service_name=service_name)
        elif service_name_frag is not None:
            query = query.filter(service_name__icontains=service_name_frag)
        if company_id is not None:
            query = query.filter(company_id=company_id)
        if user_id is not None:
            query = query.filter(user_id=user_id)
        if namespace is not None:
            query = query.filter(namespace=namespace)
        elif namespace_frag is not None:
            query = query.filter(namespace__icontains=namespace_frag)
        if from_time is not None:
            query = query.filter(start_time__gte=from_time)
        if to_time is not None:
            query = query.filter(start_time__lte=to_time)
        if company_frag is not None:
            query = query.filter(company_id__icontains=company_frag)
        if user_frag is not None:
            query = query.filter(user_id__icontains=user_frag)
        if op_frag is not None:
            query = query.filter(operation_name__icontains=op_frag)
        if event_frag is not None:
            query = query.filter(event_type__icontains=event_frag)
        rows = await _page_older_than(query, cursor, limit)
        return rows, _next_cursor(rows, limit)

    @classmethod
    async def list_spans_pending_billing_settlement(
        cls,
        *,
        from_time: datetime,
        to_time: datetime,
        limit: int,
        company_id: str | None = None,
    ) -> list[Span]:
        """
        Spans с platform.billing.resource_name и platform.billing.pending_settlement=true
        за полуинтервал [from_time, to_time), по возрастанию start_time.
        """
        if limit < 1:
            raise ValueError("limit must be >= 1")
        if from_time.tzinfo is None or to_time.tzinfo is None:
            raise ValueError("from_time and to_time must have a timezone")
        clauses = [
            "start_time >= $1",
            "start_time < $2",
            "attributes->>$3 IS NOT NULL",
            "attributes->>$3 <> ''",
            "(attributes->>$4 IN ('true', 'True', '1') OR (attributes->>$4)::boolean IS TRUE)",
        ]
        params: list[_SearchParam] = [
            from_time,
            to_time,
            trace_attr.ATTR_BILLING_RESOURCE_NAME,
            trace_attr.ATTR_BILLING_PENDING_SETTLEMENT,
        ]
        if company_id is not None:
            params.append(company_id)
            clauses.append(f"company_id = ${len(params)}")
        params.append(limit)
        return await Span._load_spans(
            f"""
            SELECT row_to_json(spans) AS span
            FROM spans
            WHERE {' AND '.join(clauses)}
            ORDER BY start_time ASC, span_id ASC
            LIMIT ${len(params)}
            """,
            params,
        )

    @classmethod
    async def admin_facet_distinct_company_ids(
        cls, *, q: str | None = None, limit: int = ADMIN_FACETS_MAX_LIMIT
    ) -> list[str]:
        if limit < 1 or limit > ADMIN_FACETS_MAX_LIMIT:
            raise ValueError(f"limit must be between 1 and {ADMIN_FACETS_MAX_LIMIT}")
        return await Span._distinct_column(
            "company_id",
            fragment=facet_query_fragment(q),
            company_id=None,
            namespace=None,
            limit=limit,
        )

    @classmethod
    async def admin_list_distinct_company_ids_in_spans(cls, *, max_ids: int = 5000) -> list[str]:
        """Distinct company_id, для которых есть spans."""
        if max_ids < 1 or max_ids > 50_000:
            raise ValueError("max_ids must be between 1 and 50000")
        return await Span._distinct_column(
            "company_id",
            fragment=None,
            company_id=None,
            namespace=None,
            limit=max_ids,
        )

    @classmethod
    async def company_has_spans(cls, company_id: str) -> bool:
        if company_id.strip() == "":
            raise ValueError("company_id is required")
        rows = await execute_raw(
            "SELECT 1 AS hit FROM spans WHERE company_id = $1 LIMIT 1",
            [company_id],
            using="tracing",
        )
        return len(rows) > 0

    @classmethod
    async def admin_facet_distinct_user_ids(
        cls,
        *,
        q: str | None = None,
        company_id: str | None = None,
        namespace: str | None = None,
        limit: int = ADMIN_FACETS_MAX_LIMIT,
    ) -> list[str]:
        if limit < 1 or limit > ADMIN_FACETS_MAX_LIMIT:
            raise ValueError(f"limit must be between 1 and {ADMIN_FACETS_MAX_LIMIT}")
        return await Span._distinct_column(
            "user_id",
            fragment=facet_query_fragment(q),
            company_id=_admin_facet_scope(company_id),
            namespace=_admin_facet_scope(namespace),
            limit=limit,
        )

    @classmethod
    async def admin_list_distinct_user_ids_in_spans(
        cls,
        *,
        max_ids: int = 5000,
        company_id: str | None = None,
        namespace: str | None = None,
    ) -> list[str]:
        """Distinct user_id, для которых есть spans."""
        if max_ids < 1 or max_ids > 50_000:
            raise ValueError("max_ids must be between 1 and 50000")
        return await Span._distinct_column(
            "user_id",
            fragment=None,
            company_id=_admin_facet_scope(company_id),
            namespace=_admin_facet_scope(namespace),
            limit=max_ids,
        )

    @classmethod
    async def admin_facet_distinct_service_names(
        cls,
        *,
        q: str | None = None,
        company_id: str | None = None,
        namespace: str | None = None,
        limit: int = ADMIN_FACETS_MAX_LIMIT,
    ) -> list[str]:
        if limit < 1 or limit > ADMIN_FACETS_MAX_LIMIT:
            raise ValueError(f"limit must be between 1 and {ADMIN_FACETS_MAX_LIMIT}")
        return await Span._distinct_column(
            "service_name",
            fragment=facet_query_fragment(q),
            company_id=_admin_facet_scope(company_id),
            namespace=_admin_facet_scope(namespace),
            limit=limit,
        )

    @classmethod
    async def admin_facet_distinct_event_types(
        cls,
        *,
        q: str | None = None,
        company_id: str | None = None,
        namespace: str | None = None,
        limit: int = ADMIN_FACETS_MAX_LIMIT,
    ) -> list[str]:
        if limit < 1 or limit > ADMIN_FACETS_MAX_LIMIT:
            raise ValueError(f"limit must be between 1 and {ADMIN_FACETS_MAX_LIMIT}")
        return await Span._distinct_column(
            "event_type",
            fragment=facet_query_fragment(q),
            company_id=_admin_facet_scope(company_id),
            namespace=_admin_facet_scope(namespace),
            limit=limit,
        )

    @classmethod
    async def admin_facet_distinct_namespaces(
        cls,
        *,
        q: str | None = None,
        company_id: str | None = None,
        limit: int = ADMIN_FACETS_MAX_LIMIT,
    ) -> list[str]:
        if limit < 1 or limit > ADMIN_FACETS_MAX_LIMIT:
            raise ValueError(f"limit must be between 1 and {ADMIN_FACETS_MAX_LIMIT}")
        return await Span._distinct_column(
            "namespace",
            fragment=facet_query_fragment(q),
            company_id=_admin_facet_scope(company_id),
            namespace=None,
            limit=limit,
        )

    @classmethod
    async def admin_facet_distinct_operation_names(
        cls,
        *,
        q: str | None = None,
        company_id: str | None = None,
        namespace: str | None = None,
        limit: int = ADMIN_FACETS_MAX_LIMIT,
    ) -> list[str]:
        if limit < 1 or limit > ADMIN_FACETS_MAX_LIMIT:
            raise ValueError(f"limit must be between 1 and {ADMIN_FACETS_MAX_LIMIT}")
        return await Span._distinct_column(
            "operation_name",
            fragment=facet_query_fragment(q),
            company_id=_admin_facet_scope(company_id),
            namespace=_admin_facet_scope(namespace),
            limit=limit,
        )

    @classmethod
    async def _load_spans(cls, sql: str, params: list[_SearchParam]) -> list[Span]:
        rows = await execute_raw(sql, params, using="tracing")
        spans: list[Span] = []
        for row in rows:
            spans.append(_span_from_row(require_json_object(row, "span")))
        return spans

    @classmethod
    async def _distinct_column(
        cls,
        column: _FacetColumn,
        *,
        fragment: str | None,
        company_id: str | None,
        namespace: str | None,
        limit: int,
    ) -> list[str]:
        clauses = [f"{column} IS NOT NULL"]
        params: list[str | int] = []
        if company_id is not None:
            params.append(company_id)
            clauses.append(f"company_id = ${len(params)}")
        if namespace is not None:
            params.append(namespace)
            clauses.append(f"namespace = ${len(params)}")
        if fragment is not None:
            params.append(_like_fragment(fragment))
            clauses.append(f"{column} ILIKE ${len(params)} ESCAPE '\\'")
        params.append(limit)
        sql = (
            f"SELECT DISTINCT {column} AS facet_value FROM spans "
            f"WHERE {' AND '.join(clauses)} "
            f"ORDER BY {column} ASC LIMIT ${len(params)}"
        )
        rows = await execute_raw(sql, params, using="tracing")
        values: list[str] = []
        for row in rows:
            parsed = require_json_object(row, "span_facet")
            cell = parsed["facet_value"]
            if not isinstance(cell, str):
                raise TypeError(f"spans.{column} facet_value must be a string")
            values.append(cell)
        return values


class TraceSearchResult(BaseModel):
    """Группа spans одного trace_id."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", strict=True)

    trace_id: str
    spans: list[Span] = Field(default_factory=list)

    def to_json_object(self) -> JsonObject:
        return {
            "trace_id": self.trace_id,
            "spans": [span.to_json_object() for span in self.spans],
        }
