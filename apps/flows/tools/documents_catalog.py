"""Platform Documents catalog tools — browse/search/read/link for Flows and Lara.

Shared tag pack: documents / office / catalog. Usable on any llm_node via
builtin registry; Lara unlocks the same ids through skill documents-catalog.
"""

from __future__ import annotations

from typing import ClassVar, Literal
from urllib.parse import quote

from pydantic import BaseModel, ConfigDict, Field

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

    file_id: str = Field(..., min_length=1, description="ID файла платформы (Documents).")
    page_start: int = Field(0, ge=0, description="Первая страница (0-based), как у read_file.")
    page_end: int = Field(-1, description="Последняя страница включительно; -1 — до конца.")
    budget: int = Field(MAX_READ_BUDGET, ge=0, description="Лимит символов результата.")


class DocumentsGetLinkArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    file_id: str = Field(..., min_length=1, description="ID документа Documents.")
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
        "Read content of a Documents library file by file_id "
        "(FileReader with page_start/page_end pagination). Not limited to state.files."
    ),
    tags=_DOCUMENTS_CATALOG_TAGS,
    parameters_model=DocumentsReadArgs,
    permission=list(STANDARD_USER_TOOL_GROUPS),
)
async def documents_read(
    file_id: str,
    page_start: int = 0,
    page_end: int = -1,
    budget: int = MAX_READ_BUDGET,
    *,
    state: ExecutionState,
) -> JsonObject:
    _ = state
    client = ServiceClient()
    resolved_file = file_id.strip()
    title = "document"
    content_type = "application/octet-stream"
    file_size = 0

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
        "file_id": resolved_file,
        "title": title,
        "envelope": payload,
    }
    return result


@tool(
    name="documents_get_link",
    description=(
        "Return a Documents UI link for a document: editor path or preview_url. "
        "Public share links are not created by this tool."
    ),
    tags=_DOCUMENTS_CATALOG_TAGS,
    parameters_model=DocumentsGetLinkArgs,
    permission=list(STANDARD_USER_TOOL_GROUPS),
)
async def documents_get_link(
    file_id: str,
    kind: Literal["editor", "preview"] = "editor",
    *,
    state: ExecutionState,
) -> JsonObject:
    _ = state
    namespace = _namespace()
    fid = file_id.strip()
    editor_path = f"/documents/edit/{quote(fid, safe='')}?namespace={quote(namespace, safe='')}"
    if kind == "editor":
        return {
            "success": True,
            "file_id": fid,
            "kind": "editor",
            "url": editor_path,
        }
    client = ServiceClient()
    try:
        raw = await client.get(
            "office",
            f"/documents/api/v1/documents/{quote(fid, safe='')}/preview",
            headers=_ns_headers(),
        )
    except ServiceClientError as exc:
        return {
            "success": False,
            "file_id": fid,
            "kind": "preview",
            "error": str(exc),
            "editor_url": editor_path,
        }
    body = require_json_object(raw, "documents.preview")
    preview_url = body.get("preview_url")
    if not isinstance(preview_url, str) or not preview_url.strip():
        return {
            "success": False,
            "file_id": fid,
            "kind": "preview",
            "error": "preview_url is empty for this document",
            "editor_url": editor_path,
        }
    return {
        "success": True,
        "file_id": fid,
        "kind": "preview",
        "url": preview_url.strip(),
        "editor_url": editor_path,
    }


class DocumentsCreateCatalogArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(..., min_length=1, max_length=500, description="Catalog folder title.")
    is_public: bool = Field(
        True,
        description="company_visible for the whole company in this namespace.",
    )
    parent_catalog_id: str | None = Field(
        None,
        description="Optional parent folder. Only parent owner may create a child.",
    )


class DocumentsUpdateCatalogArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    catalog_id: str = Field(..., min_length=1, description="catalog_id to update.")
    title: str | None = Field(None, min_length=1, max_length=500, description="New title.")
    is_public: bool | None = Field(None, description="Company-visible flag.")


class DocumentsCatalogIdArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    catalog_id: str = Field(..., min_length=1, description="catalog_id.")


class DocumentsAddCatalogMemberArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    catalog_id: str = Field(..., min_length=1, description="catalog_id.")
    user_id: str = Field(
        ...,
        min_length=1,
        description="Member user_id from team_resolve_user / team_list_members.",
    )


class DocumentsAccessArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    resource_kind: Literal["catalog", "document"] = Field(
        ...,
        description="catalog — folder ACL; document — file_id binding ACL.",
    )
    resource_id: str = Field(
        ...,
        min_length=1,
        description="catalog_id when resource_kind=catalog; file_id when document.",
    )


class DocumentsPatchAccessArgs(DocumentsAccessArgs):
    company_visible: bool | None = Field(None, description="Whole-company visibility.")
    link_enabled: bool | None = Field(None, description="Enable/disable public link.")
    link_permission: Literal["view", "edit"] | None = Field(
        None,
        description="Public link permission when link is enabled.",
    )
    member_user_ids: list[str] | None = Field(
        None,
        description="Full replacement member list when provided.",
    )


@tool(
    name="documents_create_catalog",
    description=(
        "Creates a Documents catalog (folder). Optional parent_catalog_id for nesting. "
        "Returns catalog_id, title, is_public."
    ),
    tags=_DOCUMENTS_CATALOG_TAGS,
    parameters_model=DocumentsCreateCatalogArgs,
    permission=list(STANDARD_USER_TOOL_GROUPS),
)
async def documents_create_catalog(
    title: str,
    is_public: bool = True,
    parent_catalog_id: str | None = None,
    *,
    state: ExecutionState,
) -> JsonObject:
    _ = state
    args = DocumentsCreateCatalogArgs(
        title=title,
        is_public=is_public,
        parent_catalog_id=parent_catalog_id,
    )
    body: JsonObject = {"title": args.title, "is_public": args.is_public}
    if args.parent_catalog_id is not None:
        body["parent_catalog_id"] = args.parent_catalog_id
    try:
        raw = await ServiceClient().post(
            "office",
            "/documents/api/v1/catalogs",
            headers=_ns_headers(),
            json=body,
        )
    except ServiceClientError as exc:
        return {"success": False, "error": str(exc)}
    result = require_json_object(raw, "documents.create_catalog")
    return {
        "success": True,
        "catalog_id": result.get("catalog_id"),
        "title": result.get("title"),
        "parent_catalog_id": result.get("parent_catalog_id"),
        "is_public": result.get("is_public"),
        "is_owner": result.get("is_owner"),
    }


@tool(
    name="documents_update_catalog",
    description=(
        "Updates catalog title and/or is_public. Owner only. "
        "Provide at least one of title/is_public."
    ),
    tags=_DOCUMENTS_CATALOG_TAGS,
    parameters_model=DocumentsUpdateCatalogArgs,
    permission=list(STANDARD_USER_TOOL_GROUPS),
)
async def documents_update_catalog(
    catalog_id: str,
    title: str | None = None,
    is_public: bool | None = None,
    *,
    state: ExecutionState,
) -> JsonObject:
    _ = state
    args = DocumentsUpdateCatalogArgs(
        catalog_id=catalog_id,
        title=title,
        is_public=is_public,
    )
    body: JsonObject = {}
    if args.title is not None:
        body["title"] = args.title
    if args.is_public is not None:
        body["is_public"] = args.is_public
    if not body:
        return {"success": False, "error": "Provide title and/or is_public"}
    try:
        raw = await ServiceClient().patch(
            "office",
            f"/documents/api/v1/catalogs/{quote(args.catalog_id, safe='')}",
            headers=_ns_headers(),
            json=body,
        )
    except ServiceClientError as exc:
        return {"success": False, "error": str(exc)}
    result = require_json_object(raw, "documents.update_catalog")
    return {
        "success": True,
        "catalog_id": result.get("catalog_id"),
        "title": result.get("title"),
        "is_public": result.get("is_public"),
        "is_owner": result.get("is_owner"),
    }


@tool(
    name="documents_list_catalog_members",
    description=(
        "Lists explicit members of a catalog (not the whole company). "
        "Returns items[] with user_id, display_name."
    ),
    tags=_DOCUMENTS_CATALOG_TAGS,
    parameters_model=DocumentsCatalogIdArgs,
    permission=list(STANDARD_USER_TOOL_GROUPS),
)
async def documents_list_catalog_members(
    catalog_id: str,
    *,
    state: ExecutionState,
) -> JsonObject:
    _ = state
    args = DocumentsCatalogIdArgs(catalog_id=catalog_id)
    try:
        raw = await ServiceClient().get(
            "office",
            f"/documents/api/v1/catalogs/{quote(args.catalog_id, safe='')}/members",
            headers=_ns_headers(),
        )
    except ServiceClientError as exc:
        return {"success": False, "error": str(exc)}
    body = require_json_object(raw, "documents.catalog_members")
    items = _as_object_list(body.get("members"), "documents.catalog_members.members")
    return {
        "success": True,
        "catalog_id": args.catalog_id,
        "items": [
            {
                "user_id": item.get("user_id"),
                "display_name": item.get("display_name"),
            }
            for item in items
        ],
    }


@tool(
    name="documents_add_catalog_member",
    description=(
        "Adds a user_id to catalog members. Resolve user via team_resolve_user first. "
        "Returns updated members list."
    ),
    tags=_DOCUMENTS_CATALOG_TAGS,
    parameters_model=DocumentsAddCatalogMemberArgs,
    permission=list(STANDARD_USER_TOOL_GROUPS),
)
async def documents_add_catalog_member(
    catalog_id: str,
    user_id: str,
    *,
    state: ExecutionState,
) -> JsonObject:
    _ = state
    args = DocumentsAddCatalogMemberArgs(catalog_id=catalog_id, user_id=user_id)
    try:
        raw = await ServiceClient().post(
            "office",
            f"/documents/api/v1/catalogs/{quote(args.catalog_id, safe='')}/members",
            headers=_ns_headers(),
            json={"user_id": args.user_id},
        )
    except ServiceClientError as exc:
        return {"success": False, "error": str(exc)}
    body = require_json_object(raw, "documents.add_catalog_member")
    items = _as_object_list(body.get("members"), "documents.add_catalog_member.members")
    return {
        "success": True,
        "catalog_id": args.catalog_id,
        "user_id": args.user_id,
        "items": [
            {
                "user_id": item.get("user_id"),
                "display_name": item.get("display_name"),
            }
            for item in items
        ],
    }


def _access_path(resource_kind: Literal["catalog", "document"], resource_id: str) -> str:
    rid = quote(resource_id, safe="")
    if resource_kind == "catalog":
        return f"/documents/api/v1/catalogs/{rid}/access"
    return f"/documents/api/v1/documents/{rid}/access"


@tool(
    name="documents_get_access",
    description=(
        "Reads unified access for a catalog or document: company_visible, members, "
        "link_enabled, public_url. Not the same as documents_get_link (SPA path)."
    ),
    tags=_DOCUMENTS_CATALOG_TAGS,
    parameters_model=DocumentsAccessArgs,
    permission=list(STANDARD_USER_TOOL_GROUPS),
)
async def documents_get_access(
    resource_kind: Literal["catalog", "document"],
    resource_id: str,
    *,
    state: ExecutionState,
) -> JsonObject:
    _ = state
    args = DocumentsAccessArgs(resource_kind=resource_kind, resource_id=resource_id)
    try:
        raw = await ServiceClient().get(
            "office",
            _access_path(args.resource_kind, args.resource_id),
            headers=_ns_headers(),
        )
    except ServiceClientError as exc:
        return {"success": False, "error": str(exc)}
    result = require_json_object(raw, "documents.get_access")
    return {"success": True, **result}


@tool(
    name="documents_patch_access",
    description=(
        "Patches catalog/document access: company_visible, link_enabled, "
        "link_permission, member_user_ids (full replace when set). "
        "After enabling link, call documents_rotate_public_link for a fresh public_url."
    ),
    tags=_DOCUMENTS_CATALOG_TAGS,
    parameters_model=DocumentsPatchAccessArgs,
    permission=list(STANDARD_USER_TOOL_GROUPS),
)
async def documents_patch_access(
    resource_kind: Literal["catalog", "document"],
    resource_id: str,
    company_visible: bool | None = None,
    link_enabled: bool | None = None,
    link_permission: Literal["view", "edit"] | None = None,
    member_user_ids: list[str] | None = None,
    *,
    state: ExecutionState,
) -> JsonObject:
    _ = state
    args = DocumentsPatchAccessArgs(
        resource_kind=resource_kind,
        resource_id=resource_id,
        company_visible=company_visible,
        link_enabled=link_enabled,
        link_permission=link_permission,
        member_user_ids=member_user_ids,
    )
    body: JsonObject = {}
    if args.company_visible is not None:
        body["company_visible"] = args.company_visible
    if args.link_enabled is not None:
        body["link_enabled"] = args.link_enabled
    if args.link_permission is not None:
        body["link_permission"] = args.link_permission
    if args.member_user_ids is not None:
        body["member_user_ids"] = args.member_user_ids
    if not body:
        return {"success": False, "error": "Provide at least one access field to patch"}
    try:
        raw = await ServiceClient().patch(
            "office",
            _access_path(args.resource_kind, args.resource_id),
            headers=_ns_headers(),
            json=body,
        )
    except ServiceClientError as exc:
        return {"success": False, "error": str(exc)}
    result = require_json_object(raw, "documents.patch_access")
    return {"success": True, **result}


@tool(
    name="documents_rotate_public_link",
    description=(
        "Rotates the public link token for a catalog or document and returns public_url "
        "(/documents/p/…). Enable link via documents_patch_access first. "
        "Not documents_get_link (SPA editor path)."
    ),
    tags=_DOCUMENTS_CATALOG_TAGS,
    parameters_model=DocumentsAccessArgs,
    permission=list(STANDARD_USER_TOOL_GROUPS),
)
async def documents_rotate_public_link(
    resource_kind: Literal["catalog", "document"],
    resource_id: str,
    *,
    state: ExecutionState,
) -> JsonObject:
    _ = state
    args = DocumentsAccessArgs(resource_kind=resource_kind, resource_id=resource_id)
    try:
        raw = await ServiceClient().post(
            "office",
            f"{_access_path(args.resource_kind, args.resource_id)}/link/rotate",
            headers=_ns_headers(),
        )
    except ServiceClientError as exc:
        return {"success": False, "error": str(exc)}
    result = require_json_object(raw, "documents.rotate_public_link")
    return {
        "success": True,
        "resource_kind": args.resource_kind,
        "resource_id": args.resource_id,
        "public_url": result.get("public_url"),
    }


@tool(
    name="documents_catalog_rag_status",
    description=(
        "Returns catalog RAG index status: enabled, totals, rag_namespace_id. "
        "Use before documents_find(mode=semantic) or after enable/rebuild."
    ),
    tags=_DOCUMENTS_CATALOG_TAGS,
    parameters_model=DocumentsCatalogIdArgs,
    permission=list(STANDARD_USER_TOOL_GROUPS),
)
async def documents_catalog_rag_status(
    catalog_id: str,
    *,
    state: ExecutionState,
) -> JsonObject:
    _ = state
    args = DocumentsCatalogIdArgs(catalog_id=catalog_id)
    try:
        raw = await ServiceClient().get(
            "office",
            f"/documents/api/v1/catalogs/{quote(args.catalog_id, safe='')}/rag-index/status",
            headers=_ns_headers(),
        )
    except ServiceClientError as exc:
        return {"success": False, "error": str(exc)}
    result = require_json_object(raw, "documents.catalog_rag_status")
    return {"success": True, "catalog_id": args.catalog_id, **result}


@tool(
    name="documents_catalog_rag_enable",
    description=(
        "Enables semantic RAG index for a catalog (creates office-catalog-{id} namespace "
        "and enqueues initial index). Then use documents_find(mode=semantic)."
    ),
    tags=_DOCUMENTS_CATALOG_TAGS,
    parameters_model=DocumentsCatalogIdArgs,
    permission=list(STANDARD_USER_TOOL_GROUPS),
)
async def documents_catalog_rag_enable(
    catalog_id: str,
    *,
    state: ExecutionState,
) -> JsonObject:
    _ = state
    args = DocumentsCatalogIdArgs(catalog_id=catalog_id)
    try:
        raw = await ServiceClient().post(
            "office",
            f"/documents/api/v1/catalogs/{quote(args.catalog_id, safe='')}/rag-index/enable",
            headers=_ns_headers(),
        )
    except ServiceClientError as exc:
        return {"success": False, "error": str(exc)}
    result = require_json_object(raw, "documents.catalog_rag_enable")
    return {"success": True, "catalog_id": args.catalog_id, **result}


@tool(
    name="documents_catalog_rag_disable",
    description=(
        "Disables catalog RAG index and removes vector index for that catalog namespace. "
        "Use only when the user explicitly asks to turn semantic search off."
    ),
    tags=_DOCUMENTS_CATALOG_TAGS,
    parameters_model=DocumentsCatalogIdArgs,
    permission=list(STANDARD_USER_TOOL_GROUPS),
)
async def documents_catalog_rag_disable(
    catalog_id: str,
    *,
    state: ExecutionState,
) -> JsonObject:
    _ = state
    args = DocumentsCatalogIdArgs(catalog_id=catalog_id)
    try:
        raw = await ServiceClient().post(
            "office",
            f"/documents/api/v1/catalogs/{quote(args.catalog_id, safe='')}/rag-index/disable",
            headers=_ns_headers(),
        )
    except ServiceClientError as exc:
        return {"success": False, "error": str(exc)}
    result = require_json_object(raw, "documents.catalog_rag_disable")
    return {"success": True, "catalog_id": args.catalog_id, **result}


@tool(
    name="documents_catalog_rag_rebuild",
    description=(
        "Rebuilds the catalog RAG index (TaskIQ job). Catalog must already have "
        "rag_index_enabled. Returns task_id."
    ),
    tags=_DOCUMENTS_CATALOG_TAGS,
    parameters_model=DocumentsCatalogIdArgs,
    permission=list(STANDARD_USER_TOOL_GROUPS),
)
async def documents_catalog_rag_rebuild(
    catalog_id: str,
    *,
    state: ExecutionState,
) -> JsonObject:
    _ = state
    args = DocumentsCatalogIdArgs(catalog_id=catalog_id)
    try:
        raw = await ServiceClient().post(
            "office",
            f"/documents/api/v1/catalogs/{quote(args.catalog_id, safe='')}/rag-index/rebuild",
            headers=_ns_headers(),
        )
    except ServiceClientError as exc:
        return {"success": False, "error": str(exc)}
    result = require_json_object(raw, "documents.catalog_rag_rebuild")
    return {"success": True, "catalog_id": args.catalog_id, **result}
