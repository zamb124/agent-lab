"""Операции над каноническими FileRef в ExecutionState.files."""

from __future__ import annotations

from core.files.file_ref import FileDocumentCapability, FileRef
from core.state import ExecutionState
from core.types import JsonObject


def file_document_capability(raw: JsonObject, namespace: str) -> FileDocumentCapability:
    return FileDocumentCapability.model_validate(
        {
            "binding_id": raw["binding_id"],
            "file_id": raw["file_id"],
            "catalog_id": raw["catalog_id"],
            "document_type": raw["document_type"],
            "title": raw["title"],
            "namespace": namespace,
            "editor_url": raw["editor_url"],
            "editable": True,
        }
    )


def with_document_capability(file_ref: FileRef, raw: JsonObject, namespace: str) -> FileRef:
    document = file_document_capability(raw, namespace)
    return file_ref.model_copy(
        update={
            "file_id": document.file_id,
            "capabilities": file_ref.capabilities.model_copy(update={"document": document}),
        }
    )


def upsert_state_file(state: ExecutionState, file_ref: FileRef) -> None:
    files = list(state.files)
    if file_ref.file_id is not None:
        for index, existing_file_ref in enumerate(files):
            if existing_file_ref.file_id == file_ref.file_id:
                files[index] = file_ref
                state.files = files
                return
    files.append(file_ref)
    state.files = files


__all__ = [
    "file_document_capability",
    "upsert_state_file",
    "with_document_capability",
]
