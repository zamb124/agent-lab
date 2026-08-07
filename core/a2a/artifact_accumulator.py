"""Lossless materialization of A2A ``TaskArtifactUpdateEvent`` streams."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass

from a2a.types import Artifact, TaskArtifactUpdateEvent

from core.a2a.codec import mapping_from_struct, struct_from_mapping
from core.types import JsonObject


class ArtifactAccumulationError(ValueError):
    """An artifact update violates A2A materialization invariants."""


@dataclass(frozen=True)
class ArtifactMaterialization:
    """First-seen order, replace revision and content hash for one Artifact."""

    artifact_id: str
    ordinal: int
    revision: int
    payload_hash: str
    last_chunk: bool


def _artifact_copy(artifact: Artifact) -> Artifact:
    snapshot = Artifact()
    snapshot.CopyFrom(artifact)
    return snapshot


def _merge_json_objects(current: JsonObject, update: JsonObject) -> JsonObject:
    merged: JsonObject = dict(current)
    for key, update_value in update.items():
        current_value = merged.get(key)
        if isinstance(current_value, dict) and isinstance(update_value, dict):
            merged[key] = _merge_json_objects(current_value, update_value)
        else:
            merged[key] = update_value
    return merged


def _event_fingerprint(event: TaskArtifactUpdateEvent) -> bytes:
    return event.SerializeToString(deterministic=True)


def artifact_payload_hash(artifact: Artifact) -> str:
    """SHA-256 of deterministic protobuf bytes for the materialized Artifact."""
    return hashlib.sha256(artifact.SerializeToString(deterministic=True)).hexdigest()


class ArtifactAccumulator:
    """Applies append/replace updates while preserving exact protobuf fields."""

    _artifacts: dict[str, Artifact]
    _order: list[str]
    _closed_artifact_ids: set[str]
    _event_fingerprints: dict[str, bytes]
    _sequence_fingerprints: dict[int, bytes]
    _revisions: dict[str, int]
    _payload_hashes: dict[str, str]
    _latest_sequences: dict[str, int]
    _task_id: str | None
    _context_id: str | None

    def __init__(self) -> None:
        self._artifacts = {}
        self._order = []
        self._closed_artifact_ids = set()
        self._event_fingerprints = {}
        self._sequence_fingerprints = {}
        self._revisions = {}
        self._payload_hashes = {}
        self._latest_sequences = {}
        self._task_id = None
        self._context_id = None

    @property
    def task_id(self) -> str | None:
        return self._task_id

    @property
    def context_id(self) -> str | None:
        return self._context_id

    def apply(
        self,
        event: TaskArtifactUpdateEvent,
        *,
        event_identity: str | None = None,
        sequence: int | None = None,
    ) -> None:
        """Apply one update; repeated identities/sequences are idempotent."""
        if event_identity is not None:
            if event_identity == "":
                raise ArtifactAccumulationError("event_identity must be non-empty")
            fingerprint = _event_fingerprint(event)
            previous = self._event_fingerprints.get(event_identity)
            if previous is not None:
                if previous != fingerprint:
                    raise ArtifactAccumulationError(
                        f"Artifact event identity collision: {event_identity!r}"
                    )
                return

        if sequence is not None:
            if sequence < 1:
                raise ArtifactAccumulationError("sequence must be >= 1")
            fingerprint = _event_fingerprint(event)
            previous_sequence = self._sequence_fingerprints.get(sequence)
            if previous_sequence is not None:
                if previous_sequence != fingerprint:
                    raise ArtifactAccumulationError(
                        f"Artifact sequence collision: {sequence}"
                    )
                return

        self._validate_scope(event)
        if not event.HasField("artifact"):
            raise ArtifactAccumulationError("artifact update must contain artifact")
        artifact_id = event.artifact.artifact_id.strip()
        if artifact_id == "":
            raise ArtifactAccumulationError("artifact.artifact_id is required")
        if artifact_id in self._closed_artifact_ids:
            raise ArtifactAccumulationError(
                f"Artifact {artifact_id!r} is already closed by last_chunk"
            )

        current = self._artifacts.get(artifact_id)
        if current is None or not event.append:
            self._replace(artifact_id, event.artifact)
        else:
            self._append(current, event.artifact)

        if event.last_chunk:
            self._closed_artifact_ids.add(artifact_id)
        materialized = self._artifacts[artifact_id]
        self._payload_hashes[artifact_id] = artifact_payload_hash(materialized)
        if sequence is not None:
            self._latest_sequences[artifact_id] = sequence
            self._sequence_fingerprints[sequence] = _event_fingerprint(event)
        if event_identity is not None:
            self._event_fingerprints[event_identity] = _event_fingerprint(event)

    def apply_all(
        self,
        events: Iterable[TaskArtifactUpdateEvent],
    ) -> None:
        for event in events:
            self.apply(event)

    def artifacts(self) -> list[Artifact]:
        """Return defensive copies in first-encounter order."""
        return [_artifact_copy(self._artifacts[artifact_id]) for artifact_id in self._order]

    def materializations(self) -> list[ArtifactMaterialization]:
        """Return ordinal/revision/hash state in first-encounter order."""
        states: list[ArtifactMaterialization] = []
        for ordinal, artifact_id in enumerate(self._order):
            states.append(
                ArtifactMaterialization(
                    artifact_id=artifact_id,
                    ordinal=ordinal,
                    revision=self._revisions[artifact_id],
                    payload_hash=self._payload_hashes[artifact_id],
                    last_chunk=artifact_id in self._closed_artifact_ids,
                )
            )
        return states

    def materialization(self, artifact_id: str) -> ArtifactMaterialization:
        if artifact_id not in self._artifacts:
            raise ArtifactAccumulationError(f"Unknown artifact_id: {artifact_id!r}")
        return ArtifactMaterialization(
            artifact_id=artifact_id,
            ordinal=self._order.index(artifact_id),
            revision=self._revisions[artifact_id],
            payload_hash=self._payload_hashes[artifact_id],
            last_chunk=artifact_id in self._closed_artifact_ids,
        )

    def latest_sequence(self, artifact_id: str) -> int | None:
        return self._latest_sequences.get(artifact_id)

    def is_closed(self, artifact_id: str) -> bool:
        return artifact_id in self._closed_artifact_ids

    def _validate_scope(self, event: TaskArtifactUpdateEvent) -> None:
        task_id = event.task_id.strip()
        context_id = event.context_id.strip()
        if task_id == "":
            raise ArtifactAccumulationError("artifact update task_id is required")
        if context_id == "":
            raise ArtifactAccumulationError("artifact update context_id is required")
        if self._task_id is None:
            self._task_id = task_id
            self._context_id = context_id
            return
        if task_id != self._task_id:
            raise ArtifactAccumulationError(
                f"Artifact stream task_id changed: {self._task_id!r} -> {task_id!r}"
            )
        if context_id != self._context_id:
            raise ArtifactAccumulationError(
                f"Artifact stream context_id changed: {self._context_id!r} -> {context_id!r}"
            )

    def _replace(self, artifact_id: str, update: Artifact) -> None:
        if artifact_id not in self._artifacts:
            self._order.append(artifact_id)
            self._revisions[artifact_id] = 1
        else:
            self._revisions[artifact_id] = self._revisions[artifact_id] + 1
        self._artifacts[artifact_id] = _artifact_copy(update)

    def _append(self, current: Artifact, update: Artifact) -> None:
        artifact_id = current.artifact_id
        if current.name != update.name:
            raise ArtifactAccumulationError(
                f"Artifact {artifact_id!r} name changed during append: {current.name!r} -> {update.name!r}"
            )
        if current.description != update.description:
            raise ArtifactAccumulationError(
                f"Artifact {artifact_id!r} description changed during append"
            )
        if list(current.extensions) != list(update.extensions):
            raise ArtifactAccumulationError(
                f"Artifact {artifact_id!r} extensions changed during append"
            )

        current.parts.extend(update.parts)
        if update.HasField("metadata"):
            current_metadata = (
                mapping_from_struct(current.metadata)
                if current.HasField("metadata")
                else {}
            )
            update_metadata = mapping_from_struct(update.metadata)
            current.metadata.CopyFrom(
                struct_from_mapping(_merge_json_objects(current_metadata, update_metadata))
            )
        self._revisions[artifact_id] = self._revisions[artifact_id] + 1


__all__ = [
    "ArtifactAccumulationError",
    "ArtifactAccumulator",
    "ArtifactMaterialization",
    "artifact_payload_hash",
]
