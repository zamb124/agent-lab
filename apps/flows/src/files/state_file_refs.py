"""Операции над каноническими FileRef в ExecutionState.files."""

from __future__ import annotations

from core.files.file_ref import FileDocumentCapability, FileRef
from core.state import ExecutionState
from core.types import JsonObject


def _require_non_empty_str(raw: JsonObject, key: str) -> str:
    value = raw[key]
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value.strip()


def _document_type_from_office_payload(raw: JsonObject) -> str:
    if "document_type" in raw:
        return _require_non_empty_str(raw, "document_type")
    if "onlyoffice_document_type" not in raw:
        raise ValueError("office documents payload requires onlyoffice_document_type")
    return _require_non_empty_str(raw, "onlyoffice_document_type")


def file_document_capability(raw: JsonObject, namespace: str) -> FileDocumentCapability:
    if not namespace.strip():
        raise ValueError("namespace must be a non-empty string")
    editor_url = raw["editor_url"]
    if not isinstance(editor_url, str) or not editor_url.strip():
        raise ValueError("editor_url must be a non-empty string")
    return FileDocumentCapability.model_validate(
        {
            "binding_id": _require_non_empty_str(raw, "binding_id"),
            "file_id": _require_non_empty_str(raw, "file_id"),
            "catalog_id": _require_non_empty_str(raw, "catalog_id"),
            "document_type": _document_type_from_office_payload(raw),
            "title": _require_non_empty_str(raw, "title"),
            "namespace": namespace.strip(),
            "editor_url": editor_url.strip(),
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
