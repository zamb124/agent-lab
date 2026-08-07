"""Rebuild A2A Task UI artifacts for a share viewer after server-side redaction.

Durable ExecutionState and A2A projection stay owner-truthful. Share responses
never serialize forbidden value/content paths.
"""

from __future__ import annotations

from a2a.types import Artifact, Task

from apps.flows.src.a2a.representation_service import FlowUIRepresentationService
from core.a2a import mapping_from_struct
from core.a2a.representation import A2ARepresentationSnapshot
from core.models.flow_ui_share import FlowUIShareGrant
from core.state.flow_ui import FlowUIDocument
from core.state.flow_ui_share_redaction import apply_share_redaction


def _is_flow_ui_artifact(artifact: Artifact) -> bool:
    if artifact.HasField("metadata"):
        metadata = mapping_from_struct(artifact.metadata)
        platform_ui = metadata.get("platformUi")
        if isinstance(platform_ui, dict):
            return True
    name = artifact.name.strip() if artifact.name else ""
    return name == "ui.document" or name.startswith("ui.surface.")


def task_with_share_redaction(
    task: Task,
    *,
    grant: FlowUIShareGrant,
    document: FlowUIDocument,
    representation: A2ARepresentationSnapshot,
) -> Task:
    """Return a Task copy whose Flow UI artifacts are encoded from a redacted document."""
    if not grant.redacted_value_paths:
        return task

    redacted_document = apply_share_redaction(document, grant)
    encoded = FlowUIRepresentationService().encode_snapshot(
        redacted_document,
        representation,
    )
    rebuilt = Task()
    rebuilt.CopyFrom(task)
    kept = [artifact for artifact in rebuilt.artifacts if not _is_flow_ui_artifact(artifact)]
    del rebuilt.artifacts[:]
    rebuilt.artifacts.extend(kept)
    rebuilt.artifacts.extend(encoded)
    return rebuilt


__all__ = ["task_with_share_redaction"]
