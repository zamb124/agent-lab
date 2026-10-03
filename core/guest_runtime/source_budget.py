"""Потолок 50 MiB на дерево исходников code_agent."""

from __future__ import annotations

from core.clients.documents_client import DocumentsClient
from core.config import get_settings
from core.documents.paths import source_catalog_path
from core.files.create_spec import FileCreateSpec, FileSourceKind
from core.guest_runtime.source_tree import walk_code_agent_catalog


def assert_source_bytes_within_cap(
    *,
    existing_bytes: int,
    incoming_bytes: int,
    max_bytes: int,
) -> None:
    if existing_bytes < 0:
        raise ValueError("existing_bytes must be >= 0")
    if incoming_bytes < 0:
        raise ValueError("incoming_bytes must be >= 0")
    if max_bytes < 1:
        raise ValueError("max_bytes must be >= 1")
    total = existing_bytes + incoming_bytes
    if total > max_bytes:
        raise ValueError(f"code_agent source exceeds {max_bytes} bytes: {total}")


async def assert_code_agent_source_upload_fits(
    spec: FileCreateSpec,
    *,
    incoming_bytes: int,
) -> None:
    if FileSourceKind(spec.source_kind) != FileSourceKind.CODE_AGENT_SOURCE:
        return
    max_bytes = get_settings().guest_runtime.max_source_bytes
    flow_id = spec.source_ref.flow_id
    node_id = spec.source_ref.node_id
    if flow_id is None or flow_id.strip() == "":
        raise ValueError("CODE_AGENT_SOURCE flow_id is required")
    if node_id is None or node_id.strip() == "":
        raise ValueError("CODE_AGENT_SOURCE node_id is required")
    documents = DocumentsClient()
    segments = source_catalog_path(
        FileSourceKind.CODE_AGENT_SOURCE,
        spec.source_ref,
    )
    ensured = await documents.ensure_catalog_path(segments)
    existing_files = await walk_code_agent_catalog(documents, ensured.catalog_id)
    existing_bytes = sum(item.file_size for item in existing_files)
    assert_source_bytes_within_cap(
        existing_bytes=existing_bytes,
        incoming_bytes=incoming_bytes,
        max_bytes=max_bytes,
    )
