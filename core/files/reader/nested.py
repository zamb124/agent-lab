"""Сбор и persist NestedContent из ReadPage.assets."""

from __future__ import annotations

import base64

from core.files.checksum import compute_content_checksum_sha256
from core.files.create_spec import FileSourceKind, FileSourceRef
from core.files.file_ref import FileRef
from core.files.reader.asset_persist import persist_extract_asset
from core.files.reader.markdown import nested_anchor, nested_original_name
from core.files.reader.models import NestedContent, ReadAsset, ReadPage
from core.files.reader.service import FileReader
from core.files.reader.vision import compress_image
from core.files.registry import build_file_create_spec


def nested_from_page_assets(
    page: ReadPage,
    *,
    parent_name: str,
    nest_offset: int = 0,
) -> list[NestedContent]:
    items: list[NestedContent] = []
    for local_index, asset in enumerate(page.assets, start=1):
        nest_index = nest_offset + local_index
        anchor = nested_anchor(page_index=page.index, nest_index=nest_index)
        content_type = asset.content_type
        if content_type is None or not content_type.strip():
            content_type = "application/octet-stream"
        items.append(
            NestedContent(
                anchor=anchor,
                original_name=nested_original_name(parent_name=parent_name, anchor=anchor),
                content_type=content_type,
                kind=asset.kind,
                checksum=asset.checksum,
                page_index=page.index,
                file_id=asset.file_id,
                width=asset.width,
                height=asset.height,
                bytes_b64=asset.bytes_b64,
            )
        )
    return items


def nested_bytes(item: NestedContent) -> bytes:
    if item.bytes_b64 is None or not item.bytes_b64.strip():
        raise ValueError(f"nested {item.original_name!r} has no bytes")
    return base64.b64decode(item.bytes_b64)


def compress_nested_image(item: NestedContent) -> NestedContent:
    if not item.content_type.startswith("image/"):
        return item
    raw = nested_bytes(item)
    try:
        compressed, mime = compress_image(raw)
    except OSError:
        # WMF/EMF и прочий office-media без PIL-loader — оставляем as-is.
        return item
    return item.model_copy(
        update={
            "bytes_b64": base64.b64encode(compressed).decode("utf-8"),
            "content_type": mime,
            "checksum": compute_content_checksum_sha256(compressed),
        }
    )


async def persist_nested_content(
    item: NestedContent,
    *,
    source_file_id: str | None,
    namespace_id: str | None,
    keep_bytes: bool = False,
) -> NestedContent:
    """Persist nested blob → FileRef; RAG namespace если задан, иначе GENERATED_EPHEMERAL."""
    files_service = FileReader.require_files_service()
    data = nested_bytes(item)
    if namespace_id is not None and namespace_id.strip():
        if source_file_id is None or not source_file_id.strip():
            raise ValueError("persist nested with namespace requires source file_id")
        ref = await persist_extract_asset(
            files_service=files_service,
            namespace_id=namespace_id.strip(),
            source_file_id=source_file_id.strip(),
            original_name=item.original_name,
            content_type=item.content_type,
            data=data,
        )
    else:
        entity = source_file_id.strip() if source_file_id is not None and source_file_id.strip() else item.checksum
        spec = build_file_create_spec(
            source_kind=FileSourceKind.GENERATED_EPHEMERAL,
            source_ref=FileSourceRef(entity_id=entity),
            metadata={"nested_of": entity, "anchor": item.anchor},
        )
        record = await files_service.create(
            spec,
            data,
            original_name=item.original_name,
            content_type=item.content_type,
            content_sha256_hex=item.checksum,
        )
        ref = FileRef.model_validate(record)
    return item.model_copy(
        update={
            "file_id": ref.file_id,
            "bytes_b64": item.bytes_b64 if keep_bytes else None,
        }
    )


def asset_from_nested(item: NestedContent) -> ReadAsset:
    return ReadAsset(
        kind=item.kind,
        content_type=item.content_type,
        checksum=item.checksum,
        file_id=item.file_id,
        width=item.width,
        height=item.height,
        bytes_b64=item.bytes_b64,
    )


__all__ = [
    "asset_from_nested",
    "compress_nested_image",
    "nested_bytes",
    "nested_from_page_assets",
    "persist_nested_content",
]
