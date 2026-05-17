"""Spans биллинга по фактическому использованию LiveKit (поминутно)."""

from __future__ import annotations

import math
from datetime import datetime

import core.tracing.attributes as trace_attributes
from core.models.billing_models import UsageType
from core.tracing.operation_span import traced_operation


def livekit_billed_minutes(*, started_at: datetime | None, ended_at: datetime | None) -> int:
    """Целые минуты для settlement: подъём до минуты при ненулевой длительности, минимум 1."""
    if started_at is None or ended_at is None:
        return 0
    secs = (ended_at - started_at).total_seconds()
    if secs <= 0:
        return 0
    return max(1, int(math.ceil(secs / 60.0)))


async def trace_livekit_room_session_usage(
    *,
    company_id: str,
    user_id: str,
    call_id: str,
    livekit_room_name: str,
    started_at: datetime | None,
    ended_at: datetime | None,
) -> None:
    minutes = livekit_billed_minutes(started_at=started_at, ended_at=ended_at)
    if minutes <= 0:
        return
    async with traced_operation(
        "livekit.room.session_usage",
        event_type="livekit.room",
        operation_category="livekit",
        billing_usage_type=UsageType.TOOL_CALL.value,
        billing_resource_name="livekit:room_minute",
        billing_quantity=minutes,
        billing_pending_settlement=True,
        extra_attributes={
            trace_attributes.ATTR_TENANT_COMPANY_ID: company_id,
            trace_attributes.ATTR_USER_ID: user_id,
            trace_attributes.ATTR_CALL_ID: call_id,
            trace_attributes.ATTR_LIVEKIT_ROOM: livekit_room_name,
        },
    ):
        pass


async def trace_livekit_egress_composite_usage(
    *,
    company_id: str,
    user_id: str,
    call_id: str,
    recording_id: str,
    livekit_room_name: str,
    egress_id: str,
    started_at: datetime | None,
    ended_at: datetime | None,
) -> None:
    if livekit_room_name == "" or egress_id == "":
        return
    minutes = livekit_billed_minutes(started_at=started_at, ended_at=ended_at)
    if minutes <= 0:
        return
    async with traced_operation(
        "livekit.egress.composite_usage",
        event_type="livekit.egress",
        operation_category="livekit_egress",
        billing_usage_type=UsageType.TOOL_CALL.value,
        billing_resource_name="livekit:egress_composite_minute",
        billing_quantity=minutes,
        billing_pending_settlement=True,
        extra_attributes={
            trace_attributes.ATTR_TENANT_COMPANY_ID: company_id,
            trace_attributes.ATTR_USER_ID: user_id,
            trace_attributes.ATTR_CALL_ID: call_id,
            trace_attributes.ATTR_LIVEKIT_ROOM: livekit_room_name,
            trace_attributes.ATTR_LIVEKIT_EGRESS_ID: egress_id,
            "platform.sync.recording_id": recording_id,
        },
    ):
        pass


async def trace_livekit_egress_segmented_usage(
    *,
    company_id: str,
    user_id: str,
    call_id: str,
    livekit_room_name: str,
    billed_minutes: int,
) -> None:
    if billed_minutes <= 0:
        return
    async with traced_operation(
        "livekit.egress.segmented_usage",
        event_type="livekit.egress",
        operation_category="livekit_egress",
        billing_usage_type=UsageType.TOOL_CALL.value,
        billing_resource_name="livekit:egress_segmented_minute",
        billing_quantity=billed_minutes,
        billing_pending_settlement=True,
        extra_attributes={
            trace_attributes.ATTR_TENANT_COMPANY_ID: company_id,
            trace_attributes.ATTR_USER_ID: user_id,
            trace_attributes.ATTR_CALL_ID: call_id,
            trace_attributes.ATTR_LIVEKIT_ROOM: livekit_room_name,
        },
    ):
        pass
