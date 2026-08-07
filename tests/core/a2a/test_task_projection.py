"""One lossless Task projection for every A2A delivery mode."""

from __future__ import annotations

import pytest
from a2a.helpers.proto_helpers import new_data_part, new_text_part
from a2a.types import (
    Artifact,
    Message,
    Part,
    Role,
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatusUpdateEvent,
)
from google.protobuf.json_format import MessageToDict

from core.a2a import make_task_status, struct_from_mapping
from core.a2a.task_projection import (
    TaskProjectionAccumulator,
    TaskProjectionError,
    build_task_projection,
)


def _artifact_update(
    artifact_id: str,
    parts: list[Part],
    *,
    name: str = "response",
    last_chunk: bool = False,
) -> TaskArtifactUpdateEvent:
    return TaskArtifactUpdateEvent(
        task_id="task-1",
        context_id="context-1",
        artifact=Artifact(
            artifact_id=artifact_id,
            name=name,
            parts=parts,
        ),
        append=True,
        last_chunk=last_chunk,
    )


def _completed() -> TaskStatusUpdateEvent:
    return TaskStatusUpdateEvent(
        task_id="task-1",
        context_id="context-1",
        status=make_task_status(
            TaskState.TASK_STATE_COMPLETED,
            message=Message(
                message_id="agent-1",
                role=Role.ROLE_AGENT,
                parts=[new_text_part("done")],
            ),
        ),
    )


def test_task_projection_preserves_mixed_artifacts_and_history() -> None:
    """Task contains exact accumulated Artifacts instead of derived text/res."""
    history = [
        Message(
            message_id="user-1",
            role=Role.ROLE_USER,
            parts=[new_text_part("question")],
        )
    ]
    events = [
        _artifact_update("response-1", [new_text_part("hel")]),
        _artifact_update(
            "data-1",
            [new_data_part({"kind": "arbitrary", "value": 7})],
            name="custom-result",
            last_chunk=True,
        ),
        _artifact_update(
            "response-1",
            [Part(url="https://files.linnex.io/download/1")],
            last_chunk=True,
        ),
        _completed(),
    ]

    task = build_task_projection(
        events=events,
        task_id="task-1",
        context_id="context-1",
        history=history,
        require_final_status=True,
    )

    assert task.status.state == TaskState.TASK_STATE_COMPLETED
    assert MessageToDict(task.status.message) == MessageToDict(events[-1].status.message)
    assert [artifact.artifact_id for artifact in task.artifacts] == [
        "response-1",
        "data-1",
    ]
    assert [MessageToDict(part) for part in task.artifacts[0].parts] == [
        MessageToDict(events[0].artifact.parts[0]),
        MessageToDict(events[2].artifact.parts[0]),
    ]
    assert [message.message_id for message in task.history] == ["user-1"]


def test_task_projection_preserves_task_metadata() -> None:
    metadata = struct_from_mapping({"tenant": "linnex", "revision": 7})

    task = build_task_projection(
        events=[_completed()],
        task_id="task-1",
        context_id="context-1",
        metadata=metadata,
        require_final_status=True,
    )

    assert task.metadata == metadata


def test_task_projection_requires_terminal_or_interrupted_status_for_blocking() -> None:
    """A blocking stream ending in WORKING fails instead of guessing completion."""
    projection = TaskProjectionAccumulator(task_id="task-1", context_id="context-1")
    projection.apply(
        TaskStatusUpdateEvent(
            task_id="task-1",
            context_id="context-1",
            status=make_task_status(TaskState.TASK_STATE_WORKING),
        )
    )

    with pytest.raises(TaskProjectionError, match="without terminal/interrupted"):
        projection.build_task(require_final_status=True)


def test_task_projection_accepts_input_required_as_blocking_boundary() -> None:
    """INPUT_REQUIRED is a valid interrupted result and retains its Message."""
    status_event = TaskStatusUpdateEvent(
        task_id="task-1",
        context_id="context-1",
        status=make_task_status(
            TaskState.TASK_STATE_INPUT_REQUIRED,
            message=Message(
                message_id="question-1",
                role=Role.ROLE_AGENT,
                parts=[new_text_part("Need approval")],
            ),
        ),
    )

    task = build_task_projection(
        events=[status_event],
        task_id="task-1",
        context_id="context-1",
        require_final_status=True,
    )

    assert task.status.state == TaskState.TASK_STATE_INPUT_REQUIRED
    assert task.status.message.parts[0].text == "Need approval"


def test_task_projection_rejects_cross_context_event() -> None:
    """Events from another context cannot contaminate a Task projection."""
    projection = TaskProjectionAccumulator(task_id="task-1", context_id="context-1")
    event = _completed()
    event.context_id = "context-2"

    with pytest.raises(TaskProjectionError, match="context_id changed"):
        projection.apply(event)
