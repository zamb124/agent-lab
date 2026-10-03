"""Проекция A2A Task: одна таблица — один модуль."""

from apps.flows.src.models.a2a_projection.artifact_projection import (
    A2AArtifactProjection,
)
from apps.flows.src.models.a2a_projection.contracts import (
    A2A_TASK_SNAPSHOT_KIND,
    A2AEventAppendResult,
    A2APendingEvent,
    A2AStoredEvent,
    A2ATaskProjectionMismatchError,
    A2ATaskRepositoryError,
    fingerprint_proto,
    task_state_name,
)
from apps.flows.src.models.a2a_projection.task_event import (
    A2ATaskEvent,
    event_from_row,
)
from apps.flows.src.models.a2a_projection.task_message import (
    A2ATaskMessage,
)
from apps.flows.src.models.a2a_projection.task_projection import (
    A2ATaskProjection,
    task_from_row,
)

__all__ = [
    "A2AArtifactProjection",
    "A2A_TASK_SNAPSHOT_KIND",
    "A2ATaskRepositoryError",
    "A2ATaskProjectionMismatchError",
    "A2AEventAppendResult",
    "A2APendingEvent",
    "A2AStoredEvent",
    "fingerprint_proto",
    "task_state_name",
    "A2ATaskEvent",
    "event_from_row",
    "A2ATaskMessage",
    "A2ATaskProjection",
    "task_from_row",
]
