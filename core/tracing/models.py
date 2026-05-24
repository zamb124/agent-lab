"""Доменные модели platform tracing."""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

import core.tracing.attributes as trace_attr
from core.models.billing_models import BillingCostOrigin, UsageType
from core.types import JsonArray, JsonObject, JsonValue


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


class TraceSpanWrite(BaseModel):
    """Span перед записью в platform_tracing.spans."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", strict=True)

    span_id: str
    trace_id: str
    parent_span_id: str | None = None
    operation_name: str
    kind: str | None = None
    start_time: datetime
    end_time: datetime | None = None
    duration_ms: int | None = None
    status: str | None = None
    status_message: str | None = None
    service_name: str
    company_id: str | None = None
    namespace: str | None = None
    user_id: str | None = None
    user_name: str | None = None
    user_groups: list[str] | None = None
    session_auth: str | None = None
    session_agent: str | None = None
    channel: str | None = None
    event_type: str | None = None
    resource_type: str | None = None
    resource_id: str | None = None
    attributes: JsonObject = Field(default_factory=dict)
    events: list[TraceSpanEvent] = Field(default_factory=list)

    def events_json_array(self) -> JsonArray:
        return [event.to_json_object() for event in self.events]


class TraceSpanRecord(TraceSpanWrite):
    """Span из platform_tracing.spans с индексируемыми доменными атрибутами."""

    flow_id: str | None = None
    task_id: str | None = None
    context_id: str | None = None
    branch_id: str | None = None
    node_id: str | None = None
    agent_name: str | None = None
    is_resume: bool | None = None

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
            "events": self.events_json_array(),
        }


class TraceSearchResult(BaseModel):
    """Группа spans одного trace_id."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", strict=True)

    trace_id: str
    spans: list[TraceSpanRecord] = Field(default_factory=list)

    def to_json_object(self) -> JsonObject:
        return {
            "trace_id": self.trace_id,
            "spans": [span.to_json_object() for span in self.spans],
        }


class BillingSettlementSpan(BaseModel):
    """Span, пригодный для фонового billing settlement."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", strict=True)

    span_id: str
    trace_id: str
    operation_name: str
    service_name: str
    company_id: str | None = None
    user_id: str | None = None
    event_type: str | None = None
    attributes: JsonObject = Field(default_factory=dict)

    def required_billing_resource_name(self) -> str:
        value = self.attributes.get(trace_attr.ATTR_BILLING_RESOURCE_NAME)
        if not isinstance(value, str) or not value:
            raise ValueError(f"span {self.span_id}: отсутствует {trace_attr.ATTR_BILLING_RESOURCE_NAME}")
        return value

    def billing_usage_type_or_default(self) -> UsageType:
        value = self.attributes.get(trace_attr.ATTR_BILLING_USAGE_TYPE)
        if value is None or value == "":
            return UsageType.TOOL_CALL
        if not isinstance(value, str):
            raise ValueError(f"span {self.span_id}: {trace_attr.ATTR_BILLING_USAGE_TYPE} должен быть строкой")
        try:
            return UsageType(value)
        except ValueError as exc:
            raise ValueError(f"span {self.span_id}: неизвестный UsageType {value!r}") from exc

    def billing_quantity_or_default(self) -> int:
        value = self.attributes.get(trace_attr.ATTR_BILLING_QUANTITY)
        if value is None:
            return 1
        quantity = _json_value_to_non_negative_int(value, trace_attr.ATTR_BILLING_QUANTITY)
        if quantity < 1:
            raise ValueError(f"span {self.span_id}: platform.billing.quantity должна быть >= 1")
        return quantity

    def billing_cost_origin_or_default(self) -> BillingCostOrigin:
        value = self.attributes.get(trace_attr.ATTR_BILLING_COST_ORIGIN)
        if value is None or value == "":
            return "platform"
        if not isinstance(value, str):
            raise ValueError(f"span {self.span_id}: неизвестный cost_origin {value!r}")
        if value == "platform":
            return "platform"
        if value == "company":
            return "company"
        raise ValueError(f"span {self.span_id}: неизвестный cost_origin {value!r}")

    def billing_custom_provider_id(self) -> str | None:
        value = self.attributes.get(trace_attr.ATTR_BILLING_CUSTOM_PROVIDER_ID)
        if value is None:
            return None
        if not isinstance(value, str) or not value:
            raise ValueError(f"span {self.span_id}: {trace_attr.ATTR_BILLING_CUSTOM_PROVIDER_ID} должен быть строкой")
        return value


def _json_value_to_non_negative_int(value: JsonValue, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} должен быть целым числом")
    if isinstance(value, int):
        quantity = value
    elif isinstance(value, float):
        if not value.is_integer():
            raise ValueError(f"{field_name} должен быть целым числом")
        quantity = int(value)
    elif isinstance(value, str):
        quantity = int(value)
    else:
        raise ValueError(f"{field_name} должен быть целым числом")
    if quantity < 0:
        raise ValueError(f"{field_name} должен быть >= 0")
    return quantity
