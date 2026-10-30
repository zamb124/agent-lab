"""Runtime tests: handoff wall time and HITL operator response SLI."""

from __future__ import annotations

import uuid

import pytest

from apps.flows.src.models.hitl_schemas import HitlHandoffCommand
from apps.flows.src.observability.handoff_timing import (
    maybe_record_handoff_wall_time,
    record_handoff_initiated,
)
from apps.flows.src.observability.hitl_timing import (
    maybe_record_hitl_operator_response,
    record_hitl_interrupt,
)
from apps.flows.src.state import ExecutionState
from apps.flows.src.state.interrupt import HandoffMode
from core.logging.attributes import (
    LOG_HANDOFF_TARGET_FLOW_ID,
    LOG_HANDOFF_WALL_MS,
    LOG_HITL_QUEUE_SLUG,
    LOG_HITL_WAIT_MS,
    LOG_HITL_WORK_ITEM_ID,
)
from tests.fixtures.observability_log_capture import (
    find_caplog_record,
    require_log_fields,
    require_numeric_field,
)
from tests.observability.contracts import HANDOFF_WALL_TIME, HITL_OPERATOR_RESPONDED

pytestmark = pytest.mark.timeout(60)


@pytest.mark.asyncio
async def test_handoff_wall_time_emitted_after_initiated(
    di,
    observability_caplog: pytest.LogCaptureFixture,
    unique_id: str,
) -> None:
    child_fid = f"handoff-child-{unique_id}"
    child_session_id = f"{child_fid}:ctx-{unique_id}"
    await record_handoff_initiated(di.redis_client, child_session_id=child_session_id)
    await maybe_record_handoff_wall_time(
        di.redis_client,
        child_session_id=child_session_id,
        target_flow_id=child_fid,
        depth=1,
    )

    rec = find_caplog_record(
        observability_caplog,
        message=HANDOFF_WALL_TIME.message,
        logger_name="apps.flows.src.observability.handoff_timing",
    )
    fields = require_log_fields(
        rec,
        required={
            LOG_HANDOFF_WALL_MS: (int, float),
            LOG_HANDOFF_TARGET_FLOW_ID: str,
        },
    )
    assert fields[LOG_HANDOFF_TARGET_FLOW_ID] == child_fid
    require_numeric_field(fields, LOG_HANDOFF_WALL_MS, min_value=0.0)


@pytest.mark.asyncio
async def test_hitl_operator_responded_emitted_on_resume(
    app,
    di,
    system_member_context,
    observability_caplog: pytest.LogCaptureFixture,
    unique_id: str,
) -> None:
    _ = app, system_member_context
    slug = f"hitl-metrics-{unique_id}"
    await di.work_item_service.create_queue(
        company_id="system",
        name="HITL metrics",
        slug=slug,
    )
    flow_id = f"hitl_flow_{unique_id}"
    ctx = f"ctx-{unique_id}"
    state = ExecutionState(
        task_id=f"a2a-{unique_id}",
        context_id=ctx,
        user_id="test_user",
        session_id=f"{flow_id}:{ctx}",
        branch_id="default",
    )
    command = HitlHandoffCommand(
        correlation_id=uuid.uuid5(uuid.NAMESPACE_URL, f"hitl:test:{unique_id}"),
        idempotency_key=f"hitl:test:{unique_id}",
        execution_branch_id=f"branch-{unique_id}",
        node_schedule_sequence=1,
        node_id="h",
        tool_call_id=None,
    )
    _cid, work_item_id = await di.node_constructor.hitl_work_item_service.register_handoff(
        state,
        question="Нужен оператор",
        task_title="Support",
        assignee_queue_slug=slug,
        handoff_mode=HandoffMode.SINGLE_REPLY,
        command=command,
    )

    await maybe_record_hitl_operator_response(
        di.redis_client,
        work_item_id=work_item_id,
        queue_slug=slug,
        task_id=state.task_id,
        flow_id=flow_id,
    )

    rec = find_caplog_record(
        observability_caplog,
        message=HITL_OPERATOR_RESPONDED.message,
        logger_name="apps.flows.src.observability.hitl_timing",
    )
    fields = require_log_fields(
        rec,
        required={
            LOG_HITL_WAIT_MS: (int, float),
            LOG_HITL_WORK_ITEM_ID: str,
            LOG_HITL_QUEUE_SLUG: str,
        },
    )
    assert fields[LOG_HITL_WORK_ITEM_ID] == work_item_id
    assert fields[LOG_HITL_QUEUE_SLUG] == slug
    require_numeric_field(fields, LOG_HITL_WAIT_MS, min_value=0.0)


@pytest.mark.asyncio
async def test_hitl_interrupt_timestamp_recorded_on_register(
    di,
    unique_id: str,
) -> None:
    work_item_id = f"wi-{unique_id}"
    await record_hitl_interrupt(di.redis_client, work_item_id=work_item_id)
    raw = await di.redis_client.get(f"hitl_interrupt_ts:{work_item_id}")
    assert raw is not None
