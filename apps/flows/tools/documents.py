"""Tools для привязки существующих файлов flow к редактору Documents."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

from apps.flows.src.files.state_file_refs import upsert_state_file, with_document_capability
from apps.flows.src.runtime.tool_call_context import get_active_tool_call_context
from apps.flows.src.runtime_helpers.state_utils import find_file, push_ui_event
from apps.flows.src.tools.decorator import tool
from apps.flows.tools.tool_access import STANDARD_USER_TOOL_GROUPS
from core.clients.service_client import NAMESPACE_HEADER, ServiceClient, ServiceClientError
from core.context import resolve_namespace_or_raise
from core.files.file_ref import FileRef
from core.state import ExecutionState
from core.types import JsonObject, require_json_object

JsonDict = JsonObject


class DocumentsOpenFileArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    file_id: str | None = Field(
        None,
        description="ID файла из state.files[].file_id. Используй его, если он известен.",
    )
    file_name: str | None = Field(
        None,
        description="Имя файла из state.files[].original_name; используется, если file_id не передан.",
    )
    title: str | None = Field(
        None,
        description="Название документа в сервисе documents; если не передано, берётся имя файла.",
    )
    catalog_id: str | None = Field(
        None,
        description="Каталог documents. Не передавай, если пользователь явно не выбрал каталог.",
    )

    @model_validator(mode="after")
    def _require_file_ref(self) -> "DocumentsOpenFileArgs":
        if not self.file_id and not self.file_name:
            raise ValueError("file_id or file_name is required")
        return self


class DocumentsReplaceTextArgs(DocumentsOpenFileArgs):
    find: str = Field(..., min_length=1, description="Точный текст, который надо заменить.")
    replace: str = Field("", description="Текст замены.")
    match_case: bool = Field(False, description="Учитывать регистр при поиске.")


class DocumentsAppendTextArgs(DocumentsOpenFileArgs):
    text: str = Field(..., min_length=1, description="Текст, который нужно добавить в конец документа.")


class DocumentsUpdateCellsArgs(DocumentsOpenFileArgs):
    cells: dict[str, str | int | float | bool | None] = Field(
        ...,
        min_length=1,
        description='Карта Excel/CSV ячеек: {"A1": "value", "B2": 10}.',
    )
    sheet: str | None = Field(None, description="Название листа; null — активный лист.")


def _context_namespace() -> str:
    return resolve_namespace_or_raise()


def _pick_state_file(
    files: Sequence[FileRef],
    *,
    file_id: str | None,
    file_name: str | None,
) -> FileRef | None:
    fid = (file_id or "").strip()
    if fid:
        for item in files:
            if item.file_id == fid:
                return item
    return find_file(files, file_name)


async def _bind_or_get_document(
    *,
    state: ExecutionState,
    file_id: str | None,
    file_name: str | None,
    title: str | None,
    catalog_id: str | None,
) -> tuple[FileRef | None, JsonDict | None, str, str | None]:
    files = list(state.files)
    item = _pick_state_file(files, file_id=file_id, file_name=file_name)
    if item is None:
        return None, None, _context_namespace(), f"Файл не найден. Доступные: {[file_ref.original_name for file_ref in files]}"
    if item.file_id is None:
        return item, None, _context_namespace(), "У файла нет file_id; интерактивное редактирование недоступно."

    namespace = _context_namespace()
    payload: JsonDict = {"file_id": item.file_id}
    if title and title.strip():
        payload["title"] = title.strip()
    if catalog_id and catalog_id.strip():
        payload["catalog_id"] = catalog_id.strip()
    try:
        raw = await ServiceClient().post(
            "office",
            "/documents/api/v1/documents/from-file",
            json=payload,
            headers={NAMESPACE_HEADER: namespace},
        )
    except ServiceClientError as exc:
        return item, None, namespace, str(exc)
    try:
        office_document = require_json_object(raw, "documents.from_file")
    except ValueError as exc:
        return item, None, namespace, str(exc)
    return item, office_document, namespace, None


def _tool_call_id() -> str | None:
    ctx = get_active_tool_call_context()
    return ctx.tool_call_id if ctx is not None and ctx.tool_call_id else None


async def _apply_document_mutation(
    *,
    state: ExecutionState,
    file_id: str | None,
    file_name: str | None,
    title: str | None,
    catalog_id: str | None,
    mutation_path: str,
    mutation_payload: JsonDict,
) -> str:
    item, raw, namespace, error = await _bind_or_get_document(
        state=state,
        file_id=file_id,
        file_name=file_name,
        title=title,
        catalog_id=catalog_id,
    )
    if error or item is None or raw is None:
        return json.dumps({"success": False, "error": error or "Файл недоступен"}, ensure_ascii=False)
    binding_id_value = raw["binding_id"]
    if not isinstance(binding_id_value, str) or not binding_id_value.strip():
        raise ValueError("documents.from_file.binding_id must be a non-empty string")
    binding_id = binding_id_value
    payload = {
        **mutation_payload,
        "tool_call_id": _tool_call_id(),
    }
    try:
        result = await ServiceClient().post(
            "office",
            f"/documents/api/v1/documents/{binding_id}/{mutation_path}",
            json=payload,
            headers={NAMESPACE_HEADER: namespace},
            timeout=60.0,
        )
    except ServiceClientError as exc:
        return json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False)
    try:
        mutation_result = require_json_object(result, "documents.mutation")
    except ValueError as exc:
        return json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False)
    merged = {
        **raw,
        "editor_url": mutation_result["editor_url"],
    }
    enriched = with_document_capability(item, merged, namespace)
    mutation_file_size = mutation_result["file_size"]
    if not isinstance(mutation_file_size, int):
        raise ValueError("documents.mutation.file_size must be an integer")
    mutation_checksum = mutation_result.get("checksum")
    if mutation_checksum is not None and not isinstance(mutation_checksum, str):
        raise ValueError("documents.mutation.checksum must be a string")
    enriched = enriched.model_copy(
        update={"file_size": mutation_file_size, "checksum": mutation_checksum}
    )
    upsert_state_file(state, enriched)
    _ = push_ui_event(
        state,
        event_type="files.updated",
        payload={"files": [enriched.to_json_object()]},
        source="documents",
        correlation_id=binding_id,
    )
    document = enriched.capabilities.document
    if document is None:
        raise ValueError("FileRef.capabilities.document is required after documents mutation")
    return json.dumps(
        {
            "success": True,
            "file": enriched.to_json_object(),
            "document": require_json_object(
                document.model_dump(mode="json"),
                "FileRef.capabilities.document",
            ),
            "mutation": mutation_result,
        },
        ensure_ascii=False,
    )


@tool(
    name="documents_open_file",
    description=(
        "Открывает существующий файл из state.files в интерактивном редакторе documents. "
        "Файл не копируется: documents создаёт привязку к тому же file_id/S3 object. "
        "После успешного вызова state.files[] получает capabilities.document.editor_url, "
        "а пользователь видит файл в панели файлов чата и может редактировать его в iframe."
    ),
    tags=["documents", "files", "office"],
    parameters_model=DocumentsOpenFileArgs,
    permission=list(STANDARD_USER_TOOL_GROUPS),
)
async def documents_open_file(
    file_id: str | None = None,
    file_name: str | None = None,
    title: str | None = None,
    catalog_id: str | None = None,
    *,
    state: ExecutionState,
) -> str:
    files = list(state.files)
    item = _pick_state_file(files, file_id=file_id, file_name=file_name)
    if item is None:
        return json.dumps(
            {
                "success": False,
                "error": f"Файл не найден. Доступные: {[file_ref.original_name for file_ref in files]}",
            },
            ensure_ascii=False,
        )
    if item.file_id is None:
        return json.dumps(
            {"success": False, "error": "У файла нет file_id; интерактивное редактирование недоступно."},
            ensure_ascii=False,
        )

    namespace = _context_namespace()
    payload: JsonDict = {"file_id": item.file_id}
    if title and title.strip():
        payload["title"] = title.strip()
    if catalog_id and catalog_id.strip():
        payload["catalog_id"] = catalog_id.strip()

    try:
        raw = await ServiceClient().post(
            "office",
            "/documents/api/v1/documents/from-file",
            json=payload,
            headers={NAMESPACE_HEADER: namespace},
        )
    except ServiceClientError as exc:
        return json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False)
    try:
        office_document = require_json_object(raw, "documents.open_file")
    except ValueError as exc:
        return json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False)

    enriched = with_document_capability(item, office_document, namespace)
    upsert_state_file(state, enriched)
    binding_id_value = office_document["binding_id"]
    if not isinstance(binding_id_value, str) or not binding_id_value.strip():
        raise ValueError("documents.open_file.binding_id must be a non-empty string")
    _ = push_ui_event(
        state,
        event_type="files.updated",
        payload={"files": [enriched.to_json_object()]},
        source="documents",
        correlation_id=binding_id_value,
    )
    document = enriched.capabilities.document
    if document is None:
        raise ValueError("FileRef.capabilities.document is required after documents_open_file")
    return json.dumps(
        {
            "success": True,
            "file": enriched.to_json_object(),
            "document": require_json_object(
                document.model_dump(mode="json"),
                "FileRef.capabilities.document",
            ),
        },
        ensure_ascii=False,
    )


@tool(
    name="documents_replace_text",
    description=(
        "Заменяет текст в существующем файле documents по тому же file_id. "
        "Поддерживает .docx, .xlsx, .txt, .csv. Перед правкой documents синхронизирует "
        "открытый OnlyOffice редактор через forcesave."
    ),
    tags=["documents", "files", "office"],
    parameters_model=DocumentsReplaceTextArgs,
    permission=list(STANDARD_USER_TOOL_GROUPS),
)
async def documents_replace_text(
    find: str,
    replace: str = "",
    match_case: bool = False,
    file_id: str | None = None,
    file_name: str | None = None,
    title: str | None = None,
    catalog_id: str | None = None,
    *,
    state: ExecutionState,
) -> str:
    return await _apply_document_mutation(
        state=state,
        file_id=file_id,
        file_name=file_name,
        title=title,
        catalog_id=catalog_id,
        mutation_path="mutations/replace-text",
        mutation_payload={"find": find, "replace": replace, "match_case": match_case},
    )


@tool(
    name="documents_append_text",
    description=(
        "Добавляет текст в конец существующего документа по тому же file_id. "
        "Поддерживает .docx и .txt/.csv; открытый редактор синхронизируется перед правкой."
    ),
    tags=["documents", "files", "office"],
    parameters_model=DocumentsAppendTextArgs,
    permission=list(STANDARD_USER_TOOL_GROUPS),
)
async def documents_append_text(
    text: str,
    file_id: str | None = None,
    file_name: str | None = None,
    title: str | None = None,
    catalog_id: str | None = None,
    *,
    state: ExecutionState,
) -> str:
    return await _apply_document_mutation(
        state=state,
        file_id=file_id,
        file_name=file_name,
        title=title,
        catalog_id=catalog_id,
        mutation_path="mutations/append-text",
        mutation_payload={"text": text},
    )


@tool(
    name="documents_update_cells",
    description=(
        "Обновляет ячейки в существующем Excel/CSV файле по тому же file_id. "
        "cells задаётся как JSON object с адресами A1/B2; открытый редактор синхронизируется перед правкой."
    ),
    tags=["documents", "files", "office"],
    parameters_model=DocumentsUpdateCellsArgs,
    permission=list(STANDARD_USER_TOOL_GROUPS),
)
async def documents_update_cells(
    cells: dict[str, str | int | float | bool | None],
    sheet: str | None = None,
    file_id: str | None = None,
    file_name: str | None = None,
    title: str | None = None,
    catalog_id: str | None = None,
    *,
    state: ExecutionState,
) -> str:
    return await _apply_document_mutation(
        state=state,
        file_id=file_id,
        file_name=file_name,
        title=title,
        catalog_id=catalog_id,
        mutation_path="mutations/update-cells",
        mutation_payload={"cells": cells, "sheet": sheet},
    )
