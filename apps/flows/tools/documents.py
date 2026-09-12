"""Tools для привязки существующих файлов flow к редактору Documents.

Тонкие обёртки над DocumentsClient; state.files / Flow UI / with_document_capability
остаются в tools.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from typing import Literal

from apps.flows.src.files.state_file_refs import upsert_state_file, with_document_capability
from apps.flows.src.runtime.tool_call_context import get_active_tool_call_context
from apps.flows.src.runtime_helpers.flow_ui_cards import show_files
from apps.flows.src.runtime_helpers.state_utils import find_file
from apps.flows.src.tools.decorator import tool
from apps.flows.tools.tool_access import STANDARD_USER_TOOL_GROUPS
from core.clients.documents_client import DocumentsClient
from core.clients.documents_models import (
    DocumentsAppendTextArgs,
    DocumentsCopyArgs,
    DocumentsCreateEmptyArgs,
    DocumentsEmptyArgs,
    DocumentsFileIdArgs,
    DocumentsMoveArgs,
    DocumentsOpenFileArgs,
    DocumentsRenameArgs,
    DocumentsReplaceTextArgs,
    DocumentsUpdateCellsArgs,
)
from core.context import resolve_namespace_or_raise
from core.files.file_ref import FileRef
from core.state import ExecutionState
from core.types import JsonObject, require_json_object

_TAGS = ["documents"]
_PERM = list(STANDARD_USER_TOOL_GROUPS)
CellValue = str | int | float | bool | None


def _pick_state_file(
    files: Sequence[FileRef],
    *,
    file_id: str | None,
    file_name: str | None,
) -> FileRef:
    fid = (file_id or "").strip()
    if fid:
        for item in files:
            if item.file_id == fid:
                return item
        raise ValueError(
            f"Файл не найден. Доступные: {[file_ref.original_name for file_ref in files]}"
        )
    found = find_file(files, file_name)
    if found is None:
        raise ValueError(
            f"Файл не найден. Доступные: {[file_ref.original_name for file_ref in files]}"
        )
    return found


def _tool_call_id() -> str | None:
    ctx = get_active_tool_call_context()
    return ctx.tool_call_id if ctx is not None and ctx.tool_call_id else None


def _require_document_file_id(office_document: JsonObject, label: str) -> str:
    document_file_id_value = office_document["file_id"]
    if not isinstance(document_file_id_value, str) or not document_file_id_value.strip():
        raise ValueError(f"{label}.file_id must be a non-empty string")
    return document_file_id_value


async def _bind_from_state(
    *,
    state: ExecutionState,
    file_id: str | None,
    file_name: str | None,
    title: str | None,
    catalog_id: str | None,
) -> tuple[FileRef, JsonObject, str]:
    item = _pick_state_file(list(state.files), file_id=file_id, file_name=file_name)
    if item.file_id is None:
        raise ValueError("У файла нет file_id; интерактивное редактирование недоступно.")
    namespace = resolve_namespace_or_raise()
    office_document = await DocumentsClient().from_file(
        file_id=item.file_id,
        title=title,
        catalog_id=catalog_id,
    )
    return item, office_document, namespace


async def _apply_document_mutation(
    *,
    state: ExecutionState,
    file_id: str | None,
    file_name: str | None,
    title: str | None,
    catalog_id: str | None,
    mutate: Callable[[str], Awaitable[JsonObject]],
) -> JsonObject:
    item, office_document, namespace = await _bind_from_state(
        state=state,
        file_id=file_id,
        file_name=file_name,
        title=title,
        catalog_id=catalog_id,
    )
    document_file_id = _require_document_file_id(office_document, "documents.from_file")
    mutation_result = require_json_object(
        await mutate(document_file_id),
        "documents.mutation",
    )
    merged = {
        **office_document,
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
    _ = show_files(state, [enriched])
    document = enriched.capabilities.document
    if document is None:
        raise ValueError("FileRef.capabilities.document is required after documents mutation")
    return {
        "file": enriched.to_json_object(),
        "document": require_json_object(
            document.model_dump(mode="json"),
            "FileRef.capabilities.document",
        ),
        "mutation": mutation_result,
    }


@tool(
    name="documents_open_file",
    description=(
        "Открывает существующий файл из state.files в интерактивном редакторе documents. "
        "Файл не копируется: documents создаёт привязку к тому же file_id/S3 object. "
        "После успешного вызова state.files[] получает capabilities.document.editor_url, "
        "а пользователь видит файл в панели файлов чата и может редактировать его в iframe."
    ),
    tags=_TAGS,
    parameters_model=DocumentsOpenFileArgs,
    permission=_PERM,
)
async def documents_open_file(
    file_id: str | None = None,
    file_name: str | None = None,
    title: str | None = None,
    catalog_id: str | None = None,
    *,
    state: ExecutionState,
) -> JsonObject:
    item, office_document, namespace = await _bind_from_state(
        state=state,
        file_id=file_id,
        file_name=file_name,
        title=title,
        catalog_id=catalog_id,
    )
    enriched = with_document_capability(item, office_document, namespace)
    upsert_state_file(state, enriched)
    _ = show_files(state, [enriched])
    document = enriched.capabilities.document
    if document is None:
        raise ValueError("FileRef.capabilities.document is required after documents_open_file")
    return {
        "file": enriched.to_json_object(),
        "document": require_json_object(
            document.model_dump(mode="json"),
            "FileRef.capabilities.document",
        ),
    }


@tool(
    name="documents_replace_text",
    description=(
        "Заменяет текст в существующем файле documents по тому же file_id. "
        "Поддерживает .docx, .xlsx, .txt, .csv. Перед правкой documents синхронизирует "
        "открытый OnlyOffice редактор через forcesave."
    ),
    tags=_TAGS,
    parameters_model=DocumentsReplaceTextArgs,
    permission=_PERM,
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
) -> JsonObject:
    client = DocumentsClient()
    tool_call_id = _tool_call_id()

    async def _mutate(document_file_id: str) -> JsonObject:
        return await client.replace_text(
            file_id=document_file_id,
            find=find,
            replace=replace,
            match_case=match_case,
            tool_call_id=tool_call_id,
        )

    return await _apply_document_mutation(
        state=state,
        file_id=file_id,
        file_name=file_name,
        title=title,
        catalog_id=catalog_id,
        mutate=_mutate,
    )


@tool(
    name="documents_append_text",
    description=(
        "Добавляет текст в конец существующего документа по тому же file_id. "
        "Поддерживает .docx и .txt/.csv; открытый редактор синхронизируется перед правкой."
    ),
    tags=_TAGS,
    parameters_model=DocumentsAppendTextArgs,
    permission=_PERM,
)
async def documents_append_text(
    text: str,
    file_id: str | None = None,
    file_name: str | None = None,
    title: str | None = None,
    catalog_id: str | None = None,
    *,
    state: ExecutionState,
) -> JsonObject:
    client = DocumentsClient()
    tool_call_id = _tool_call_id()

    async def _mutate(document_file_id: str) -> JsonObject:
        return await client.append_text(
            file_id=document_file_id,
            text=text,
            tool_call_id=tool_call_id,
        )

    return await _apply_document_mutation(
        state=state,
        file_id=file_id,
        file_name=file_name,
        title=title,
        catalog_id=catalog_id,
        mutate=_mutate,
    )


@tool(
    name="documents_update_cells",
    description=(
        "Обновляет ячейки в существующем Excel/CSV файле по тому же file_id. "
        "cells задаётся как JSON object с адресами A1/B2; открытый редактор синхронизируется перед правкой."
    ),
    tags=_TAGS,
    parameters_model=DocumentsUpdateCellsArgs,
    permission=_PERM,
)
async def documents_update_cells(
    cells: dict[str, CellValue],
    sheet: str | None = None,
    file_id: str | None = None,
    file_name: str | None = None,
    title: str | None = None,
    catalog_id: str | None = None,
    *,
    state: ExecutionState,
) -> JsonObject:
    client = DocumentsClient()
    tool_call_id = _tool_call_id()

    async def _mutate(document_file_id: str) -> JsonObject:
        return await client.update_cells(
            file_id=document_file_id,
            cells=cells,
            sheet=sheet,
            tool_call_id=tool_call_id,
        )

    return await _apply_document_mutation(
        state=state,
        file_id=file_id,
        file_name=file_name,
        title=title,
        catalog_id=catalog_id,
        mutate=_mutate,
    )


@tool(
    name="documents_create_empty",
    description=(
        "Creates a blank Office document in a catalog (word/cell/slide). "
        "Prefer this over create_file when the user wants an empty OOXML in Documents. "
        "Requires catalog_id. Returns file_id, catalog_id, editor_url."
    ),
    tags=_TAGS,
    parameters_model=DocumentsCreateEmptyArgs,
    permission=_PERM,
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
    return await DocumentsClient().create_empty(
        title=title,
        catalog_id=catalog_id,
        document_type=document_type,
        spreadsheet_format=spreadsheet_format,
    )


@tool(
    name="documents_rename",
    description=(
        "Renames a Documents binding title by file_id. "
        "Does not rewrite file bytes. Returns file_id and title."
    ),
    tags=_TAGS,
    parameters_model=DocumentsRenameArgs,
    permission=_PERM,
)
async def documents_rename(
    file_id: str,
    title: str,
    *,
    state: ExecutionState,
) -> JsonObject:
    _ = state
    return await DocumentsClient().rename(file_id=file_id, title=title)


@tool(
    name="documents_move",
    description=(
        "Moves a Documents binding into another catalog_id. "
        "Requires access to source and destination catalogs. Returns document brief."
    ),
    tags=_TAGS,
    parameters_model=DocumentsMoveArgs,
    permission=_PERM,
)
async def documents_move(
    file_id: str,
    catalog_id: str,
    *,
    state: ExecutionState,
) -> JsonObject:
    _ = state
    return await DocumentsClient().move(file_id=file_id, catalog_id=catalog_id)


@tool(
    name="documents_copy",
    description=(
        "Copies a Documents file into catalog_id (new file_id). "
        "Optional title. Returns file_id, catalog_id, editor_url."
    ),
    tags=_TAGS,
    parameters_model=DocumentsCopyArgs,
    permission=_PERM,
)
async def documents_copy(
    file_id: str,
    catalog_id: str,
    title: str | None = None,
    *,
    state: ExecutionState,
) -> JsonObject:
    _ = state
    return await DocumentsClient().copy(file_id=file_id, catalog_id=catalog_id, title=title)


@tool(
    name="documents_delete",
    description=(
        "Soft-deletes a Documents binding (moves to trash). "
        "Use documents_restore or documents_permanent_delete next. Returns file_id."
    ),
    tags=_TAGS,
    parameters_model=DocumentsFileIdArgs,
    permission=_PERM,
)
async def documents_delete(file_id: str, *, state: ExecutionState) -> JsonObject:
    _ = state
    return await DocumentsClient().delete(file_id)


@tool(
    name="documents_list_deleted",
    description=(
        "Lists soft-deleted Documents bindings in the active namespace (trash). "
        "Returns items[] with file_id, title, catalog_id."
    ),
    tags=_TAGS,
    parameters_model=DocumentsEmptyArgs,
    permission=_PERM,
)
async def documents_list_deleted(*, state: ExecutionState) -> JsonObject:
    _ = state
    return await DocumentsClient().list_deleted()


@tool(
    name="documents_restore",
    description=(
        "Restores a soft-deleted Documents binding from trash. "
        "Returns document brief."
    ),
    tags=_TAGS,
    parameters_model=DocumentsFileIdArgs,
    permission=_PERM,
)
async def documents_restore(file_id: str, *, state: ExecutionState) -> JsonObject:
    _ = state
    return await DocumentsClient().restore(file_id)


@tool(
    name="documents_permanent_delete",
    description=(
        "Permanently deletes a Documents binding that is already in trash. "
        "Not for active documents — soft-delete first. Returns file_id."
    ),
    tags=_TAGS,
    parameters_model=DocumentsFileIdArgs,
    permission=_PERM,
)
async def documents_permanent_delete(file_id: str, *, state: ExecutionState) -> JsonObject:
    _ = state
    return await DocumentsClient().permanent_delete(file_id)
