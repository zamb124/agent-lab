"""Tools that attach existing flow files to the Documents editor."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from apps.flows.src.runtime.tool_call_context import get_active_tool_call_context
from apps.flows.src.runtime_helpers.state_utils import find_file, push_ui_event
from apps.flows.src.tools.decorator import tool
from apps.flows.tools.tool_access import STANDARD_USER_TOOL_GROUPS
from core.clients.service_client import NAMESPACE_HEADER, ServiceClient, ServiceClientError
from core.context import get_context
from core.state import ExecutionState

JsonDict = dict[str, Any]


class DocumentsOpenFileArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

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
    def _require_file_ref(self):  # noqa: ANN201
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
    ctx = get_context()
    if ctx is None:
        raise RuntimeError("Context is not set")
    ns = (ctx.active_namespace or "default").strip()
    return ns or "default"


def _pick_state_file(files: list[JsonDict], *, file_id: str | None, file_name: str | None) -> JsonDict | None:
    fid = (file_id or "").strip()
    if fid:
        for item in files:
            if str(item.get("file_id") or "") == fid:
                return item
    return find_file(files, file_name)


def _document_capability(raw: JsonDict, namespace: str) -> JsonDict:
    return {
        "kind": "onlyoffice",
        "binding_id": raw["binding_id"],
        "file_id": raw["file_id"],
        "catalog_id": raw["catalog_id"],
        "document_type": raw.get("document_type") or "",
        "title": raw.get("title") or "",
        "namespace": namespace,
        "editor_url": raw.get("editor_url") or "",
        "editable": True,
    }


def _with_document_capability(item: JsonDict, raw: JsonDict, namespace: str) -> JsonDict:
    original_name = item.get("original_name")
    if not isinstance(original_name, str) or not original_name.strip():
        raise ValueError("state.files[].original_name обязателен для documents")
    capabilities = item.get("capabilities")
    if not isinstance(capabilities, dict):
        capabilities = {}
    doc = _document_capability(raw, namespace)
    return {
        **item,
        "file_id": raw["file_id"],
        "original_name": original_name,
        "capabilities": {**capabilities, "document": doc},
        "document": doc,
    }


def _upsert_state_file(state: ExecutionState, item: JsonDict) -> None:
    fid = str(item.get("file_id") or "").strip()
    files = list(state.files or [])
    if fid:
        for idx, existing in enumerate(files):
            if str(existing.get("file_id") or "") == fid:
                files[idx] = {**existing, **item}
                state.files = files
                return
    files.append(item)
    state.files = files


async def _bind_or_get_document(
    *,
    state: ExecutionState,
    file_id: str | None,
    file_name: str | None,
    title: str | None,
    catalog_id: str | None,
) -> tuple[JsonDict | None, JsonDict | None, str, str | None]:
    files = list(state.files or [])
    item = _pick_state_file(files, file_id=file_id, file_name=file_name)
    if item is None:
        return None, None, _context_namespace(), f"Файл не найден. Доступные: {[f.get('original_name') for f in files]}"
    fid = str(item.get("file_id") or "").strip()
    if not fid:
        return item, None, _context_namespace(), "У файла нет file_id; интерактивное редактирование недоступно."

    namespace = _context_namespace()
    payload: JsonDict = {"file_id": fid}
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
    if not isinstance(raw, dict) or not isinstance(raw.get("binding_id"), str):
        return item, None, namespace, "documents: invalid office response"
    return item, raw, namespace, None


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
    binding_id = str(raw["binding_id"])
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
    if not isinstance(result, dict) or not isinstance(result.get("file_id"), str):
        return json.dumps({"success": False, "error": "documents mutation: invalid office response"}, ensure_ascii=False)
    merged = {
        **raw,
        "editor_url": result.get("editor_url") or raw.get("editor_url") or "",
    }
    enriched = _with_document_capability(item, merged, namespace)
    if isinstance(result.get("file_size"), int):
        enriched["file_size"] = result["file_size"]
    _upsert_state_file(state, enriched)
    push_ui_event(
        state,
        event_type="files.updated",
        payload={"files": [enriched]},
        source="documents",
        correlation_id=binding_id,
    )
    return json.dumps(
        {
            "success": True,
            "file": enriched,
            "document": enriched["capabilities"]["document"],
            "mutation": result,
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
    args_schema=DocumentsOpenFileArgs,
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
    files = list(state.files or [])
    item = _pick_state_file(files, file_id=file_id, file_name=file_name)
    if item is None:
        return json.dumps(
            {
                "success": False,
                "error": f"Файл не найден. Доступные: {[f.get('original_name') for f in files]}",
            },
            ensure_ascii=False,
        )
    fid = str(item.get("file_id") or "").strip()
    if not fid:
        return json.dumps(
            {"success": False, "error": "У файла нет file_id; интерактивное редактирование недоступно."},
            ensure_ascii=False,
        )

    namespace = _context_namespace()
    payload: JsonDict = {"file_id": fid}
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
    if not isinstance(raw, dict) or not isinstance(raw.get("binding_id"), str):
        return json.dumps({"success": False, "error": "documents_open_file: invalid office response"}, ensure_ascii=False)

    enriched = _with_document_capability(item, raw, namespace)
    _upsert_state_file(state, enriched)
    push_ui_event(
        state,
        event_type="files.updated",
        payload={"files": [enriched]},
        source="documents",
        correlation_id=str(raw["binding_id"]),
    )
    return json.dumps(
        {
            "success": True,
            "file": enriched,
            "document": enriched["capabilities"]["document"],
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
    args_schema=DocumentsReplaceTextArgs,
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
    args_schema=DocumentsAppendTextArgs,
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
    args_schema=DocumentsUpdateCellsArgs,
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
