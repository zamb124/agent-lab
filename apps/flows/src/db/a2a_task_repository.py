"""Durable lossless A2A Task, Message, Artifact and event projections."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import final
from uuid import uuid4

from a2a.types import (
    Message,
    Task,
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatusUpdateEvent,
)
from sqlalchemy import desc, select, update
from sqlalchemy import func as sa_func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from apps.flows.src.db.models import (
    A2AArtifactProjections,
    A2ATaskEventDedup,
    A2ATaskMessages,
    A2ATaskProjections,
)
from core.a2a import (
    TaskProjectionAccumulator,
    artifact_payload_hash,
    artifact_to_json_dict,
    artifact_update_from_json_dict,
    artifact_update_to_json_dict,
    is_terminal_a2a_task_state,
    mapping_from_struct,
    message_to_json_dict,
    status_update_from_json_dict,
    status_update_to_json_dict,
    struct_from_mapping,
    task_from_json_dict,
    task_to_json_dict,
)
from core.a2a.task_projection import TaskProjectionEvent
from core.db.storage import Storage
from core.types import JsonObject, require_json_object
from core.utils.time import utcnow

_TASK_SNAPSHOT_KIND = "task"
_ARTIFACT_UPDATE_KIND = "artifact_update"
_STATUS_UPDATE_KIND = "status_update"


class A2ATaskRepositoryError(RuntimeError):
    """A durable A2A projection invariant was violated."""


class A2ATaskProjectionMismatchError(A2ATaskRepositoryError):
    """The query projection differs from a replay of the task event ledger."""


@dataclass(frozen=True)
class A2AEventAppendResult:
    event: TaskProjectionEvent
    sequence: int
    event_identity: str
    was_created: bool


@dataclass(frozen=True)
class A2APendingEvent:
    company_id: str
    task_id: str
    event_identity: str
    sequence: int
    event: TaskProjectionEvent


@dataclass(frozen=True)
class A2AStoredEvent:
    sequence: int
    event_identity: str
    event: TaskProjectionEvent
    source_fingerprint: str
    published_at: datetime | None


def _fingerprint_proto(message: Message | Task | TaskProjectionEvent) -> str:
    return hashlib.sha256(message.SerializeToString(deterministic=True)).hexdigest()


def _task_state_name(task: Task) -> str:
    if not task.HasField("status"):
        raise A2ATaskRepositoryError(f"Task {task.id!r} must contain status")
    return TaskState.Name(task.status.state)


def _copy_event(event: TaskProjectionEvent) -> TaskProjectionEvent:
    if isinstance(event, TaskArtifactUpdateEvent):
        snapshot = TaskArtifactUpdateEvent()
        snapshot.CopyFrom(event)
    else:
        snapshot = TaskStatusUpdateEvent()
        snapshot.CopyFrom(event)
    return snapshot


def _enrich_event(
    event: TaskProjectionEvent,
    *,
    event_identity: str,
    sequence: int,
) -> TaskProjectionEvent:
    snapshot = _copy_event(event)
    metadata = (
        mapping_from_struct(snapshot.metadata)
        if snapshot.HasField("metadata")
        else {}
    )
    existing_identity = metadata.get("platformEventId")
    if existing_identity is not None and existing_identity != event_identity:
        raise A2ATaskRepositoryError("A2A event contains conflicting platformEventId")
    existing_sequence = metadata.get("platformSequence")
    if existing_sequence is not None and existing_sequence != sequence:
        raise A2ATaskRepositoryError("A2A event contains conflicting platformSequence")
    metadata["platformEventId"] = event_identity
    metadata["platformSequence"] = sequence
    snapshot.metadata.CopyFrom(struct_from_mapping(metadata))
    return snapshot


def _event_kind(event: TaskProjectionEvent) -> str:
    if isinstance(event, TaskArtifactUpdateEvent):
        return _ARTIFACT_UPDATE_KIND
    return _STATUS_UPDATE_KIND


def _event_to_json(event: TaskProjectionEvent) -> JsonObject:
    if isinstance(event, TaskArtifactUpdateEvent):
        return artifact_update_to_json_dict(event)
    return status_update_to_json_dict(event)


def _event_from_row(row: A2ATaskEventDedup) -> TaskProjectionEvent:
    payload = require_json_object(row.event_json, "A2ATaskEvent.event_json")
    if row.event_kind == _ARTIFACT_UPDATE_KIND:
        return artifact_update_from_json_dict(payload)
    if row.event_kind == _STATUS_UPDATE_KIND:
        return status_update_from_json_dict(payload)
    raise A2ATaskRepositoryError(
        f"Unsupported A2A task event kind: {row.event_kind!r}"
    )


@final
class A2ATaskRepository:
    """Owns query projection and append-only delivery ledger for A2A Tasks."""

    def __init__(self, storage: Storage) -> None:
        self._storage: Storage = storage

    async def ensure_task(
        self,
        *,
        company_id: str,
        session_id: str,
        flow_id: str,
        owner_user_id: str,
        task: Task,
        execution_branch_id: str | None = None,
        flow_config_version: str | None = None,
        input_message_id: str | None = None,
    ) -> bool:
        """Create the submitted Task snapshot exactly once."""
        self._validate_task_identity(
            task,
            company_id,
            session_id,
            flow_id,
            owner_user_id,
        )
        task_json = task_to_json_dict(task)
        task_metadata = mapping_from_struct(task.metadata) if task.HasField("metadata") else {}
        now = utcnow()
        async with self._storage.get_session() as session:
            async with session.begin():
                created_result = await session.execute(
                    insert(A2ATaskProjections)
                    .values(
                        task_id=task.id,
                        company_id=company_id,
                        context_id=task.context_id,
                        session_id=session_id,
                        flow_id=flow_id,
                        owner_user_id=owner_user_id,
                        execution_branch_id=execution_branch_id,
                        task_state=_task_state_name(task),
                        task_json=task_json,
                        task_metadata=task_metadata,
                        input_message_id=input_message_id,
                        flow_config_version=flow_config_version,
                        latest_sequence=0,
                        is_terminal=is_terminal_a2a_task_state(task.status.state),
                        completed_at=(
                            now
                            if is_terminal_a2a_task_state(task.status.state)
                            else None
                        ),
                        created_at=now,
                        updated_at=now,
                    )
                    .on_conflict_do_nothing(index_elements=["task_id"])
                    .returning(A2ATaskProjections.task_id)
                )
                created_task_id = created_result.scalar_one_or_none()
                if created_task_id is None:
                    existing_result = await session.execute(
                        select(A2ATaskProjections)
                        .where(A2ATaskProjections.task_id == task.id)
                        .with_for_update()
                    )
                    existing = existing_result.scalar_one()
                    self._validate_existing_scope(
                        existing,
                        company_id=company_id,
                        session_id=session_id,
                        flow_id=flow_id,
                        context_id=task.context_id,
                        owner_user_id=owner_user_id,
                    )
                    snapshot_result = await session.execute(
                        select(A2ATaskEventDedup).where(
                            A2ATaskEventDedup.task_id == task.id,
                            A2ATaskEventDedup.sequence == 0,
                            A2ATaskEventDedup.event_kind == _TASK_SNAPSHOT_KIND,
                        )
                    )
                    snapshot = snapshot_result.scalar_one_or_none()
                    if snapshot is None or snapshot.source_fingerprint != _fingerprint_proto(task):
                        raise A2ATaskRepositoryError(
                            f"A2A Task identity collision: {task.id!r}"
                        )
                    return False

                self._add_history_rows(
                    session,
                    company_id=company_id,
                    task=task,
                    now=now,
                )
                self._add_artifact_rows(
                    session,
                    company_id=company_id,
                    task=task,
                    sequence=0,
                    now=now,
                    closed=True,
                )
                session.add(
                    A2ATaskEventDedup(
                        task_event_id=str(uuid4()),
                        company_id=company_id,
                        task_id=task.id,
                        event_identity=f"task:{task.id}:created",
                        sequence=0,
                        event_kind=_TASK_SNAPSHOT_KIND,
                        event_json=task_json,
                        source_fingerprint=_fingerprint_proto(task),
                        published_at=now,
                        created_at=now,
                    )
                )
                return True

    async def append_event(
        self,
        *,
        company_id: str,
        event: TaskProjectionEvent,
        event_identity: str,
    ) -> A2AEventAppendResult:
        """Append event and update Task/Artifact projection in one transaction."""
        if event_identity.strip() == "":
            raise A2ATaskRepositoryError("event_identity is required")
        source_fingerprint = _fingerprint_proto(event)
        async with self._storage.get_session() as session:
            async with session.begin():
                task_result = await session.execute(
                    select(A2ATaskProjections)
                    .where(A2ATaskProjections.task_id == event.task_id)
                    .with_for_update()
                )
                task_row = task_result.scalar_one_or_none()
                if task_row is None:
                    raise A2ATaskRepositoryError(
                        f"A2A Task {event.task_id!r} must be ensured before event append"
                    )
                if task_row.company_id != company_id:
                    raise A2ATaskRepositoryError("A2A Task belongs to another company")
                if task_row.context_id != event.context_id:
                    raise A2ATaskRepositoryError("A2A event context_id does not match Task")

                duplicate_result = await session.execute(
                    select(A2ATaskEventDedup).where(
                        A2ATaskEventDedup.task_id == event.task_id,
                        A2ATaskEventDedup.event_identity == event_identity,
                    )
                )
                duplicate = duplicate_result.scalar_one_or_none()
                if duplicate is not None:
                    if duplicate.source_fingerprint != source_fingerprint:
                        raise A2ATaskRepositoryError(
                            f"A2A event identity collision: {event_identity!r}"
                        )
                    return A2AEventAppendResult(
                        event=_event_from_row(duplicate),
                        sequence=int(duplicate.sequence),
                        event_identity=event_identity,
                        was_created=False,
                    )

                sequence = int(task_row.latest_sequence) + 1
                stored_event = _enrich_event(
                    event,
                    event_identity=event_identity,
                    sequence=sequence,
                )
                current_task = task_from_json_dict(
                    require_json_object(task_row.task_json, "A2ATask.task_json")
                )
                artifact_rows_result = await session.execute(
                    select(A2AArtifactProjections)
                    .where(A2AArtifactProjections.task_id == event.task_id)
                    .order_by(A2AArtifactProjections.ordinal.asc())
                )
                artifact_rows = list(artifact_rows_result.scalars().all())
                next_task = self._apply_event_to_task(
                    current_task,
                    artifact_rows=artifact_rows,
                    event=stored_event,
                )
                task_row.task_json = task_to_json_dict(next_task)
                task_row.task_state = _task_state_name(next_task)
                task_row.latest_sequence = sequence
                task_row.is_terminal = is_terminal_a2a_task_state(
                    next_task.status.state
                )
                updated_at = utcnow()
                task_row.updated_at = updated_at
                if task_row.is_terminal and task_row.completed_at is None:
                    task_row.completed_at = updated_at

                if isinstance(stored_event, TaskArtifactUpdateEvent):
                    await self._upsert_artifact_projection(
                        session,
                        company_id=company_id,
                        task=next_task,
                        event=stored_event,
                        sequence=sequence,
                        existing_rows=artifact_rows,
                    )

                session.add(
                    A2ATaskEventDedup(
                        task_event_id=str(uuid4()),
                        company_id=company_id,
                        task_id=event.task_id,
                        event_identity=event_identity,
                        sequence=sequence,
                        event_kind=_event_kind(stored_event),
                        event_json=_event_to_json(stored_event),
                        source_fingerprint=source_fingerprint,
                        published_at=None,
                        created_at=utcnow(),
                    )
                )
                return A2AEventAppendResult(
                    event=stored_event,
                    sequence=sequence,
                    event_identity=event_identity,
                    was_created=True,
                )

    async def mark_published(
        self,
        *,
        company_id: str,
        task_id: str,
        event_identity: str,
    ) -> None:
        async with self._storage.get_session() as session:
            async with session.begin():
                update_result = await session.execute(
                    update(A2ATaskEventDedup)
                    .where(
                        A2ATaskEventDedup.company_id == company_id,
                        A2ATaskEventDedup.task_id == task_id,
                        A2ATaskEventDedup.event_identity == event_identity,
                        A2ATaskEventDedup.published_at.is_(None),
                    )
                    .values(published_at=utcnow())
                    .returning(A2ATaskEventDedup.task_event_id)
                )
                if update_result.scalar_one_or_none() is None:
                    existing_result = await session.execute(
                        select(A2ATaskEventDedup).where(
                            A2ATaskEventDedup.company_id == company_id,
                            A2ATaskEventDedup.task_id == task_id,
                            A2ATaskEventDedup.event_identity == event_identity,
                        )
                    )
                    if existing_result.scalar_one_or_none() is None:
                        raise A2ATaskRepositoryError(
                            f"Unknown A2A event identity: {event_identity!r}"
                        )

    async def list_unpublished(self, *, limit: int = 100) -> list[A2APendingEvent]:
        if limit <= 0:
            raise A2ATaskRepositoryError("unpublished event limit must be positive")
        async with self._storage.get_session() as session:
            result = await session.execute(
                select(A2ATaskEventDedup)
                .where(A2ATaskEventDedup.published_at.is_(None))
                .order_by(A2ATaskEventDedup.created_at.asc())
                .limit(limit)
            )
            rows = result.scalars().all()
        return [
            A2APendingEvent(
                company_id=row.company_id,
                task_id=row.task_id,
                event_identity=row.event_identity,
                sequence=int(row.sequence),
                event=_event_from_row(row),
            )
            for row in rows
        ]

    async def list_events_after_sequence(
        self,
        *,
        company_id: str,
        task_id: str,
        after_sequence: int,
    ) -> list[A2AStoredEvent]:
        """Return durable events with sequence in (after_sequence, latest]."""
        if after_sequence < 0:
            raise A2ATaskRepositoryError("after_sequence must be >= 0")
        async with self._storage.get_session() as session:
            task_result = await session.execute(
                select(A2ATaskProjections).where(
                    A2ATaskProjections.company_id == company_id,
                    A2ATaskProjections.task_id == task_id,
                )
            )
            task_row = task_result.scalar_one_or_none()
            if task_row is None:
                raise A2ATaskRepositoryError(f"A2A Task {task_id!r} not found")
            if after_sequence > int(task_row.latest_sequence):
                raise A2ATaskRepositoryError(
                    f"after_sequence {after_sequence} is ahead of task latest_sequence {task_row.latest_sequence}"
                )
            result = await session.execute(
                select(A2ATaskEventDedup)
                .where(
                    A2ATaskEventDedup.company_id == company_id,
                    A2ATaskEventDedup.task_id == task_id,
                    A2ATaskEventDedup.sequence > after_sequence,
                )
                .order_by(A2ATaskEventDedup.sequence.asc())
            )
            rows = list(result.scalars().all())
        return [
            A2AStoredEvent(
                sequence=int(row.sequence),
                event_identity=row.event_identity,
                event=_event_from_row(row),
                source_fingerprint=row.source_fingerprint,
                published_at=row.published_at,
            )
            for row in rows
        ]

    async def get_task(self, *, company_id: str, task_id: str) -> Task | None:
        async with self._storage.get_session() as session:
            task_result = await session.execute(
                select(A2ATaskProjections).where(
                    A2ATaskProjections.company_id == company_id,
                    A2ATaskProjections.task_id == task_id,
                )
            )
            task_row = task_result.scalar_one_or_none()
            if task_row is None:
                return None
            return task_from_json_dict(
                require_json_object(task_row.task_json, "A2ATask.task_json")
            )

    async def get_latest_sequence(self, *, company_id: str, task_id: str) -> int:
        """Sequence of the last durable event of the task (0 — only the submitted snapshot)."""
        _, latest = await self.get_task_with_sequence(company_id=company_id, task_id=task_id)
        return latest

    async def get_task_with_sequence(self, *, company_id: str, task_id: str) -> tuple[Task, int]:
        """Projection Task together with the sequence it reflects — one row, one read.

        A stream that starts with this snapshot continues with events whose sequence is
        greater than the returned one: nothing is lost and nothing is applied twice.
        """
        async with self._storage.get_session() as session:
            result = await session.execute(
                select(A2ATaskProjections).where(
                    A2ATaskProjections.company_id == company_id,
                    A2ATaskProjections.task_id == task_id,
                )
            )
            row = result.scalar_one_or_none()
        if row is None:
            raise A2ATaskRepositoryError(f"A2A Task {task_id!r} not found")
        return (
            task_from_json_dict(require_json_object(row.task_json, "A2ATask.task_json")),
            int(row.latest_sequence),
        )

    async def get_submitted_task(self, *, company_id: str, task_id: str) -> Task | None:
        """Sequence-0 snapshot: SUBMITTED Task with history and without artifacts.

        Every status/artifact event of the task has sequence >= 1, so a stream that
        starts with this snapshot and continues from sequence 1 never duplicates parts.
        """
        async with self._storage.get_session() as session:
            result = await session.execute(
                select(A2ATaskEventDedup).where(
                    A2ATaskEventDedup.company_id == company_id,
                    A2ATaskEventDedup.task_id == task_id,
                    A2ATaskEventDedup.sequence == 0,
                    A2ATaskEventDedup.event_kind == _TASK_SNAPSHOT_KIND,
                )
            )
            row = result.scalar_one_or_none()
        if row is None:
            return None
        return task_from_json_dict(require_json_object(row.event_json, "A2ATaskEvent.task"))

    async def get_task_for_owner(
        self,
        *,
        company_id: str,
        owner_user_id: str,
        task_id: str,
    ) -> Task | None:
        async with self._storage.get_session() as session:
            result = await session.execute(
                select(A2ATaskProjections).where(
                    A2ATaskProjections.company_id == company_id,
                    A2ATaskProjections.owner_user_id == owner_user_id,
                    A2ATaskProjections.task_id == task_id,
                )
            )
            row = result.scalar_one_or_none()
        if row is None:
            return None
        return task_from_json_dict(
            require_json_object(row.task_json, "A2ATask.task_json")
        )

    async def get_task_for_context(
        self,
        *,
        company_id: str,
        flow_id: str,
        context_id: str,
        task_id: str,
    ) -> Task | None:
        """Read a task after an external access service authorized its context."""
        async with self._storage.get_session() as session:
            result = await session.execute(
                select(A2ATaskProjections).where(
                    A2ATaskProjections.company_id == company_id,
                    A2ATaskProjections.flow_id == flow_id,
                    A2ATaskProjections.context_id == context_id,
                    A2ATaskProjections.task_id == task_id,
                )
            )
            row = result.scalar_one_or_none()
        if row is None:
            return None
        return task_from_json_dict(
            require_json_object(row.task_json, "A2ATask.task_json")
        )

    async def task_exists_in_scope(
        self,
        *,
        company_id: str,
        task_id: str,
        session_id: str,
        flow_id: str,
        context_id: str,
        owner_user_id: str,
    ) -> bool:
        async with self._storage.get_session() as session:
            result = await session.execute(
                select(A2ATaskProjections).where(A2ATaskProjections.task_id == task_id)
            )
            row = result.scalar_one_or_none()
        if row is None:
            return False
        self._validate_existing_scope(
            row,
            company_id=company_id,
            session_id=session_id,
            flow_id=flow_id,
            context_id=context_id,
            owner_user_id=owner_user_id,
        )
        return True

    async def get_latest_for_context(
        self,
        *,
        company_id: str,
        owner_user_id: str,
        flow_id: str,
        context_id: str,
    ) -> Task | None:
        async with self._storage.get_session() as session:
            task_result = await session.execute(
                select(A2ATaskProjections)
                .where(
                    A2ATaskProjections.company_id == company_id,
                    A2ATaskProjections.owner_user_id == owner_user_id,
                    A2ATaskProjections.flow_id == flow_id,
                    A2ATaskProjections.context_id == context_id,
                )
                .order_by(desc(A2ATaskProjections.updated_at))
                .limit(1)
            )
            task_row = task_result.scalar_one_or_none()
            if task_row is None:
                return None
            return task_from_json_dict(
                require_json_object(task_row.task_json, "A2ATask.task_json")
            )

    async def list_tasks(
        self,
        *,
        company_id: str,
        owner_user_id: str,
        flow_id: str,
        context_id: str | None,
        task_state: int | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Task], int]:
        filters = [
            A2ATaskProjections.company_id == company_id,
            A2ATaskProjections.owner_user_id == owner_user_id,
            A2ATaskProjections.flow_id == flow_id,
        ]
        if context_id is not None:
            filters.append(A2ATaskProjections.context_id == context_id)
        if task_state is not None:
            filters.append(A2ATaskProjections.task_state == TaskState.Name(task_state))
        async with self._storage.get_session() as session:
            count_result = await session.execute(
                select(sa_func.count()).select_from(A2ATaskProjections).where(*filters)
            )
            total = int(count_result.scalar_one())
            rows_result = await session.execute(
                select(A2ATaskProjections)
                .where(*filters)
                .order_by(desc(A2ATaskProjections.updated_at))
                .limit(limit)
                .offset(offset)
            )
            rows = rows_result.scalars().all()
            return [
                task_from_json_dict(
                    require_json_object(row.task_json, "A2ATask.task_json")
                )
                for row in rows
            ], total

    async def list_tasks_for_context(
        self,
        *,
        company_id: str,
        flow_id: str,
        context_id: str,
        task_state: int | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Task], int]:
        """List only one pre-authorized live-share context."""
        filters = [
            A2ATaskProjections.company_id == company_id,
            A2ATaskProjections.flow_id == flow_id,
            A2ATaskProjections.context_id == context_id,
        ]
        if task_state is not None:
            filters.append(A2ATaskProjections.task_state == TaskState.Name(task_state))
        async with self._storage.get_session() as session:
            count_result = await session.execute(
                select(sa_func.count()).select_from(A2ATaskProjections).where(*filters)
            )
            total = int(count_result.scalar_one())
            rows_result = await session.execute(
                select(A2ATaskProjections)
                .where(*filters)
                .order_by(desc(A2ATaskProjections.updated_at))
                .limit(limit)
                .offset(offset)
            )
            rows = rows_result.scalars().all()
        return [
            task_from_json_dict(require_json_object(row.task_json, "A2ATask.task_json"))
            for row in rows
        ], total

    async def rebuild_task(self, *, company_id: str, task_id: str) -> Task:
        """Replay task snapshot + events and verify the query projection."""
        async with self._storage.get_session() as session:
            task_result = await session.execute(
                select(A2ATaskProjections).where(
                    A2ATaskProjections.company_id == company_id,
                    A2ATaskProjections.task_id == task_id,
                )
            )
            task_row = task_result.scalar_one_or_none()
            if task_row is None:
                raise A2ATaskRepositoryError(f"A2A Task {task_id!r} not found")
            event_result = await session.execute(
                select(A2ATaskEventDedup)
                .where(A2ATaskEventDedup.task_id == task_id)
                .order_by(A2ATaskEventDedup.sequence.asc())
            )
            rows = list(event_result.scalars().all())
        if not rows or rows[0].event_kind != _TASK_SNAPSHOT_KIND:
            raise A2ATaskRepositoryError(f"A2A Task {task_id!r} has no snapshot event")
        initial_task = task_from_json_dict(
            require_json_object(rows[0].event_json, "A2ATaskEvent.task")
        )
        projection = TaskProjectionAccumulator(
            task_id=initial_task.id,
            context_id=initial_task.context_id,
        )
        projection.apply(
            TaskStatusUpdateEvent(
                task_id=initial_task.id,
                context_id=initial_task.context_id,
                status=initial_task.status,
            )
        )
        for artifact in initial_task.artifacts:
            projection.apply(
                TaskArtifactUpdateEvent(
                    task_id=initial_task.id,
                    context_id=initial_task.context_id,
                    artifact=artifact,
                    append=False,
                )
            )
        for row in rows[1:]:
            projection.apply(_event_from_row(row), event_identity=row.event_identity)
        rebuilt = projection.build_task(
            history=initial_task.history,
            metadata=initial_task.metadata if initial_task.HasField("metadata") else None,
        )
        current = task_from_json_dict(
            require_json_object(task_row.task_json, "A2ATask.task_json")
        )
        if task_to_json_dict(rebuilt) != task_to_json_dict(current):
            raise A2ATaskProjectionMismatchError(
                f"A2A Task projection mismatch for {task_id!r}"
            )
        return rebuilt

    @staticmethod
    def _validate_task_identity(
        task: Task,
        company_id: str,
        session_id: str,
        flow_id: str,
        owner_user_id: str,
    ) -> None:
        if company_id.strip() == "":
            raise A2ATaskRepositoryError("company_id is required")
        if session_id.strip() == "":
            raise A2ATaskRepositoryError("session_id is required")
        if flow_id.strip() == "":
            raise A2ATaskRepositoryError("flow_id is required")
        if owner_user_id.strip() == "":
            raise A2ATaskRepositoryError("owner_user_id is required")
        if task.id.strip() == "":
            raise A2ATaskRepositoryError("task.id is required")
        if task.context_id.strip() == "":
            raise A2ATaskRepositoryError("task.context_id is required")
        _ = _task_state_name(task)

    @staticmethod
    def _validate_existing_scope(
        task_row: A2ATaskProjections,
        *,
        company_id: str,
        session_id: str,
        flow_id: str,
        context_id: str,
        owner_user_id: str,
    ) -> None:
        if (
            task_row.company_id != company_id
            or task_row.session_id != session_id
            or task_row.flow_id != flow_id
            or task_row.context_id != context_id
            or task_row.owner_user_id != owner_user_id
        ):
            raise A2ATaskRepositoryError(
                f"A2A Task {task_row.task_id!r} identity belongs to another scope"
            )

    @staticmethod
    def _add_history_rows(
        session: AsyncSession,
        *,
        company_id: str,
        task: Task,
        now: datetime,
    ) -> None:
        for ordinal, message in enumerate(task.history):
            if message.message_id.strip() == "":
                raise A2ATaskRepositoryError("Task history Message.message_id is required")
            session.add(
                A2ATaskMessages(
                    task_message_id=f"{task.id}:{message.message_id}",
                    company_id=company_id,
                    task_id=task.id,
                    message_id=message.message_id,
                    ordinal=ordinal,
                    message_json=message_to_json_dict(message),
                    created_at=now,
                )
            )

    @staticmethod
    def _add_artifact_rows(
        session: AsyncSession,
        *,
        company_id: str,
        task: Task,
        sequence: int,
        now: datetime,
        closed: bool,
    ) -> None:
        for ordinal, artifact in enumerate(task.artifacts):
            if artifact.artifact_id.strip() == "":
                raise A2ATaskRepositoryError("Task Artifact.artifact_id is required")
            session.add(
                A2AArtifactProjections(
                    artifact_projection_id=f"{task.id}:{artifact.artifact_id}",
                    company_id=company_id,
                    task_id=task.id,
                    artifact_id=artifact.artifact_id,
                    ordinal=ordinal,
                    artifact_json=artifact_to_json_dict(artifact),
                    revision=1,
                    is_closed=closed,
                    latest_sequence=sequence,
                    payload_hash=artifact_payload_hash(artifact),
                    created_at=now,
                    updated_at=now,
                )
            )

    @staticmethod
    def _apply_event_to_task(
        current_task: Task,
        *,
        artifact_rows: list[A2AArtifactProjections],
        event: TaskProjectionEvent,
    ) -> Task:
        projection = TaskProjectionAccumulator(
            task_id=current_task.id,
            context_id=current_task.context_id,
        )
        projection.apply(
            TaskStatusUpdateEvent(
                task_id=current_task.id,
                context_id=current_task.context_id,
                status=current_task.status,
            )
        )
        artifacts_by_id = {
            artifact.artifact_id: artifact for artifact in current_task.artifacts
        }
        if len(artifacts_by_id) != len(artifact_rows):
            raise A2ATaskProjectionMismatchError(
                f"A2A Artifact projection mismatch for task {current_task.id!r}"
            )
        for row in artifact_rows:
            artifact = artifacts_by_id.get(row.artifact_id)
            if artifact is None:
                raise A2ATaskProjectionMismatchError(
                    f"A2A Artifact {row.artifact_id!r} missing from Task projection"
                )
            projection.apply(
                TaskArtifactUpdateEvent(
                    task_id=current_task.id,
                    context_id=current_task.context_id,
                    artifact=artifact,
                    append=False,
                    last_chunk=row.is_closed,
                )
            )
        projection.apply(event)
        return projection.build_task(
            history=current_task.history,
            metadata=current_task.metadata if current_task.HasField("metadata") else None,
        )

    @staticmethod
    async def _upsert_artifact_projection(
        session: AsyncSession,
        *,
        company_id: str,
        task: Task,
        event: TaskArtifactUpdateEvent,
        sequence: int,
        existing_rows: list[A2AArtifactProjections],
    ) -> None:
        artifact_id = event.artifact.artifact_id
        ordinal = next(
            index
            for index, artifact in enumerate(task.artifacts)
            if artifact.artifact_id == artifact_id
        )
        materialized = task.artifacts[ordinal]
        existing = next(
            (row for row in existing_rows if row.artifact_id == artifact_id),
            None,
        )
        is_closed = event.last_chunk or (existing.is_closed if existing is not None else False)
        revision = 1 if existing is None else int(existing.revision) + 1
        payload_hash = artifact_payload_hash(materialized)
        now = utcnow()
        _ = await session.execute(
            insert(A2AArtifactProjections)
            .values(
                artifact_projection_id=f"{task.id}:{artifact_id}",
                company_id=company_id,
                task_id=task.id,
                artifact_id=artifact_id,
                ordinal=ordinal,
                artifact_json=artifact_to_json_dict(materialized),
                revision=revision,
                is_closed=is_closed,
                latest_sequence=sequence,
                payload_hash=payload_hash,
                created_at=now,
                updated_at=now,
            )
            .on_conflict_do_update(
                index_elements=["task_id", "artifact_id"],
                set_={
                    "artifact_json": artifact_to_json_dict(materialized),
                    "revision": revision,
                    "is_closed": is_closed,
                    "latest_sequence": sequence,
                    "payload_hash": payload_hash,
                    "updated_at": now,
                },
            )
        )


__all__ = [
    "A2AEventAppendResult",
    "A2APendingEvent",
    "A2AStoredEvent",
    "A2ATaskProjectionMismatchError",
    "A2ATaskRepository",
    "A2ATaskRepositoryError",
]
