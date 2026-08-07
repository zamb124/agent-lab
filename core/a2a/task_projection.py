"""Shared lossless projection of A2A stream events into a ``Task`` snapshot."""

from __future__ import annotations

from collections.abc import Iterable

from a2a.types import (
    Message,
    Task,
    TaskArtifactUpdateEvent,
    TaskStatus,
    TaskStatusUpdateEvent,
)
from google.protobuf.struct_pb2 import Struct

from core.a2a.artifact_accumulator import ArtifactAccumulator
from core.a2a.task_states import (
    is_interrupted_a2a_task_state,
    is_terminal_a2a_task_state,
)

TaskProjectionEvent = TaskStatusUpdateEvent | TaskArtifactUpdateEvent


class TaskProjectionError(ValueError):
    """A stream cannot be represented as one valid A2A Task."""


def _message_copy(message: Message) -> Message:
    snapshot = Message()
    snapshot.CopyFrom(message)
    return snapshot


def _status_copy(status: TaskStatus) -> TaskStatus:
    snapshot = TaskStatus()
    snapshot.CopyFrom(status)
    return snapshot


class TaskProjectionAccumulator:
    """Materializes status and artifacts through one transport-neutral reducer."""

    task_id: str
    context_id: str
    _artifacts: ArtifactAccumulator
    _latest_status: TaskStatus | None
    _has_final_status: bool
    _event_fingerprints: dict[str, bytes]

    def __init__(self, *, task_id: str, context_id: str) -> None:
        if task_id.strip() == "":
            raise TaskProjectionError("task_id is required")
        if context_id.strip() == "":
            raise TaskProjectionError("context_id is required")
        self.task_id = task_id
        self.context_id = context_id
        self._artifacts = ArtifactAccumulator()
        self._latest_status = None
        self._has_final_status = False
        self._event_fingerprints = {}

    @property
    def has_final_status(self) -> bool:
        return self._has_final_status

    def apply(
        self,
        event: TaskProjectionEvent,
        *,
        event_identity: str | None = None,
    ) -> None:
        """Apply one status/artifact update with optional delivery idempotency."""
        if event_identity is not None:
            if event_identity == "":
                raise TaskProjectionError("event_identity must be non-empty")
            fingerprint = event.SerializeToString(deterministic=True)
            previous = self._event_fingerprints.get(event_identity)
            if previous is not None:
                if previous != fingerprint:
                    raise TaskProjectionError(
                        f"Task event identity collision: {event_identity!r}"
                    )
                return

        self._validate_scope(event)
        if isinstance(event, TaskArtifactUpdateEvent):
            self._artifacts.apply(event)
        else:
            if not event.HasField("status"):
                raise TaskProjectionError("status update must contain status")
            self._latest_status = _status_copy(event.status)
            state = event.status.state
            if is_terminal_a2a_task_state(state) or is_interrupted_a2a_task_state(state):
                self._has_final_status = True

        if event_identity is not None:
            self._event_fingerprints[event_identity] = event.SerializeToString(
                deterministic=True
            )

    def apply_all(self, events: Iterable[TaskProjectionEvent]) -> None:
        for event in events:
            self.apply(event)

    def build_task(
        self,
        *,
        history: Iterable[Message] = (),
        metadata: Struct | None = None,
        require_final_status: bool = False,
    ) -> Task:
        """Build a defensive Task snapshot without re-synthesizing Parts."""
        if self._latest_status is None:
            raise TaskProjectionError(
                f"A2A stream for task {self.task_id!r} contains no status update"
            )
        if require_final_status and not self._has_final_status:
            raise TaskProjectionError(
                f"A2A stream for task {self.task_id!r} ended without terminal/interrupted status"
            )

        task = Task(
            id=self.task_id,
            context_id=self.context_id,
            status=_status_copy(self._latest_status),
        )
        task.artifacts.extend(self._artifacts.artifacts())
        task.history.extend(_message_copy(message) for message in history)
        if metadata is not None:
            task.metadata.CopyFrom(metadata)
        return task

    def _validate_scope(self, event: TaskProjectionEvent) -> None:
        if event.task_id != self.task_id:
            raise TaskProjectionError(
                f"Task event task_id changed: {self.task_id!r} -> {event.task_id!r}"
            )
        if event.context_id != self.context_id:
            raise TaskProjectionError(
                f"Task event context_id changed: {self.context_id!r} -> {event.context_id!r}"
            )


def build_task_projection(
    *,
    events: Iterable[TaskProjectionEvent],
    task_id: str,
    context_id: str,
    history: Iterable[Message] = (),
    metadata: Struct | None = None,
    require_final_status: bool = False,
) -> Task:
    """Convenience entry point shared by blocking and durable projections."""
    projection = TaskProjectionAccumulator(task_id=task_id, context_id=context_id)
    projection.apply_all(events)
    return projection.build_task(
        history=history,
        metadata=metadata,
        require_final_status=require_final_status,
    )


__all__ = [
    "TaskProjectionAccumulator",
    "TaskProjectionError",
    "TaskProjectionEvent",
    "build_task_projection",
]
