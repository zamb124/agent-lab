"""Share-редакция артефакта ``state``: snapshot, JSON Patch и всё, что редакции не подлежит."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from a2a.types import Artifact, Part, Task, TaskArtifactUpdateEvent, TaskState, TaskStatus
from google.protobuf.struct_pb2 import Struct

from apps.flows.src.a2a.share_task_redaction import (
    artifact_event_for_share_viewer,
    redact_artifact,
    task_for_share_viewer,
)
from core.a2a.codec import get_part_data, value_from_json
from core.flow_ui.protocol import (
    FLOW_UI_MEDIA_TYPE,
    JSON_MEDIA_TYPE,
    JSON_PATCH_MEDIA_TYPE,
    STATE_ARTIFACT_ID,
    UI_ARTIFACT_ID,
)
from core.models.flow_ui_share import FlowUIShareGrant
from core.types import JsonValue

pytestmark = [pytest.mark.no_test_doubles]


def _grant(unique_id: str, redacted_paths: list[str]) -> FlowUIShareGrant:
    now = datetime.now(UTC)
    return FlowUIShareGrant(
        grant_id=f"grant-{unique_id}".ljust(24, "0"),
        company_id="system",
        flow_id=f"flow-{unique_id}",
        branch_id="base",
        context_id=f"ctx-{unique_id}",
        permission="viewer",
        redacted_paths=redacted_paths,
        created_by_user_id="u1",
        expires_at=now + timedelta(hours=1),
        created_at=now,
    )


def _data_part(payload: JsonValue, media_type: str) -> Part:
    return Part(data=value_from_json(payload), media_type=media_type)


def _state_artifact(*parts: Part) -> Artifact:
    return Artifact(artifact_id=STATE_ARTIFACT_ID, name=STATE_ARTIFACT_ID, parts=list(parts))


def _parts_json(artifact: Artifact) -> list[JsonValue]:
    return [get_part_data(part) for part in artifact.parts]


class TestSnapshot:
    def test_nested_and_top_level_pointers_are_cut(self, unique_id: str) -> None:
        artifact = _state_artifact(
            _data_part(
                {"name": "Ann", "card": {"number": "4111", "holder": "Ann"}, "notes": ["x"]},
                JSON_MEDIA_TYPE,
            )
        )
        redacted = redact_artifact(artifact, _grant(unique_id, ["/card/number", "/notes", "/missing"]))
        assert _parts_json(redacted) == [{"name": "Ann", "card": {"holder": "Ann"}}]
        assert redacted.parts[0].media_type == JSON_MEDIA_TYPE
        assert redacted.artifact_id == STATE_ARTIFACT_ID and redacted.name == STATE_ARTIFACT_ID
        # исходный артефакт остаётся нетронутым
        assert _parts_json(artifact) == [{"name": "Ann", "card": {"number": "4111", "holder": "Ann"}, "notes": ["x"]}]

    def test_part_metadata_survives_redaction(self, unique_id: str) -> None:
        part = _data_part({"secret": 1, "keep": 2}, JSON_MEDIA_TYPE)
        metadata = Struct()
        metadata.update({"sequence": 7})
        part.metadata.CopyFrom(metadata)
        redacted = redact_artifact(_state_artifact(part), _grant(unique_id, ["/secret"]))
        assert _parts_json(redacted) == [{"keep": 2}]
        assert redacted.parts[0].metadata["sequence"] == 7


class TestPatch:
    def test_operations_inside_redacted_paths_are_dropped(self, unique_id: str) -> None:
        artifact = _state_artifact(
            _data_part(
                [
                    {"op": "replace", "path": "/card/number", "value": "5555"},
                    {"op": "add", "path": "/card/number/last4", "value": "5555"},
                    {"op": "remove", "path": "/card"},
                    {"op": "replace", "path": "/name", "value": "Bob"},
                    {"op": "remove", "path": "/notes"},
                ],
                JSON_PATCH_MEDIA_TYPE,
            )
        )
        redacted = redact_artifact(artifact, _grant(unique_id, ["/card", "/card/number"]))
        assert _parts_json(redacted) == [
            [{"op": "replace", "path": "/name", "value": "Bob"}, {"op": "remove", "path": "/notes"}]
        ]

    def test_redacted_descendants_are_cut_out_of_object_values(self, unique_id: str) -> None:
        artifact = _state_artifact(
            _data_part(
                [
                    {"op": "add", "path": "/card", "value": {"number": "4111", "holder": "Ann", "meta": {"pin": "1"}}},
                    {"op": "replace", "path": "", "value": {"card": {"number": "x"}, "name": "Ann"}},
                    {"op": "replace", "path": "/list", "value": [{"number": "kept-inside-list"}]},
                    {"op": "replace", "path": "/scalar", "value": 5},
                ],
                JSON_PATCH_MEDIA_TYPE,
            )
        )
        redacted = redact_artifact(artifact, _grant(unique_id, ["/card/number", "/card/meta/pin"]))
        assert _parts_json(redacted) == [
            [
                {"op": "add", "path": "/card", "value": {"holder": "Ann", "meta": {}}},
                {"op": "replace", "path": "", "value": {"card": {}, "name": "Ann"}},
                {"op": "replace", "path": "/list", "value": [{"number": "kept-inside-list"}]},
                {"op": "replace", "path": "/scalar", "value": 5},
            ]
        ]

    def test_patch_part_must_be_an_array_and_snapshot_an_object(self, unique_id: str) -> None:
        grant = _grant(unique_id, ["/x"])
        with pytest.raises(ValueError, match="json patch part must carry an array"):
            _ = redact_artifact(_state_artifact(_data_part({"op": "add"}, JSON_PATCH_MEDIA_TYPE)), grant)
        with pytest.raises(ValueError, match="state snapshot must be a JSON object"):
            _ = redact_artifact(_state_artifact(_data_part([1], JSON_MEDIA_TYPE)), grant)
        with pytest.raises(ValueError, match="unexpected state artifact media type"):
            _ = redact_artifact(_state_artifact(_data_part({}, "text/plain")), grant)
        with pytest.raises(ValueError, match="state artifact part must carry data"):
            _ = redact_artifact(_state_artifact(Part(text="oops", media_type=JSON_MEDIA_TYPE)), grant)


class TestPassThrough:
    def test_other_artifacts_and_empty_grants_are_returned_as_is(self, unique_id: str) -> None:
        ui_artifact = Artifact(
            artifact_id=UI_ARTIFACT_ID,
            name=UI_ARTIFACT_ID,
            parts=[_data_part({"kind": "navigate", "page_id": "secret"}, FLOW_UI_MEDIA_TYPE)],
        )
        response = Artifact(artifact_id="response", name="response", parts=[Part(text="card 4111")])
        grant = _grant(unique_id, ["/card"])
        assert redact_artifact(ui_artifact, grant) is ui_artifact
        assert redact_artifact(response, grant) is response
        state = _state_artifact(_data_part({"card": 1}, JSON_MEDIA_TYPE))
        assert redact_artifact(state, _grant(unique_id, [])) is state

    def test_task_and_event_views(self, unique_id: str) -> None:
        state = _state_artifact(_data_part({"card": {"number": "4111"}, "name": "Ann"}, JSON_MEDIA_TYPE))
        response = Artifact(artifact_id="response", name="response", parts=[Part(text="hello")])
        task = Task(
            id=f"task-{unique_id}",
            context_id=f"ctx-{unique_id}",
            status=TaskStatus(state=TaskState.TASK_STATE_COMPLETED),
            artifacts=[state, response],
        )
        grant = _grant(unique_id, ["/card/number"])

        assert task_for_share_viewer(task, None) is task
        assert task_for_share_viewer(task, _grant(unique_id, [])) is task
        viewer_task = task_for_share_viewer(task, grant)
        assert viewer_task.id == task.id and viewer_task.status.state == TaskState.TASK_STATE_COMPLETED
        assert [artifact.artifact_id for artifact in viewer_task.artifacts] == [STATE_ARTIFACT_ID, "response"]
        assert _parts_json(viewer_task.artifacts[0]) == [{"card": {}, "name": "Ann"}]
        assert viewer_task.artifacts[1].parts[0].text == "hello"
        assert _parts_json(task.artifacts[0]) == [{"card": {"number": "4111"}, "name": "Ann"}]

        event = TaskArtifactUpdateEvent(task_id=task.id, context_id=task.context_id, artifact=state, append=True)
        assert artifact_event_for_share_viewer(event, None) is event
        viewer_event = artifact_event_for_share_viewer(event, grant)
        assert viewer_event.append is True and viewer_event.task_id == task.id
        assert _parts_json(viewer_event.artifact) == [{"card": {}, "name": "Ann"}]
        without_artifact = TaskArtifactUpdateEvent(task_id=task.id, context_id=task.context_id)
        assert artifact_event_for_share_viewer(without_artifact, grant) is without_artifact
