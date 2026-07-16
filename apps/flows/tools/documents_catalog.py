"""Platform Documents catalog tools — browse/search/read/link for Flows and Lara.

Shared tag pack: documents / office / catalog. Usable on any llm_node via
builtin registry; Lara unlocks the same ids through skill documents-catalog.
"""

from __future__ import annotations

from typing import ClassVar, Literal
from urllib.parse import quote

from pydantic import BaseModel, ConfigDict, Field, model_validator

from apps.flows.src.tools.decorator import tool
from apps.flows.tools.tool_access import STANDARD_USER_TOOL_GROUPS
from core.clients.service_client import NAMESPACE_HEADER, ServiceClient, ServiceClientError
from core.context import resolve_namespace_or_raise
from core.files.file_ref import FileRef
from core.files.reader.engine import read_files_to_envelope
from core.files.reader.models import MAX_READ_BUDGET, CompressionMode, ReadFileArgs
from core.state import ExecutionState
from core.types import JsonObject, JsonValue, require_json_array, require_json_object

_DOCUMENTS_CATALOG_TAGS = ["documents", "office", "catalog"]


class DocumentsListCatalogArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    catalog_id: str | None = Field(
        None,
        description=(
            "Каталог для browse. Без параметра — корень: только каталоги с "
            "parent_catalog_id=null (документов на виртуальном корне нет)."
        ),
    )


class DocumentsFindArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    query: str = Field(..., min_length=1, max_length=500, description="Поисковый запрос.")
    catalog_id: str | None = Field(
        None,
        description="Scope каталога. Для semantic обязателен; для lexical без него — весь namespace.",
    )
    mode: Literal["auto", "semantic", "lexical"] = Field(
        "auto",
        description=(
            "auto — semantic если rag_index_enabled, иначе lexical; "
            "semantic без индекса возвращает rag_index_disabled; lexical всегда title search."
        ),
    )
    limit: int = Field(20, ge=1, le=50, description="Лимит результатов.")


class DocumentsReadArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    binding_id: str | None = Field(None, description="ID привязки документа в Documents.")
    file_id: str | None = Field(None, description="ID файла платформы, если binding_id неизвестен.")
    page_start: int = Field(0, ge=0, description="Первая страница (0-based), как у read_file.")
    page_end: int = Field(-1, description="Последняя страница включительно; -1 — до конца.")
    budget: int = Field(MAX_READ_BUDGET, ge=0, description="Лимит символов результата.")

    @model_validator(mode="after")
    def _require_id(self) -> "DocumentsReadArgs":
        has_binding = isinstance(self.binding_id, str) and self.binding_id.strip() != ""
        has_file = isinstance(self.file_id, str) and self.file_id.strip() != ""
        if not has_binding and not has_file:
            raise ValueError("binding_id or file_id is required")
        return self


class DocumentsGetLinkArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    binding_id: str = Field(..., min_length=1, description="ID привязки документа.")
    kind: Literal["editor", "preview"] = Field(
        "editor",
        description="editor — SPA path /documents/edit/...; preview — preview_url из BFF.",
    )


def _namespace() -> str:
    return resolve_namespace_or_raise()


def _ns_headers() -> dict[str, str]:
    return {NAMESPACE_HEADER: _namespace()}


def _as_object_list(value: object, label: str) -> list[JsonObject]:
    items = require_json_array(value, label)
    out: list[JsonObject] = []
    for index, item in enumerate(items):
        out.append(require_json_object(item, f"{label}[{index}]"))
    return out


def _catalog_summary(item: JsonObject) -> JsonObject:
    return {
        "catalog_id": item["catalog_id"],
        "title": item["title"],
        "file_count": item.get("file_count"),
        "rag_index_enabled": item.get("rag_index_enabled"),
        "parent_catalog_id": item.get("parent_catalog_id"),
    }


def _document_summary(item: JsonObject) -> JsonObject:
    return {
        "binding_id": item["binding_id"],
        "file_id": item["file_id"],
        "title": item["title"],
        "file_category": item.get("file_category"),
        "catalog_id": item.get("catalog_id"),
        "updated_at": item.get("updated_at"),
        "file_size": item.get("file_size"),
    }


async def _list_all_catalogs(client: ServiceClient) -> list[JsonObject]:
    raw = await client.get(
        "office",
        "/documents/api/v1/catalogs",
        headers=_ns_headers(),
    )
    body = require_json_object(raw, "documents.catalogs")
    return _as_object_list(body.get("items"), "documents.catalogs.items")


async def _list_documents_in_catalog(
    client: ServiceClient,
    catalog_id: str,
    *,
    query: str | None = None,
) -> list[JsonObject]:
    params: dict[str, str] = {"catalog_id": catalog_id}
    if query is not None and query.strip() != "":
        params["q"] = query.strip()
    raw = await client.get(
        "office",
        "/documents/api/v1/documents",
        headers=_ns_headers(),
        params=params,
    )
    body = require_json_object(raw, "documents.list")
    return _as_object_list(body.get("items"), "documents.list.items")


async def _catalog_by_id(client: ServiceClient, catalog_id: str) -> JsonObject | None:
    for item in await _list_all_catalogs(client):
        cid = item.get("catalog_id")
        if isinstance(cid, str) and cid == catalog_id:
            return item
    return None


async def _resolve_binding_file(
    client: ServiceClient,
    binding_id: str,
) -> JsonObject:
    raw = await client.get(
        "office",
        f"/documents/api/v1/documents/{quote(binding_id, safe='')}/editor-config",
        headers=_ns_headers(),
    )
    return require_json_object(raw, "documents.editor_config")


@tool(
    name="documents_list_catalog",
    description=(
        "Browse Documents catalog tree. Without catalog_id returns root catalogs "
        "(parent_catalog_id=null). With catalog_id returns child catalogs and documents "
        "in that catalog (non-recursive)."
    ),
    tags=_DOCUMENTS_CATALOG_TAGS,
    parameters_model=DocumentsListCatalogArgs,
    permission=list(STANDARD_USER_TOOL_GROUPS),
)
async def documents_list_catalog(
    catalog_id: str | None = None,
    *,
    state: ExecutionState,
) -> JsonObject:
    _ = state
    client = ServiceClient()
    try:
        catalogs = await _list_all_catalogs(client)
    except ServiceClientError as exc:
        return {"success": False, "error": str(exc)}

    resolved = catalog_id.strip() if isinstance(catalog_id, str) and catalog_id.strip() else None
    if resolved is None:
        root_catalogs = [
            _catalog_summary(item)
            for item in catalogs
            if item.get("parent_catalog_id") is None
        ]
        return {
            "success": True,
            "catalog_id": None,
            "catalogs": root_catalogs,
            "documents": [],
        }

    child_catalogs = [
        _catalog_summary(item)
        for item in catalogs
        if item.get("parent_catalog_id") == resolved
    ]
    try:
        documents = [
            _document_summary(item)
            for item in await _list_documents_in_catalog(client, resolved)
        ]
    except ServiceClientError as exc:
        return {"success": False, "error": str(exc), "catalog_id": resolved}
    return {
        "success": True,
        "catalog_id": resolved,
        "catalogs": child_catalogs,
        "documents": documents,
    }


@tool(
    name="documents_find",
    description=(
        "Find documents in Documents. mode=auto uses catalog semantic search when "
        "rag_index_enabled, otherwise lexical title search. Explicit semantic fails "
        "with rag_index_disabled when index is off."
    ),
    tags=_DOCUMENTS_CATALOG_TAGS,
    parameters_model=DocumentsFindArgs,
    permission=list(STANDARD_USER_TOOL_GROUPS),
)
async def documents_find(
    query: str,
    catalog_id: str | None = None,
    mode: Literal["auto", "semantic", "lexical"] = "auto",
    limit: int = 20,
    *,
    state: ExecutionState,
) -> JsonObject:
    _ = state
    client = ServiceClient()
    q = query.strip()
    resolved_catalog = (
        catalog_id.strip() if isinstance(catalog_id, str) and catalog_id.strip() else None
    )

    use_semantic = False
    if mode == "semantic":
        use_semantic = True
    elif mode == "auto" and resolved_catalog is not None:
        try:
            catalog = await _catalog_by_id(client, resolved_catalog)
        except ServiceClientError as exc:
            return {"success": False, "error": str(exc)}
        if catalog is None:
            return {
                "success": False,
                "error": f"catalog_id not found or not accessible: {resolved_catalog}",
            }
        use_semantic = catalog.get("rag_index_enabled") is True

    if use_semantic:
        if resolved_catalog is None:
            return {
                "success": False,
                "error_code": "catalog_id_required",
                "error": "semantic search requires catalog_id",
            }
        catalog = await _catalog_by_id(client, resolved_catalog)
        if catalog is None:
            return {
                "success": False,
                "error": f"catalog_id not found or not accessible: {resolved_catalog}",
            }
        if catalog.get("rag_index_enabled") is not True:
            return {
                "success": False,
                "error_code": "rag_index_disabled",
                "error": "RAG index is not enabled for this catalog; use mode=lexical or mode=auto",
                "catalog_id": resolved_catalog,
            }
        try:
            raw = await client.post(
                "office",
                f"/documents/api/v1/catalogs/{quote(resolved_catalog, safe='')}/rag-index/search",
                headers=_ns_headers(),
                json={"query": q, "limit": limit},
            )
        except ServiceClientError as exc:
            return {"success": False, "error": str(exc)}
        body = require_json_object(raw, "documents.semantic_search")
        hits = _as_object_list(body.get("items"), "documents.semantic_search.items")
        items: list[JsonObject] = []
        for hit in hits:
            items.append(
                {
                    "binding_id": hit.get("binding_id"),
                    "file_id": hit.get("file_id"),
                    "title": hit.get("title"),
                    "snippet": hit.get("snippet"),
                    "score": hit.get("score"),
                    "catalog_id": hit.get("catalog_id"),
                }
            )
        return {
            "success": True,
            "mode_used": "semantic",
            "query": q,
            "catalog_id": resolved_catalog,
            "items": items,
        }

    try:
        if resolved_catalog is not None:
            docs = await _list_documents_in_catalog(client, resolved_catalog, query=q)
        else:
            raw = await client.get(
                "office",
                "/documents/api/v1/documents/search",
                headers=_ns_headers(),
                params={"q": q},
            )
            body = require_json_object(raw, "documents.search")
            docs = _as_object_list(body.get("items"), "documents.search.items")
    except ServiceClientError as exc:
        return {"success": False, "error": str(exc)}

    items = [_document_summary(item) for item in docs[:limit]]
    return {
        "success": True,
        "mode_used": "lexical",
        "query": q,
        "catalog_id": resolved_catalog,
        "items": items,
    }


@tool(
    name="documents_read",
    description=(
        "Read content of a Documents library file by binding_id or file_id "
        "(FileReader with page_start/page_end pagination). Not limited to state.files."
    ),
    tags=_DOCUMENTS_CATALOG_TAGS,
    parameters_model=DocumentsReadArgs,
    permission=list(STANDARD_USER_TOOL_GROUPS),
)
async def documents_read(
    binding_id: str | None = None,
    file_id: str | None = None,
    page_start: int = 0,
    page_end: int = -1,
    budget: int = MAX_READ_BUDGET,
    *,
    state: ExecutionState,
) -> JsonObject:
    _ = state
    client = ServiceClient()
    resolved_binding = (
        binding_id.strip() if isinstance(binding_id, str) and binding_id.strip() else None
    )
    resolved_file = file_id.strip() if isinstance(file_id, str) and file_id.strip() else None
    title = "document"
    content_type = "application/octet-stream"
    file_size = 0

    if resolved_binding is not None:
        try:
            config = await _resolve_binding_file(client, resolved_binding)
        except ServiceClientError as exc:
            return {"success": False, "error": str(exc)}
        fid = config.get("file_id")
        if not isinstance(fid, str) or not fid.strip():
            return {"success": False, "error": "editor-config.file_id missing"}
        resolved_file = fid.strip()
        name = config.get("original_name")
        if isinstance(name, str) and name.strip():
            title = name.strip()
        elif isinstance(config.get("title"), str) and str(config["title"]).strip():
            title = str(config["title"]).strip()
        ctype = config.get("content_type")
        if isinstance(ctype, str) and ctype.strip():
            content_type = ctype.strip()

    if resolved_file is None:
        return {"success": False, "error": "file_id could not be resolved"}

    if resolved_binding is None:
        try:
            meta_raw = await client.get(
                "frontend",
                f"/frontend/api/v1/files/{quote(resolved_file, safe='')}",
            )
            meta = require_json_object(meta_raw, "files.metadata")
            oname = meta.get("original_name")
            if isinstance(oname, str) and oname.strip():
                title = oname.strip()
            ctype = meta.get("content_type")
            if isinstance(ctype, str) and ctype.strip():
                content_type = ctype.strip()
            size = meta.get("file_size")
            if isinstance(size, int) and size >= 0:
                file_size = size
        except ServiceClientError as exc:
            return {"success": False, "error": str(exc)}

    file_ref = FileRef(
        file_id=resolved_file,
        original_name=title,
        url=f"/frontend/api/v1/files/download/{resolved_file}",
        content_type=content_type,
        file_size=file_size,
    )
    args = ReadFileArgs(
        names=[title],
        page_start=page_start,
        page_end=page_end,
        compression=CompressionMode.NEVER,
        budget=budget,
    )
    envelope = await read_files_to_envelope([file_ref], args, tool_name="documents_read")
    payload = require_json_object(envelope.model_dump(mode="json"), "documents_read.envelope")
    result: dict[str, JsonValue] = {
        "success": True,
        "binding_id": resolved_binding,
        "file_id": resolved_file,
        "title": title,
        "envelope": payload,
    }
    return result


@tool(
    name="documents_get_link",
    description=(
        "Return a Documents UI link for a binding: editor path or preview_url. "
        "Public share links are not created by this tool."
    ),
    tags=_DOCUMENTS_CATALOG_TAGS,
    parameters_model=DocumentsGetLinkArgs,
    permission=list(STANDARD_USER_TOOL_GROUPS),
)
async def documents_get_link(
    binding_id: str,
    kind: Literal["editor", "preview"] = "editor",
    *,
    state: ExecutionState,
) -> JsonObject:
    _ = state
    namespace = _namespace()
    bid = binding_id.strip()
    editor_path = f"/documents/edit/{quote(bid, safe='')}?namespace={quote(namespace, safe='')}"
    if kind == "editor":
        return {
            "success": True,
            "binding_id": bid,
            "kind": "editor",
            "url": editor_path,
        }
    client = ServiceClient()
    try:
        raw = await client.get(
            "office",
            f"/documents/api/v1/documents/{quote(bid, safe='')}/preview",
            headers=_ns_headers(),
        )
    except ServiceClientError as exc:
        return {
            "success": False,
            "binding_id": bid,
            "kind": "preview",
            "error": str(exc),
            "editor_url": editor_path,
        }
    body = require_json_object(raw, "documents.preview")
    preview_url = body.get("preview_url")
    if not isinstance(preview_url, str) or not preview_url.strip():
        return {
            "success": False,
            "binding_id": bid,
            "kind": "preview",
            "error": "preview_url is empty for this binding",
            "editor_url": editor_path,
        }
    return {
        "success": True,
        "binding_id": bid,
        "kind": "preview",
        "url": preview_url.strip(),
        "editor_url": editor_path,
    }
