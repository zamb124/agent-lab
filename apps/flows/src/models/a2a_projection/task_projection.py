"""Таблица проекции A2A."""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar
from uuid import uuid4

from a2a.types import Task, TaskArtifactUpdateEvent, TaskState, TaskStatusUpdateEvent
from oxyde import Field as DbField
from oxyde import Index, atomic
from oxyde.exceptions import IntegrityError

from apps.flows.src.models.a2a_projection.artifact_projection import A2AArtifactProjection
from apps.flows.src.models.a2a_projection.contracts import (
    A2A_TASK_SNAPSHOT_KIND,
    ARTIFACT_UPDATE_KIND,
    STATUS_UPDATE_KIND,
    A2AEventAppendResult,
    A2AStoredEvent,
    A2ATaskProjectionMismatchError,
    A2ATaskRepositoryError,
    fingerprint_proto,
    task_state_name,
)
from apps.flows.src.models.a2a_projection.task_event import A2ATaskEvent, event_from_row
from apps.flows.src.models.a2a_projection.task_message import A2ATaskMessage
from core.a2a import (
    TaskProjectionAccumulator,
    artifact_payload_hash,
    artifact_to_json_dict,
    artifact_update_to_json_dict,
    is_terminal_a2a_task_state,
    mapping_from_struct,
    message_to_json_dict,
    status_update_to_json_dict,
    struct_from_mapping,
    task_from_json_dict,
    task_to_json_dict,
)
from core.a2a.task_projection import TaskProjectionEvent
from core.models.platform_model import PlatformModel
from core.types import JsonObject, require_json_object
from core.utils.time import utcnow


class A2ATaskProjection(PlatformModel):
    """Снимок Task для чтения. Таблица ``a2a_task_projections``."""

    __database_alias__: ClassVar[str | None] = "flows"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "a2a_task_projections"
        unique_together: list[tuple[str, str]] = [("company_id", "task_id")]
        indexes: list[Index] = [
            Index(["company_id", "context_id", "updated_at"]),
            Index(["company_id", "flow_id", "updated_at"]),
            Index(["company_id", "session_id"]),
            Index(["company_id", "owner_user_id", "updated_at"]),
            Index(["company_id", "task_state"]),
        ]

    task_id: str = DbField(db_pk=True)
    company_id: str = DbField()
    context_id: str = DbField()
    session_id: str = DbField()
    flow_id: str = DbField()
    owner_user_id: str = DbField()
    task_state: str = DbField()
    task_json: JsonObject = DbField(db_type="JSONB")
    created_at: datetime = DbField()
    updated_at: datetime = DbField()
    execution_branch_id: str | None = DbField(default=None)
    task_metadata: JsonObject = DbField(default_factory=dict, db_type="JSONB")
    input_message_id: str | None = DbField(default=None)
    flow_config_version: str | None = DbField(default=None)
    latest_sequence: int = DbField(default=0, ge=0)
    is_terminal: bool = DbField(default=False)
    completed_at: datetime | None = DbField(default=None)

    def validate_existing_scope(
        self,
        *,
        company_id: str,
        session_id: str,
        flow_id: str,
        context_id: str,
        owner_user_id: str,
    ) -> None:
        if (
            self.company_id != company_id
            or self.session_id != session_id
            or self.flow_id != flow_id
            or self.context_id != context_id
            or self.owner_user_id != owner_user_id
        ):
            raise A2ATaskRepositoryError(
                f"A2A Task {self.task_id!r} identity belongs to another scope"
            )

    @classmethod
    async def ensure_task(
        cls,
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

        task_json = task_to_json_dict(task)
        task_metadata = mapping_from_struct(task.metadata) if task.HasField("metadata") else {}
        now = utcnow()
        terminal = is_terminal_a2a_task_state(task.status.state)
        projection = cls(
            task_id=task.id,
            company_id=company_id,
            context_id=task.context_id,
            session_id=session_id,
            flow_id=flow_id,
            owner_user_id=owner_user_id,
            execution_branch_id=execution_branch_id,
            task_state=task_state_name(task),
            task_json=task_json,
            task_metadata=task_metadata,
            input_message_id=input_message_id,
            flow_config_version=flow_config_version,
            latest_sequence=0,
            is_terminal=terminal,
            completed_at=now if terminal else None,
            created_at=now,
            updated_at=now,
        )
        try:
            async with atomic(using="flows"):
                _ = await cls.objects.create(instance=projection)
                for ordinal, message in enumerate(task.history):
                    if message.message_id.strip() == "":
                        raise A2ATaskRepositoryError(
                            "Task history Message.message_id is required"
                        )
                    _ = await A2ATaskMessage.objects.create(
                        instance=A2ATaskMessage(
                            task_message_id=f"{task.id}:{message.message_id}",
                            company_id=company_id,
                            task_id=task.id,
                            message_id=message.message_id,
                            ordinal=ordinal,
                            message_json=message_to_json_dict(message),
                            created_at=now,
                        )
                    )
                for ordinal, artifact in enumerate(task.artifacts):
                    if artifact.artifact_id.strip() == "":
                        raise A2ATaskRepositoryError(
                            "Task Artifact.artifact_id is required"
                        )
                    _ = await A2AArtifactProjection.objects.create(
                        instance=A2AArtifactProjection(
                            artifact_projection_id=f"{task.id}:{artifact.artifact_id}",
                            company_id=company_id,
                            task_id=task.id,
                            artifact_id=artifact.artifact_id,
                            ordinal=ordinal,
                            artifact_json=artifact_to_json_dict(artifact),
                            revision=1,
                            is_closed=True,
                            latest_sequence=0,
                            payload_hash=artifact_payload_hash(artifact),
                            created_at=now,
                            updated_at=now,
                        )
                    )
                _ = await A2ATaskEvent.objects.create(
                    instance=A2ATaskEvent(
                        task_event_id=str(uuid4()),
                        company_id=company_id,
                        task_id=task.id,
                        event_identity=f"task:{task.id}:created",
                        sequence=0,
                        event_kind=A2A_TASK_SNAPSHOT_KIND,
                        event_json=task_json,
                        source_fingerprint=fingerprint_proto(task),
                        published_at=now,
                        created_at=now,
                    )
                )
        except IntegrityError:
            async with atomic(using="flows"):
                existing = await cls.objects.filter(task_id=task.id).for_update().first()
                if existing is None:
                    raise
                existing.validate_existing_scope(
                    company_id=company_id,
                    session_id=session_id,
                    flow_id=flow_id,
                    context_id=task.context_id,
                    owner_user_id=owner_user_id,
                )
                snapshot = await A2ATaskEvent.objects.filter(
                    task_id=task.id,
                    sequence=0,
                    event_kind=A2A_TASK_SNAPSHOT_KIND,
                ).first()
                if snapshot is None or snapshot.source_fingerprint != fingerprint_proto(task):
                    raise A2ATaskRepositoryError(
                        f"A2A Task identity collision: {task.id!r}"
                    ) from None
            return False
        return True

    @classmethod
    async def append_event(
        cls,
        *,
        company_id: str,
        event: TaskProjectionEvent,
        event_identity: str,
    ) -> A2AEventAppendResult:
        """Append event and update Task/Artifact projection in one transaction."""
        if event_identity.strip() == "":
            raise A2ATaskRepositoryError("event_identity is required")
        source_fingerprint = fingerprint_proto(event)
        async with atomic(using="flows"):
            task_row = await cls.objects.filter(task_id=event.task_id).for_update().first()
            if task_row is None:
                raise A2ATaskRepositoryError(
                    f"A2A Task {event.task_id!r} must be ensured before event append"
                )
            if task_row.company_id != company_id:
                raise A2ATaskRepositoryError("A2A Task belongs to another company")
            if task_row.context_id != event.context_id:
                raise A2ATaskRepositoryError("A2A event context_id does not match Task")

            duplicate = await A2ATaskEvent.objects.filter(
                task_id=event.task_id,
                event_identity=event_identity,
            ).first()
            if duplicate is not None:
                if duplicate.source_fingerprint != source_fingerprint:
                    raise A2ATaskRepositoryError(
                        f"A2A event identity collision: {event_identity!r}"
                    )
                return A2AEventAppendResult(
                    event=event_from_row(duplicate),
                    sequence=duplicate.sequence,
                    event_identity=event_identity,
                    was_created=False,
                )

            sequence = task_row.latest_sequence + 1
            stored_event = _enrich_event(
                event,
                event_identity=event_identity,
                sequence=sequence,
            )
            current_task = task_from_row(task_row)
            artifact_rows = await (
                A2AArtifactProjection.objects.filter(task_id=event.task_id)
                .order_by("ordinal")
                .all()
            )
            next_task = _apply_event_to_task(
                current_task,
                artifact_rows=artifact_rows,
                event=stored_event,
            )
            task_row.task_json = task_to_json_dict(next_task)
            task_row.task_state = task_state_name(next_task)
            task_row.latest_sequence = sequence
            task_row.is_terminal = is_terminal_a2a_task_state(next_task.status.state)
            updated_at = utcnow()
            task_row.updated_at = updated_at
            if task_row.is_terminal and task_row.completed_at is None:
                task_row.completed_at = updated_at
            _ = await task_row.save()

            if isinstance(stored_event, TaskArtifactUpdateEvent):
                artifact_id = stored_event.artifact.artifact_id
                ordinal = next(
                    index
                    for index, artifact in enumerate(next_task.artifacts)
                    if artifact.artifact_id == artifact_id
                )
                materialized = next_task.artifacts[ordinal]
                existing = next(
                    (row for row in artifact_rows if row.artifact_id == artifact_id),
                    None,
                )
                is_closed = stored_event.last_chunk or (
                    existing.is_closed if existing is not None else False
                )
                revision = 1 if existing is None else existing.revision + 1
                payload_hash = artifact_payload_hash(materialized)
                artifact_updated_at = utcnow()
                artifact_json = artifact_to_json_dict(materialized)
                if existing is None:
                    _ = await A2AArtifactProjection.objects.create(
                        instance=A2AArtifactProjection(
                            artifact_projection_id=f"{next_task.id}:{artifact_id}",
                            company_id=company_id,
                            task_id=next_task.id,
                            artifact_id=artifact_id,
                            ordinal=ordinal,
                            artifact_json=artifact_json,
                            revision=revision,
                            is_closed=is_closed,
                            latest_sequence=sequence,
                            payload_hash=payload_hash,
                            created_at=artifact_updated_at,
                            updated_at=artifact_updated_at,
                        )
                    )
                else:
                    existing.ordinal = ordinal
                    existing.artifact_json = artifact_json
                    existing.revision = revision
                    existing.is_closed = is_closed
                    existing.latest_sequence = sequence
                    existing.payload_hash = payload_hash
                    existing.updated_at = artifact_updated_at
                    _ = await existing.save()

            _ = await A2ATaskEvent.objects.create(
                instance=A2ATaskEvent(
                    task_event_id=str(uuid4()),
                    company_id=company_id,
                    task_id=event.task_id,
                    event_identity=event_identity,
                    sequence=sequence,
                    event_kind=_event_kind(stored_event),
                    event_json=_event_to_json(stored_event),
                    source_fingerprint=source_fingerprint,
                    created_at=utcnow(),
                )
            )
            return A2AEventAppendResult(
                event=stored_event,
                sequence=sequence,
                event_identity=event_identity,
                was_created=True,
            )



    @classmethod
    async def list_events_after_sequence(
        cls,
        *,
        company_id: str,
        task_id: str,
        after_sequence: int,
    ) -> list[A2AStoredEvent]:
        """Return durable events with sequence in (after_sequence, latest]."""
        if after_sequence < 0:
            raise A2ATaskRepositoryError("after_sequence must be >= 0")
        task_row = await A2ATaskProjection.objects.filter(
            company_id=company_id,
            task_id=task_id,
        ).first()
        if task_row is None:
            raise A2ATaskRepositoryError(f"A2A Task {task_id!r} not found")
        if after_sequence > task_row.latest_sequence:
            raise A2ATaskRepositoryError(
                f"after_sequence {after_sequence} is ahead of task latest_sequence {task_row.latest_sequence}"
            )
        rows = await (
            A2ATaskEvent.objects.filter(
                company_id=company_id,
                task_id=task_id,
                sequence__gt=after_sequence,
            )
            .order_by("sequence")
            .all()
        )
        return [
            A2AStoredEvent(
                sequence=row.sequence,
                event_identity=row.event_identity,
                event=event_from_row(row),
                source_fingerprint=row.source_fingerprint,
                published_at=row.published_at,
            )
            for row in rows
        ]

    @classmethod
    async def get_task(cls, *, company_id: str, task_id: str) -> Task | None:
        task_row = await A2ATaskProjection.objects.filter(
            company_id=company_id,
            task_id=task_id,
        ).first()
        if task_row is None:
            return None
        return task_from_row(task_row)

    @classmethod
    async def get_latest_sequence(cls, *, company_id: str, task_id: str) -> int:
        """Sequence of the last durable event of the task (0 — only the submitted snapshot)."""
        _, latest = await cls.get_task_with_sequence(company_id=company_id, task_id=task_id)
        return latest

    @classmethod
    async def get_task_with_sequence(cls, *, company_id: str, task_id: str) -> tuple[Task, int]:
        """Projection Task together with the sequence it reflects — one row, one read.

        A stream that starts with this snapshot continues with events whose sequence is
        greater than the returned one: nothing is lost and nothing is applied twice.
        """
        row = await A2ATaskProjection.objects.filter(
            company_id=company_id,
            task_id=task_id,
        ).first()
        if row is None:
            raise A2ATaskRepositoryError(f"A2A Task {task_id!r} not found")
        return task_from_row(row), row.latest_sequence

    @classmethod
    async def get_task_for_owner(
        cls,
        *,
        company_id: str,
        owner_user_id: str,
        task_id: str,
    ) -> Task | None:
        row = await A2ATaskProjection.objects.filter(
            company_id=company_id,
            owner_user_id=owner_user_id,
            task_id=task_id,
        ).first()
        if row is None:
            return None
        return task_from_row(row)

    @classmethod
    async def get_task_for_context(
        cls,
        *,
        company_id: str,
        flow_id: str,
        context_id: str,
        task_id: str,
    ) -> Task | None:
        """Read a task after an external access service authorized its context."""
        row = await A2ATaskProjection.objects.filter(
            company_id=company_id,
            flow_id=flow_id,
            context_id=context_id,
            task_id=task_id,
        ).first()
        if row is None:
            return None
        return task_from_row(row)

    @classmethod
    async def task_exists_in_scope(
        cls,
        *,
        company_id: str,
        task_id: str,
        session_id: str,
        flow_id: str,
        context_id: str,
        owner_user_id: str,
    ) -> bool:
        row = await A2ATaskProjection.objects.filter(task_id=task_id).first()
        if row is None:
            return False
        row.validate_existing_scope(
            company_id=company_id,
            session_id=session_id,
            flow_id=flow_id,
            context_id=context_id,
            owner_user_id=owner_user_id,
        )
        return True

    @classmethod
    async def get_latest_for_context(
        cls,
        *,
        company_id: str,
        owner_user_id: str,
        flow_id: str,
        context_id: str,
    ) -> Task | None:
        task_row = await (
            A2ATaskProjection.objects.filter(
                company_id=company_id,
                owner_user_id=owner_user_id,
                flow_id=flow_id,
                context_id=context_id,
            )
            .order_by("-updated_at")
            .first()
        )
        if task_row is None:
            return None
        return task_from_row(task_row)

    @classmethod
    async def list_tasks(
        cls,
        *,
        company_id: str,
        owner_user_id: str,
        flow_id: str,
        context_id: str | None,
        task_state: int | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Task], int]:
        query = A2ATaskProjection.objects.filter(
            company_id=company_id,
            owner_user_id=owner_user_id,
            flow_id=flow_id,
        )
        if context_id is not None:
            query = query.filter(context_id=context_id)
        if task_state is not None:
            query = query.filter(task_state=TaskState.Name(task_state))
        total = await query.count()
        rows = await query.order_by("-updated_at").limit(limit).offset(offset).all()
        return [task_from_row(row) for row in rows], total

    @classmethod
    async def list_tasks_for_context(
        cls,
        *,
        company_id: str,
        flow_id: str,
        context_id: str,
        task_state: int | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Task], int]:
        """List only one pre-authorized live-share context."""
        query = A2ATaskProjection.objects.filter(
            company_id=company_id,
            flow_id=flow_id,
            context_id=context_id,
        )
        if task_state is not None:
            query = query.filter(task_state=TaskState.Name(task_state))
        total = await query.count()
        rows = await query.order_by("-updated_at").limit(limit).offset(offset).all()
        return [task_from_row(row) for row in rows], total

    @classmethod
    async def rebuild_task(cls, *, company_id: str, task_id: str) -> Task:
        """Replay task snapshot + events and verify the query projection."""
        task_row = await A2ATaskProjection.objects.filter(
            company_id=company_id,
            task_id=task_id,
        ).first()
        if task_row is None:
            raise A2ATaskRepositoryError(f"A2A Task {task_id!r} not found")
        rows = await (
            A2ATaskEvent.objects.filter(task_id=task_id).order_by("sequence").all()
        )
        if not rows or rows[0].event_kind != A2A_TASK_SNAPSHOT_KIND:
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
            projection.apply(event_from_row(row), event_identity=row.event_identity)
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
        return ARTIFACT_UPDATE_KIND
    return STATUS_UPDATE_KIND

def _event_to_json(event: TaskProjectionEvent) -> JsonObject:
    if isinstance(event, TaskArtifactUpdateEvent):
        return artifact_update_to_json_dict(event)
    return status_update_to_json_dict(event)

def task_from_row(row: A2ATaskProjection) -> Task:
    return task_from_json_dict(require_json_object(row.task_json, "A2ATask.task_json"))

def _apply_event_to_task(
    current_task: Task,
    *,
    artifact_rows: list[A2AArtifactProjection],
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
