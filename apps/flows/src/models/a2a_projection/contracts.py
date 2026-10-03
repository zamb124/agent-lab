"""Строки проекции A2A Task в базе flows."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime

from a2a.types import (
    Message,
    Task,
    TaskState,
)

from core.a2a.task_projection import TaskProjectionEvent

A2A_TASK_SNAPSHOT_KIND = "task"
ARTIFACT_UPDATE_KIND = "artifact_update"
STATUS_UPDATE_KIND = "status_update"


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



def fingerprint_proto(message: Message | Task | TaskProjectionEvent) -> str:
    return hashlib.sha256(message.SerializeToString(deterministic=True)).hexdigest()


def task_state_name(task: Task) -> str:
    if not task.HasField("status"):
        raise A2ATaskRepositoryError(f"Task {task.id!r} must contain status")
    return TaskState.Name(task.status.state)





