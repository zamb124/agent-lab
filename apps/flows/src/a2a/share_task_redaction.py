"""Share-редакция артефакта ``state`` для посетителей по grant с ``redacted_paths``.

Посетитель share видит те же A2A Task и события, что владелец, но значения по
``redacted_paths`` (JSON Pointers) вырезаются из snapshot-части ``state`` и из
операций JSON Patch. Остальные артефакты (``response``, ``reasoning``, ``ui``)
значений полей не несут и проходят без изменений.
"""

from __future__ import annotations

from a2a.types import Artifact, Part, Task, TaskArtifactUpdateEvent

from core.a2a.codec import get_part_data, part_has_data, value_from_json
from core.flow_ui.projection import redact_state
from core.flow_ui.protocol import (
    JSON_MEDIA_TYPE,
    JSON_PATCH_MEDIA_TYPE,
    STATE_ARTIFACT_ID,
    JsonPatchOperation,
)
from core.models.flow_ui_share import FlowUIShareGrant
from core.types import JsonObject, JsonValue, require_json_object


def _pointer_covers(redacted: str, path: str) -> bool:
    return path == redacted or path.startswith(redacted + "/")


def _redact_operation(
    operation: JsonPatchOperation,
    redacted_paths: list[str],
) -> JsonPatchOperation | None:
    """Операция внутри скрытого пути отбрасывается; скрытые потомки вырезаются из значения."""

    if any(_pointer_covers(redacted, operation.path) for redacted in redacted_paths):
        return None
    if operation.op == "remove" or not isinstance(operation.value, dict):
        return operation
    nested = [
        redacted[len(operation.path) :]
        for redacted in redacted_paths
        if redacted.startswith(operation.path + "/")
    ]
    if not nested:
        return operation
    return operation.model_copy(update={"value": redact_state(operation.value, nested)})


def _redact_state_part(part: Part, redacted_paths: list[str]) -> Part:
    if not part_has_data(part):
        raise ValueError("state artifact part must carry data")
    payload: JsonValue = get_part_data(part)
    if part.media_type == JSON_MEDIA_TYPE:
        redacted: JsonValue = redact_state(
            require_json_object(payload, "state snapshot"),
            redacted_paths,
        )
    elif part.media_type == JSON_PATCH_MEDIA_TYPE:
        if not isinstance(payload, list):
            raise ValueError("json patch part must carry an array of operations")
        kept: list[JsonObject] = []
        for raw_operation in payload:
            operation = _redact_operation(
                JsonPatchOperation.model_validate(raw_operation),
                redacted_paths,
            )
            if operation is not None:
                kept.append(require_json_object(operation.model_dump(mode="json"), "json patch op"))
        redacted = kept
    else:
        raise ValueError(f"unexpected state artifact media type {part.media_type!r}")
    redacted_part = Part(data=value_from_json(redacted), media_type=part.media_type)
    if part.HasField("metadata"):
        redacted_part.metadata.CopyFrom(part.metadata)
    return redacted_part


def redact_artifact(artifact: Artifact, grant: FlowUIShareGrant) -> Artifact:
    """Копия артефакта; для ``state`` части редактируются по grant."""

    if artifact.artifact_id != STATE_ARTIFACT_ID or not grant.redacted_paths:
        return artifact
    redacted = Artifact()
    redacted.CopyFrom(artifact)
    del redacted.parts[:]
    redacted.parts.extend(
        _redact_state_part(part, list(grant.redacted_paths)) for part in artifact.parts
    )
    return redacted


def task_for_share_viewer(task: Task, grant: FlowUIShareGrant | None) -> Task:
    """Task для посетителя share: без grant или без ``redacted_paths`` — как есть."""

    if grant is None or not grant.redacted_paths:
        return task
    viewer_task = Task()
    viewer_task.CopyFrom(task)
    del viewer_task.artifacts[:]
    viewer_task.artifacts.extend(redact_artifact(artifact, grant) for artifact in task.artifacts)
    return viewer_task


def artifact_event_for_share_viewer(
    event: TaskArtifactUpdateEvent,
    grant: FlowUIShareGrant | None,
) -> TaskArtifactUpdateEvent:
    """Событие артефакта для посетителя share (replay и live tail)."""

    if grant is None or not grant.redacted_paths or not event.HasField("artifact"):
        return event
    viewer_event = TaskArtifactUpdateEvent()
    viewer_event.CopyFrom(event)
    viewer_event.artifact.CopyFrom(redact_artifact(event.artifact, grant))
    return viewer_event


__all__ = [
    "artifact_event_for_share_viewer",
    "redact_artifact",
    "task_for_share_viewer",
]
