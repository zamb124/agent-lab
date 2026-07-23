"""Tools для привязки существующих файлов flow к редактору Documents."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import ClassVar, Literal

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
    document_file_id_value = raw["file_id"]
    if not isinstance(document_file_id_value, str) or not document_file_id_value.strip():
        raise ValueError("documents.from_file.file_id must be a non-empty string")
    document_file_id = document_file_id_value
    payload = {
        **mutation_payload,
        "tool_call_id": _tool_call_id(),
    }
    try:
        result = await ServiceClient().post(
            "office",
            f"/documents/api/v1/documents/{document_file_id}/{mutation_path}",
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
        correlation_id=document_file_id,
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
    document_file_id_value = office_document["file_id"]
    if not isinstance(document_file_id_value, str) or not document_file_id_value.strip():
        raise ValueError("documents.open_file.file_id must be a non-empty string")
    _ = push_ui_event(
        state,
        event_type="files.updated",
        payload={"files": [enriched.to_json_object()]},
        source="documents",
        correlation_id=document_file_id_value,
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


class DocumentsCreateEmptyArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(..., min_length=1, max_length=500, description="Title of the new blank document.")
    document_type: Literal["word", "cell", "slide"] = Field(
        "word",
        description="Blank Office kind: word (.docx), cell (.xlsx/.csv), slide (.pptx).",
    )
    catalog_id: str = Field(
        ...,
        min_length=1,
        description="Target catalog_id. Required when the namespace has catalogs.",
    )
    spreadsheet_format: Literal["xlsx", "csv"] | None = Field(
        None,
        description="Only for document_type=cell. Default xlsx.",
    )


class DocumentsRenameArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    file_id: str = Field(..., min_length=1, description="file_id of the Documents binding.")
    title: str = Field(..., min_length=1, max_length=500, description="New document title.")


class DocumentsMoveArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    file_id: str = Field(..., min_length=1, description="file_id to move.")
    catalog_id: str = Field(..., min_length=1, description="Destination catalog_id.")


class DocumentsCopyArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    file_id: str = Field(..., min_length=1, description="Source file_id.")
    catalog_id: str = Field(..., min_length=1, description="Destination catalog_id.")
    title: str | None = Field(
        None,
        min_length=1,
        max_length=500,
        description="Optional title for the copy. Default: «{title} (copy)».",
    )


class DocumentsListDeletedArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")


class DocumentsFileIdArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    file_id: str = Field(..., min_length=1, description="file_id of the Documents binding.")


def _ns_headers() -> dict[str, str]:
    return {NAMESPACE_HEADER: _context_namespace()}


def _document_item_brief(raw: JsonObject) -> JsonObject:
    return {
        "file_id": raw.get("file_id"),
        "catalog_id": raw.get("catalog_id"),
        "title": raw.get("title"),
        "file_category": raw.get("file_category"),
        "onlyoffice_document_type": raw.get("onlyoffice_document_type"),
        "updated_at": raw.get("updated_at"),
        "file_size": raw.get("file_size"),
    }


@tool(
    name="documents_create_empty",
    description=(
        "Creates a blank Office document in a catalog (word/cell/slide). "
        "Prefer this over create_file when the user wants an empty OOXML in Documents. "
        "Requires catalog_id. Returns file_id, catalog_id, editor_url."
    ),
    tags=["documents", "files", "office"],
    parameters_model=DocumentsCreateEmptyArgs,
    permission=list(STANDARD_USER_TOOL_GROUPS),
)
async def documents_create_empty(
    title: str,
    catalog_id: str,
    document_type: Literal["word", "cell", "slide"] = "word",
    spreadsheet_format: Literal["xlsx", "csv"] | None = None,
    *,
    state: ExecutionState,
) -> JsonObject:
    _ = state
    args = DocumentsCreateEmptyArgs(
        title=title,
        catalog_id=catalog_id,
        document_type=document_type,
        spreadsheet_format=spreadsheet_format,
    )
    body: JsonObject = {
        "title": args.title,
        "document_type": args.document_type,
        "catalog_id": args.catalog_id,
    }
    if args.spreadsheet_format is not None:
        body["spreadsheet_format"] = args.spreadsheet_format
    try:
        raw = await ServiceClient().post(
            "office",
            "/documents/api/v1/documents/empty",
            json=body,
            headers=_ns_headers(),
        )
    except ServiceClientError as exc:
        return {"success": False, "error": str(exc)}
    result = require_json_object(raw, "documents.create_empty")
    return {
        "success": True,
        "file_id": result.get("file_id"),
        "catalog_id": result.get("catalog_id"),
        "title": result.get("title"),
        "file_category": result.get("file_category"),
        "onlyoffice_document_type": result.get("onlyoffice_document_type"),
        "editor_url": result.get("editor_url"),
    }


@tool(
    name="documents_rename",
    description=(
        "Renames a Documents binding title by file_id. "
        "Does not rewrite file bytes. Returns file_id and title."
    ),
    tags=["documents", "files", "office"],
    parameters_model=DocumentsRenameArgs,
    permission=list(STANDARD_USER_TOOL_GROUPS),
)
async def documents_rename(
    file_id: str,
    title: str,
    *,
    state: ExecutionState,
) -> JsonObject:
    _ = state
    args = DocumentsRenameArgs(file_id=file_id, title=title)
    try:
        raw = await ServiceClient().patch(
            "office",
            f"/documents/api/v1/documents/{args.file_id}",
            json={"title": args.title},
            headers=_ns_headers(),
        )
    except ServiceClientError as exc:
        return {"success": False, "error": str(exc)}
    result = require_json_object(raw, "documents.rename")
    return {
        "success": True,
        "file_id": result.get("file_id"),
        "title": result.get("title"),
    }


@tool(
    name="documents_move",
    description=(
        "Moves a Documents binding into another catalog_id. "
        "Requires access to source and destination catalogs. Returns document brief."
    ),
    tags=["documents", "files", "office"],
    parameters_model=DocumentsMoveArgs,
    permission=list(STANDARD_USER_TOOL_GROUPS),
)
async def documents_move(
    file_id: str,
    catalog_id: str,
    *,
    state: ExecutionState,
) -> JsonObject:
    _ = state
    args = DocumentsMoveArgs(file_id=file_id, catalog_id=catalog_id)
    try:
        raw = await ServiceClient().post(
            "office",
            f"/documents/api/v1/documents/{args.file_id}/move",
            json={"catalog_id": args.catalog_id},
            headers=_ns_headers(),
        )
    except ServiceClientError as exc:
        return {"success": False, "error": str(exc)}
    result = require_json_object(raw, "documents.move")
    return {"success": True, **_document_item_brief(result)}


@tool(
    name="documents_copy",
    description=(
        "Copies a Documents file into catalog_id (new file_id). "
        "Optional title. Returns file_id, catalog_id, editor_url."
    ),
    tags=["documents", "files", "office"],
    parameters_model=DocumentsCopyArgs,
    permission=list(STANDARD_USER_TOOL_GROUPS),
)
async def documents_copy(
    file_id: str,
    catalog_id: str,
    title: str | None = None,
    *,
    state: ExecutionState,
) -> JsonObject:
    _ = state
    args = DocumentsCopyArgs(file_id=file_id, catalog_id=catalog_id, title=title)
    body: JsonObject = {"catalog_id": args.catalog_id}
    if args.title is not None:
        body["title"] = args.title
    try:
        raw = await ServiceClient().post(
            "office",
            f"/documents/api/v1/documents/{args.file_id}/copy",
            json=body,
            headers=_ns_headers(),
        )
    except ServiceClientError as exc:
        return {"success": False, "error": str(exc)}
    result = require_json_object(raw, "documents.copy")
    return {
        "success": True,
        "file_id": result.get("file_id"),
        "catalog_id": result.get("catalog_id"),
        "title": result.get("title"),
        "editor_url": result.get("editor_url"),
        "source_file_id": args.file_id,
    }


@tool(
    name="documents_delete",
    description=(
        "Soft-deletes a Documents binding (moves to trash). "
        "Use documents_restore or documents_permanent_delete next. Returns file_id."
    ),
    tags=["documents", "files", "office"],
    parameters_model=DocumentsFileIdArgs,
    permission=list(STANDARD_USER_TOOL_GROUPS),
)
async def documents_delete(file_id: str, *, state: ExecutionState) -> JsonObject:
    _ = state
    args = DocumentsFileIdArgs(file_id=file_id)
    try:
        _ = await ServiceClient().delete(
            "office",
            f"/documents/api/v1/documents/{args.file_id}",
            headers=_ns_headers(),
        )
    except ServiceClientError as exc:
        return {"success": False, "error": str(exc)}
    return {"success": True, "file_id": args.file_id, "deleted": True}


@tool(
    name="documents_list_deleted",
    description=(
        "Lists soft-deleted Documents bindings in the active namespace (trash). "
        "Returns items[] with file_id, title, catalog_id."
    ),
    tags=["documents", "files", "office"],
    parameters_model=DocumentsListDeletedArgs,
    permission=list(STANDARD_USER_TOOL_GROUPS),
)
async def documents_list_deleted(*, state: ExecutionState) -> JsonObject:
    _ = state
    try:
        raw = await ServiceClient().get(
            "office",
            "/documents/api/v1/documents/deleted",
            headers=_ns_headers(),
        )
    except ServiceClientError as exc:
        return {"success": False, "error": str(exc)}
    body = require_json_object(raw, "documents.list_deleted")
    items_raw = body.get("items")
    items: list[JsonObject] = []
    if isinstance(items_raw, list):
        for item in items_raw:
            if isinstance(item, dict):
                items.append(_document_item_brief(require_json_object(item, "deleted.item")))
    return {"success": True, "count": len(items), "items": items}


@tool(
    name="documents_restore",
    description=(
        "Restores a soft-deleted Documents binding from trash. "
        "Returns document brief."
    ),
    tags=["documents", "files", "office"],
    parameters_model=DocumentsFileIdArgs,
    permission=list(STANDARD_USER_TOOL_GROUPS),
)
async def documents_restore(file_id: str, *, state: ExecutionState) -> JsonObject:
    _ = state
    args = DocumentsFileIdArgs(file_id=file_id)
    try:
        raw = await ServiceClient().post(
            "office",
            f"/documents/api/v1/documents/{args.file_id}/restore",
            headers=_ns_headers(),
        )
    except ServiceClientError as exc:
        return {"success": False, "error": str(exc)}
    result = require_json_object(raw, "documents.restore")
    return {"success": True, **_document_item_brief(result)}


@tool(
    name="documents_permanent_delete",
    description=(
        "Permanently deletes a Documents binding that is already in trash. "
        "Not for active documents — soft-delete first. Returns file_id."
    ),
    tags=["documents", "files", "office"],
    parameters_model=DocumentsFileIdArgs,
    permission=list(STANDARD_USER_TOOL_GROUPS),
)
async def documents_permanent_delete(file_id: str, *, state: ExecutionState) -> JsonObject:
    _ = state
    args = DocumentsFileIdArgs(file_id=file_id)
    try:
        _ = await ServiceClient().delete(
            "office",
            f"/documents/api/v1/documents/{args.file_id}/permanent",
            headers=_ns_headers(),
        )
    except ServiceClientError as exc:
        return {"success": False, "error": str(exc)}
    return {"success": True, "file_id": args.file_id, "permanently_deleted": True}
