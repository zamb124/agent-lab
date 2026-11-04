"""A2A Part(raw) из NestedContent для nested_mode=parts."""

from __future__ import annotations

import base64
from collections.abc import Sequence

from a2a.types import Part

from core.files.reader.models import FileResult, NestedContent, NestedMode, ReadFileEnvelope


def nested_to_raw_part(item: NestedContent) -> Part:
    if item.bytes_b64 is None or not item.bytes_b64.strip():
        raise ValueError(f"nested {item.original_name!r} has no bytes for Part")
    return Part(
        raw=base64.b64decode(item.bytes_b64),
        media_type=item.content_type,
        filename=item.original_name,
    )


def parts_from_file_results(files: Sequence[FileResult]) -> list[Part]:
    parts: list[Part] = []
    for file_result in files:
        if file_result.nested_mode is not NestedMode.PARTS:
            continue
        for item in file_result.nested:
            if item.anchor and item.bytes_b64:
                parts.append(nested_to_raw_part(item))
    return parts


def strip_envelope_nested_bytes(envelope: ReadFileEnvelope) -> ReadFileEnvelope:
    files: list[FileResult] = []
    for file_result in envelope.files:
        nested = [
            item.model_copy(update={"bytes_b64": None}) for item in file_result.nested
        ]
        files.append(file_result.model_copy(update={"nested": nested}))
    return envelope.model_copy(update={"files": files})


__all__ = [
    "nested_to_raw_part",
    "parts_from_file_results",
    "strip_envelope_nested_bytes",
]
