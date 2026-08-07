"""Lossless materialization of A2A artifact update streams."""

from __future__ import annotations

import pytest
from a2a.helpers.proto_helpers import new_data_part, new_text_part
from a2a.types import Artifact, Part, TaskArtifactUpdateEvent
from google.protobuf.json_format import MessageToDict

from core.a2a.artifact_accumulator import (
    ArtifactAccumulationError,
    ArtifactAccumulator,
)
from core.a2a.codec import struct_from_mapping


def _artifact(
    artifact_id: str,
    *,
    name: str = "response",
    parts: list[Part],
) -> Artifact:
    artifact = Artifact(
        artifact_id=artifact_id,
        name=name,
        description="A lossless artifact",
        parts=parts,
        extensions=["https://linnex.io/a2a/extensions/example/v1"],
    )
    artifact.metadata.CopyFrom(
        struct_from_mapping({"source": "test", "nested": {"first": 1}})
    )
    return artifact


def _update(
    artifact: Artifact,
    *,
    append: bool,
    last_chunk: bool = False,
) -> TaskArtifactUpdateEvent:
    return TaskArtifactUpdateEvent(
        task_id="task-1",
        context_id="context-1",
        artifact=artifact,
        append=append,
        last_chunk=last_chunk,
    )


def _proto_json(artifact: Artifact) -> dict[str, object]:
    return MessageToDict(artifact)


def test_accumulator_round_trips_all_part_variants_and_artifact_fields() -> None:
    """Text/raw/url/data, metadata and extensions survive without synthesis."""
    raw_part = Part(
        raw=b"\x00\x01payload",
        filename="payload.bin",
        media_type="application/octet-stream",
    )
    raw_part.metadata.CopyFrom(struct_from_mapping({"checksum": "sha256:test"}))
    url_part = Part(
        url="https://files.linnex.io/download/file-1",
        filename="report.pdf",
        media_type="application/pdf",
    )
    data_part = new_data_part(
        {"rows": [{"name": "alpha", "enabled": True}], "count": 1}
    )
    source = _artifact(
        "artifact-1",
        parts=[new_text_part("hello"), raw_part, url_part, data_part],
    )
    accumulator = ArtifactAccumulator()

    accumulator.apply(_update(source, append=False, last_chunk=True))

    snapshots = accumulator.artifacts()
    assert len(snapshots) == 1
    assert _proto_json(snapshots[0]) == _proto_json(source)


def test_accumulator_append_preserves_order_and_recursively_merges_metadata() -> None:
    """First encounter orders artifacts; append adds Parts without field loss."""
    first = _artifact("artifact-1", parts=[new_text_part("A")])
    second = _artifact("artifact-2", name="files", parts=[new_data_part({"file": 1})])
    continuation = _artifact("artifact-1", parts=[new_text_part("B")])
    continuation.metadata.CopyFrom(
        struct_from_mapping({"source": "test", "nested": {"second": 2}})
    )
    accumulator = ArtifactAccumulator()

    accumulator.apply(_update(first, append=False))
    accumulator.apply(_update(second, append=False, last_chunk=True))
    accumulator.apply(_update(continuation, append=True, last_chunk=True))

    snapshots = accumulator.artifacts()
    assert [artifact.artifact_id for artifact in snapshots] == [
        "artifact-1",
        "artifact-2",
    ]
    assert [part.text for part in snapshots[0].parts] == ["A", "B"]
    assert MessageToDict(snapshots[0].metadata) == {
        "source": "test",
        "nested": {"first": 1.0, "second": 2.0},
    }


def test_accumulator_replace_overwrites_complete_artifact_without_reordering() -> None:
    """append=false replaces all artifact fields at the original position."""
    original = _artifact("artifact-1", parts=[new_text_part("old")])
    replacement = Artifact(
        artifact_id="artifact-1",
        name="replacement",
        description="new description",
        parts=[new_data_part({"value": "new"})],
        extensions=["https://linnex.io/a2a/extensions/replacement/v1"],
    )
    replacement.metadata.CopyFrom(struct_from_mapping({"replacement": True}))
    accumulator = ArtifactAccumulator()

    accumulator.apply(_update(original, append=False))
    accumulator.apply(_update(replacement, append=False, last_chunk=True))

    assert _proto_json(accumulator.artifacts()[0]) == _proto_json(replacement)


def test_accumulator_rejects_update_after_last_chunk() -> None:
    """lastChunk closes the artifact identity for later updates."""
    artifact = _artifact("artifact-1", parts=[new_text_part("complete")])
    continuation = _artifact("artifact-1", parts=[new_text_part("late")])
    accumulator = ArtifactAccumulator()
    accumulator.apply(_update(artifact, append=False, last_chunk=True))

    with pytest.raises(ArtifactAccumulationError, match="already closed"):
        accumulator.apply(_update(continuation, append=True))


def test_accumulator_rejects_append_contract_changes() -> None:
    """Append cannot silently change name, description or extensions."""
    artifact = _artifact("artifact-1", parts=[new_text_part("first")])
    changed = _artifact(
        "artifact-1",
        name="different",
        parts=[new_text_part("second")],
    )
    accumulator = ArtifactAccumulator()
    accumulator.apply(_update(artifact, append=False))

    with pytest.raises(ArtifactAccumulationError, match="name changed"):
        accumulator.apply(_update(changed, append=True))


def test_accumulator_requires_artifact_identity_and_consistent_task_scope() -> None:
    """Missing artifact ID or cross-task updates fail closed."""
    accumulator = ArtifactAccumulator()
    without_id = Artifact(name="response", parts=[new_text_part("text")])

    with pytest.raises(ArtifactAccumulationError, match="artifact_id is required"):
        accumulator.apply(_update(without_id, append=False))

    accumulator.apply(
        _update(_artifact("artifact-1", parts=[new_text_part("first")]), append=False)
    )
    wrong_task = _update(
        _artifact("artifact-2", parts=[new_text_part("second")]),
        append=False,
    )
    wrong_task.task_id = "task-2"
    with pytest.raises(ArtifactAccumulationError, match="task_id changed"):
        accumulator.apply(wrong_task)


def test_accumulator_event_identity_is_idempotent_and_detects_collision() -> None:
    """A repeated event identity is accepted only for byte-identical protobuf."""
    accumulator = ArtifactAccumulator()
    event = _update(
        _artifact("artifact-1", parts=[new_text_part("once")]),
        append=False,
    )

    accumulator.apply(event, event_identity="event-1")
    accumulator.apply(event, event_identity="event-1")
    assert len(accumulator.artifacts()) == 1

    collision = _update(
        _artifact("artifact-1", parts=[new_text_part("different")]),
        append=False,
    )
    with pytest.raises(ArtifactAccumulationError, match="identity collision"):
        accumulator.apply(collision, event_identity="event-1")


def test_accumulator_tracks_ordinal_revision_and_payload_hash() -> None:
    """First-seen ordinal is stable; replace/append bumps revision and hash."""
    accumulator = ArtifactAccumulator()
    first = _update(_artifact("artifact-1", parts=[new_text_part("A")]), append=False)
    second = _update(
        _artifact("artifact-2", name="files", parts=[new_data_part({"file": 1})]),
        append=False,
        last_chunk=True,
    )
    replace = _update(_artifact("artifact-1", parts=[new_text_part("B")]), append=False)
    append = _update(_artifact("artifact-1", parts=[new_text_part("C")]), append=True)

    accumulator.apply(first, sequence=1)
    accumulator.apply(second, sequence=2)
    states = accumulator.materializations()
    assert [item.artifact_id for item in states] == ["artifact-1", "artifact-2"]
    assert states[0].ordinal == 0
    assert states[0].revision == 1
    assert states[1].ordinal == 1
    assert states[1].last_chunk is True
    hash_before = states[0].payload_hash

    accumulator.apply(replace, sequence=3)
    replaced = accumulator.materialization("artifact-1")
    assert replaced.ordinal == 0
    assert replaced.revision == 2
    assert replaced.payload_hash != hash_before

    accumulator.apply(append, sequence=4)
    appended = accumulator.materialization("artifact-1")
    assert appended.ordinal == 0
    assert appended.revision == 3
    assert accumulator.latest_sequence("artifact-1") == 4


def test_accumulator_sequence_is_idempotent_and_detects_collision() -> None:
    accumulator = ArtifactAccumulator()
    event = _update(_artifact("artifact-1", parts=[new_text_part("once")]), append=False)
    accumulator.apply(event, sequence=7)
    accumulator.apply(event, sequence=7)
    assert accumulator.materialization("artifact-1").revision == 1

    collision = _update(
        _artifact("artifact-1", parts=[new_text_part("different")]),
        append=False,
    )
    with pytest.raises(ArtifactAccumulationError, match="sequence collision"):
        accumulator.apply(collision, sequence=7)


def test_accumulator_returns_defensive_protobuf_copies() -> None:
    """Consumers cannot mutate the authoritative accumulated projection."""
    accumulator = ArtifactAccumulator()
    accumulator.apply(
        _update(_artifact("artifact-1", parts=[new_text_part("stable")]), append=False)
    )

    snapshot = accumulator.artifacts()[0]
    snapshot.parts[0].text = "mutated"

    assert accumulator.artifacts()[0].parts[0].text == "stable"
