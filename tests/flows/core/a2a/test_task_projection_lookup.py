"""Необязательное чтение Task из проекции A2A."""

import uuid

import pytest
from a2a.types import Task, TaskState, TaskStatus

from apps.flows.src.models.a2a_projection.contracts import A2ATaskRepositoryError
from apps.flows.src.models.a2a_projection.task_event import A2ATaskEvent
from apps.flows.src.models.a2a_projection.task_projection import A2ATaskProjection


@pytest.mark.asyncio
async def test_task_lookups_return_task_or_none(unique_id: str) -> None:
    company_id = f"co-{unique_id}"
    other_company_id = f"ot-{unique_id}"
    flow_id = f"flow-{unique_id}"
    session_id = f"session-{unique_id}"
    context_id = f"context-{unique_id}"
    owner_user_id = f"owner-{unique_id}"
    task_id = str(uuid.uuid4())
    task = Task(
        id=task_id,
        context_id=context_id,
        status=TaskStatus(state=TaskState.TASK_STATE_SUBMITTED),
    )
    created = await A2ATaskProjection.ensure_task(
        company_id=company_id,
        session_id=session_id,
        flow_id=flow_id,
        owner_user_id=owner_user_id,
        task=task,
    )
    assert created is True

    found = await A2ATaskProjection.any_task_in_company(company_id=company_id, task_id=task_id)
    assert found is not None
    assert found.id == task_id
    again = await A2ATaskProjection.any_task_in_company(company_id=company_id, task_id=task_id)
    assert again is not None
    assert again.id == found.id
    assert await A2ATaskProjection.any_task_in_company(company_id=other_company_id, task_id=task_id) is None

    owned = await A2ATaskProjection.any_task_for_owner(
        company_id=company_id,
        owner_user_id=owner_user_id,
        task_id=task_id,
    )
    assert owned is not None
    assert owned.id == task_id
    assert (
        await A2ATaskProjection.any_task_for_owner(
            company_id=company_id,
            owner_user_id=f"other-{unique_id}",
            task_id=task_id,
        )
        is None
    )

    in_context = await A2ATaskProjection.any_task_for_context(
        company_id=company_id,
        flow_id=flow_id,
        context_id=context_id,
        task_id=task_id,
    )
    assert in_context is not None
    assert in_context.context_id == context_id
    assert (
        await A2ATaskProjection.any_task_for_context(
            company_id=company_id,
            flow_id=flow_id,
            context_id=f"other-{unique_id}",
            task_id=task_id,
        )
        is None
    )

    latest = await A2ATaskProjection.latest_task_for_context_by_updated_at_desc(
        company_id=company_id,
        owner_user_id=owner_user_id,
        flow_id=flow_id,
        context_id=context_id,
    )
    assert latest is not None
    assert latest.id == task_id

    loaded, sequence = await A2ATaskProjection.require_any_task_with_sequence(
        company_id=company_id,
        task_id=task_id,
    )
    assert loaded.id == task_id
    assert sequence == 0
    again_task, again_sequence = await A2ATaskProjection.require_any_task_with_sequence(
        company_id=company_id,
        task_id=task_id,
    )
    assert again_task.id == loaded.id
    assert again_sequence == sequence
    with pytest.raises(A2ATaskRepositoryError, match="not found"):
        _ = await A2ATaskProjection.require_any_task_with_sequence(
            company_id=company_id,
            task_id=str(uuid.uuid4()),
        )

    submitted = await A2ATaskEvent.any_submitted_task(company_id=company_id, task_id=task_id)
    assert submitted is not None
    assert submitted.id == task_id
    assert await A2ATaskEvent.any_submitted_task(company_id=company_id, task_id=str(uuid.uuid4())) is None
