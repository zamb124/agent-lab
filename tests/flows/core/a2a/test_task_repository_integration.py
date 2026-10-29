"""Integration coverage for the durable lossless A2A Task projection."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from a2a.helpers.proto_helpers import new_data_part, new_text_part
from a2a.types import (
    Artifact,
    Message,
    Part,
    Role,
    Task,
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
)
from sqlalchemy import func, select

from apps.flows.config import get_settings
from apps.flows.src.models.a2a_projection import A2ATaskRepositoryError
from core.a2a import struct_from_mapping, task_to_json_dict
from core.db.storage import Storage

pytestmark = [
    pytest.mark.integration,
    pytest.mark.real_taskiq,
    pytest.mark.no_service_client_patch,
]


@pytest_asyncio.fixture
async def task_repository(
    setup_database_before_tests: object,
) -> AsyncIterator[tuple[A2ATaskRepository, Storage]]:
    _ = setup_database_before_tests
    settings = get_settings()
    if not settings.database.flows_url:
        pytest.skip("DATABASE__FLOWS_URL is required for A2A repository tests")
    storage = Storage(db_url=settings.database.flows_url)
    yield A2ATaskRepository(storage), storage


def _scope() -> tuple[str, str, str, str, str]:
    suffix = uuid.uuid4().hex
    return (
        f"company-{suffix}",
        f"flow-{suffix}",
        f"session-{suffix}",
        f"context-{suffix}",
        f"task-{suffix}",
    )


def _submitted_task(*, task_id: str, context_id: str) -> Task:
    task = Task(
        id=task_id,
        context_id=context_id,
        status=TaskStatus(state=TaskState.TASK_STATE_SUBMITTED),
        history=[
            Message(
                message_id=f"message-{task_id}",
                role=Role.ROLE_USER,
                parts=[
                    new_text_part("start"),
                    new_data_part({"form": {"email": "user@linnex.io"}}),
                ],
            )
        ],
    )
    task.metadata.CopyFrom(struct_from_mapping({"origin": "integration"}))
    return task


@pytest.mark.asyncio
async def test_repository_materializes_lossless_task_and_replays_ledger(
    task_repository: tuple[A2ATaskRepository, Storage],
) -> None:
    repository, storage = task_repository
    company_id, flow_id, session_id, context_id, task_id = _scope()
    initial = _submitted_task(task_id=task_id, context_id=context_id)

    assert await repository.ensure_task(
        company_id=company_id,
        session_id=session_id,
        flow_id=flow_id,
        owner_user_id="owner-1",
        task=initial,
    )
    assert not await repository.ensure_task(
        company_id=company_id,
        session_id=session_id,
        flow_id=flow_id,
        owner_user_id="owner-1",
        task=initial,
    )

    first = TaskArtifactUpdateEvent(
        task_id=task_id,
        context_id=context_id,
        artifact=Artifact(
            artifact_id="surface-stream",
            name="interface",
            description="lossless mixed content",
            parts=[new_text_part("hello ")],
            extensions=["https://example.test/a2a-extension/proof/v1"],
        ),
        append=False,
        last_chunk=False,
    )
    first.artifact.metadata.CopyFrom(struct_from_mapping({"nested": {"first": 1}}))
    first_result = await repository.append_event(
        company_id=company_id,
        event=first,
        event_identity="event-1",
    )
    assert first_result.sequence == 1
    assert first_result.was_created

    duplicate = await repository.append_event(
        company_id=company_id,
        event=first,
        event_identity="event-1",
    )
    assert duplicate.sequence == 1
    assert not duplicate.was_created

    second = TaskArtifactUpdateEvent(
        task_id=task_id,
        context_id=context_id,
        artifact=Artifact(
            artifact_id="surface-stream",
            name="interface",
            description="lossless mixed content",
            parts=[
                new_text_part("world"),
                Part(raw=b"bytes", filename="proof.bin", media_type="application/octet-stream"),
                Part(url="https://linnex.io/files/proof"),
                new_data_part({"kind": "render", "slot_id": "conversation"}),
            ],
            extensions=["https://example.test/a2a-extension/proof/v1"],
        ),
        append=True,
        last_chunk=True,
    )
    second.artifact.metadata.CopyFrom(struct_from_mapping({"nested": {"second": 2}}))
    second_result = await repository.append_event(
        company_id=company_id,
        event=second,
        event_identity="event-2",
    )
    assert second_result.sequence == 2

    completed = TaskStatusUpdateEvent(
        task_id=task_id,
        context_id=context_id,
        status=TaskStatus(
            state=TaskState.TASK_STATE_COMPLETED,
            message=Message(
                message_id=f"complete-{task_id}",
                role=Role.ROLE_AGENT,
                parts=[new_text_part("done")],
            ),
        ),
    )
    completed_result = await repository.append_event(
        company_id=company_id,
        event=completed,
        event_identity="event-3",
    )
    await repository.mark_published(
        company_id=company_id,
        task_id=task_id,
        event_identity=completed_result.event_identity,
    )

    task = await repository.get_task(company_id=company_id, task_id=task_id)
    assert task is not None
    assert task.status.state == TaskState.TASK_STATE_COMPLETED
    assert len(task.history) == 1
    assert len(task.artifacts) == 1
    assert [part.WhichOneof("content") for part in task.artifacts[0].parts] == [
        "text",
        "text",
        "raw",
        "url",
        "data",
    ]
    assert task.artifacts[0].metadata.fields["nested"].struct_value.fields.keys() == {
        "first",
        "second",
    }
    assert task.metadata.fields["origin"].string_value == "integration"
    rebuilt = await repository.rebuild_task(company_id=company_id, task_id=task_id)
    assert task_to_json_dict(rebuilt) == task_to_json_dict(task)

    async with storage.get_session() as session:
        event_count = await session.scalar(
            select(func.count())
            .select_from(A2ATaskEventDedup)
            .where(A2ATaskEventDedup.task_id == task_id)
        )
        message_count = await session.scalar(
            select(func.count())
            .select_from(A2ATaskMessages)
            .where(A2ATaskMessages.task_id == task_id)
        )
        artifact_row = await session.scalar(
            select(A2AArtifactProjections).where(A2AArtifactProjections.task_id == task_id)
        )
    assert event_count == 4
    assert message_count == 1
    assert artifact_row is not None
    assert artifact_row.is_closed
    assert artifact_row.latest_sequence == 2


@pytest.mark.asyncio
async def test_repository_keeps_multiple_tasks_per_context_and_rejects_collisions(
    task_repository: tuple[A2ATaskRepository, Storage],
) -> None:
    repository, _ = task_repository
    company_id, flow_id, session_id, context_id, first_task_id = _scope()
    first = _submitted_task(task_id=first_task_id, context_id=context_id)
    _ = await repository.ensure_task(
        company_id=company_id,
        session_id=session_id,
        flow_id=flow_id,
        owner_user_id="owner-1",
        task=first,
    )

    changed = _submitted_task(task_id=first_task_id, context_id=context_id)
    changed.history[0].parts[0].text = "different"
    with pytest.raises(A2ATaskRepositoryError, match="identity collision"):
        _ = await repository.ensure_task(
            company_id=company_id,
            session_id=session_id,
            flow_id=flow_id,
            owner_user_id="owner-1",
            task=changed,
        )

    second_task_id = f"task-{uuid.uuid4().hex}"
    second = _submitted_task(task_id=second_task_id, context_id=context_id)
    _ = await repository.ensure_task(
        company_id=company_id,
        session_id=session_id,
        flow_id=flow_id,
        owner_user_id="owner-1",
        task=second,
    )
    tasks, total = await repository.list_tasks(
        company_id=company_id,
        owner_user_id="owner-1",
        flow_id=flow_id,
        context_id=context_id,
        task_state=TaskState.TASK_STATE_SUBMITTED,
        limit=10,
        offset=0,
    )
    assert total == 2
    assert {task.id for task in tasks} == {first_task_id, second_task_id}
