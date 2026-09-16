"""Spans биллинга фермы code_agent."""

from __future__ import annotations

import core.tracing.attributes as trace_attributes
from core.models.billing_models import UsageType
from core.tracing.operation_span import traced_operation


async def trace_guest_start(*, company_id: str, user_id: str, flow_id: str, node_id: str) -> None:
    async with traced_operation(
        "guest_runtime.start",
        event_type="guest.runtime",
        operation_category="guest",
        billing_usage_type=UsageType.AGENT_EXECUTION.value,
        billing_resource_name="guest:start",
        billing_quantity=1,
        billing_pending_settlement=True,
        extra_attributes={
            trace_attributes.ATTR_TENANT_COMPANY_ID: company_id,
            trace_attributes.ATTR_USER_ID: user_id,
            trace_attributes.ATTR_FLOW_ID: flow_id,
            "guest.node_id": node_id,
        },
    ):
        pass


async def trace_guest_session_usage(
    *,
    company_id: str,
    user_id: str,
    flow_id: str,
    node_id: str,
    lifetime_seconds: int,
) -> None:
    if lifetime_seconds <= 0:
        raise ValueError("guest session_usage lifetime_seconds must be positive")
    async with traced_operation(
        "guest_runtime.session_usage",
        event_type="guest.runtime",
        operation_category="guest",
        billing_usage_type=UsageType.AGENT_EXECUTION.value,
        billing_resource_name="guest:runtime_second",
        billing_quantity=lifetime_seconds,
        billing_pending_settlement=True,
        extra_attributes={
            trace_attributes.ATTR_TENANT_COMPANY_ID: company_id,
            trace_attributes.ATTR_USER_ID: user_id,
            trace_attributes.ATTR_FLOW_ID: flow_id,
            "guest.node_id": node_id,
        },
    ):
        pass


async def trace_guest_build_usage(
    *,
    company_id: str,
    user_id: str,
    flow_id: str,
    node_id: str,
    build_seconds: int,
) -> None:
    if build_seconds <= 0:
        raise ValueError("guest build_usage build_seconds must be positive")
    async with traced_operation(
        "guest_runtime.build_usage",
        event_type="guest.build",
        operation_category="guest",
        billing_usage_type=UsageType.AGENT_EXECUTION.value,
        billing_resource_name="guest:build_second",
        billing_quantity=build_seconds,
        billing_pending_settlement=True,
        extra_attributes={
            trace_attributes.ATTR_TENANT_COMPANY_ID: company_id,
            trace_attributes.ATTR_USER_ID: user_id,
            trace_attributes.ATTR_FLOW_ID: flow_id,
            "guest.node_id": node_id,
        },
    ):
        pass
