"""Platform Documents catalog tools — thin wrappers over DocumentsClient.

Shared tag: documents. Usable on any llm_node via builtin registry;
Lara unlocks the same ids through skill documents-catalog.
"""

from __future__ import annotations

from typing import Literal

from apps.flows.src.tools.decorator import tool
from apps.flows.tools.tool_access import STANDARD_USER_TOOL_GROUPS
from core.clients.documents_client import DocumentsClient
from core.clients.documents_models import (
    DocumentsAccessArgs,
    DocumentsAccessMemberItem,
    DocumentsAddCatalogMemberArgs,
    DocumentsCatalogIdArgs,
    DocumentsCreateCatalogArgs,
    DocumentsFindArgs,
    DocumentsGetLinkArgs,
    DocumentsListCatalogArgs,
    DocumentsPatchAccessArgs,
    DocumentsReadArgs,
    DocumentsUpdateCatalogArgs,
)
from core.files.reader.models import MAX_READ_BUDGET
from core.state import ExecutionState
from core.types import JsonObject

_TAGS = ["documents"]
_PERM = list(STANDARD_USER_TOOL_GROUPS)


@tool(
    name="documents_list_catalog",
    description=(
        "Browse Documents catalog tree. Without catalog_id returns root catalogs "
        "(parent_catalog_id=null). With catalog_id returns child catalogs and documents "
        "in that catalog (non-recursive)."
    ),
    tags=_TAGS,
    parameters_model=DocumentsListCatalogArgs,
    permission=_PERM,
)
async def documents_list_catalog(
    catalog_id: str | None = None,
    *,
    state: ExecutionState,
) -> JsonObject:
    _ = state
    return await DocumentsClient().list_catalog(catalog_id)


@tool(
    name="documents_find",
    description=(
        "Find documents in Documents. mode=auto uses catalog semantic search when "
        "rag_index_enabled, otherwise lexical title search. Explicit semantic fails "
        "with rag_index_disabled when index is off."
    ),
    tags=_TAGS,
    parameters_model=DocumentsFindArgs,
    permission=_PERM,
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
    return await DocumentsClient().find(
        query=query,
        catalog_id=catalog_id,
        mode=mode,
        limit=limit,
    )


@tool(
    name="documents_read",
    description=(
        "Read content of a Documents library / catalog file by file_id "
        "(from UI context, documents_find, or documents_list_catalog; "
        "FileReader with page_start/page_end). Not limited to state.files. "
        "Do not use read_agent_skill_reference for catalog or SPA UI file_id."
    ),
    tags=_TAGS,
    parameters_model=DocumentsReadArgs,
    permission=_PERM,
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
    return await DocumentsClient().read(
        file_id=file_id,
        page_start=page_start,
        page_end=page_end,
        budget=budget,
    )


@tool(
    name="documents_get_link",
    description=(
        "Return a Documents UI link for a document: editor path or preview_url. "
        "Public share links are not created by this tool."
    ),
    tags=_TAGS,
    parameters_model=DocumentsGetLinkArgs,
    permission=_PERM,
)
async def documents_get_link(
    file_id: str,
    kind: Literal["editor", "preview"] = "editor",
    *,
    state: ExecutionState,
) -> JsonObject:
    _ = state
    return await DocumentsClient().get_link(file_id=file_id, kind=kind)


@tool(
    name="documents_create_catalog",
    description=(
        "Creates a Documents catalog (folder). Optional parent_catalog_id for nesting. "
        "Returns catalog_id, title, company_visible."
    ),
    tags=_TAGS,
    parameters_model=DocumentsCreateCatalogArgs,
    permission=_PERM,
)
async def documents_create_catalog(
    title: str,
    company_visible: bool = True,
    parent_catalog_id: str | None = None,
    *,
    state: ExecutionState,
) -> JsonObject:
    _ = state
    return await DocumentsClient().create_catalog(
        title=title,
        company_visible=company_visible,
        parent_catalog_id=parent_catalog_id,
    )


@tool(
    name="documents_update_catalog",
    description=(
        "Updates catalog title and/or company_visible. Owner only. "
        "Provide at least one of title/company_visible."
    ),
    tags=_TAGS,
    parameters_model=DocumentsUpdateCatalogArgs,
    permission=_PERM,
)
async def documents_update_catalog(
    catalog_id: str,
    title: str | None = None,
    company_visible: bool | None = None,
    *,
    state: ExecutionState,
) -> JsonObject:
    _ = state
    return await DocumentsClient().update_catalog(
        catalog_id=catalog_id,
        title=title,
        company_visible=company_visible,
    )


@tool(
    name="documents_list_catalog_members",
    description=(
        "Lists explicit members of a catalog (not the whole company). "
        "Returns items[] with user_id, display_name."
    ),
    tags=_TAGS,
    parameters_model=DocumentsCatalogIdArgs,
    permission=_PERM,
)
async def documents_list_catalog_members(
    catalog_id: str,
    *,
    state: ExecutionState,
) -> JsonObject:
    _ = state
    return await DocumentsClient().list_catalog_members(catalog_id)


@tool(
    name="documents_add_catalog_member",
    description=(
        "Adds a user_id to catalog members. Resolve user via team_resolve_user first. "
        "Returns updated members list."
    ),
    tags=_TAGS,
    parameters_model=DocumentsAddCatalogMemberArgs,
    permission=_PERM,
)
async def documents_add_catalog_member(
    catalog_id: str,
    user_id: str,
    *,
    state: ExecutionState,
) -> JsonObject:
    _ = state
    return await DocumentsClient().add_catalog_member(
        catalog_id=catalog_id,
        user_id=user_id,
    )


@tool(
    name="documents_get_access",
    description=(
        "Reads unified access for a catalog or document: company_visible, members, "
        "link_enabled, public_url. Not the same as documents_get_link (SPA path)."
    ),
    tags=_TAGS,
    parameters_model=DocumentsAccessArgs,
    permission=_PERM,
)
async def documents_get_access(
    resource_kind: Literal["catalog", "document"],
    resource_id: str,
    *,
    state: ExecutionState,
) -> JsonObject:
    _ = state
    return await DocumentsClient().get_access(
        resource_kind=resource_kind,
        resource_id=resource_id,
    )


@tool(
    name="documents_patch_access",
    description=(
        "Patches catalog/document access: company_visible, link_enabled, "
        "link_permission, members (full replace when set). "
        "After enabling link, call documents_rotate_public_link for a fresh public_url."
    ),
    tags=_TAGS,
    parameters_model=DocumentsPatchAccessArgs,
    permission=_PERM,
)
async def documents_patch_access(
    resource_kind: Literal["catalog", "document"],
    resource_id: str,
    company_visible: bool | None = None,
    link_enabled: bool | None = None,
    link_permission: Literal["viewer", "editor"] | None = None,
    members: list[DocumentsAccessMemberItem] | None = None,
    *,
    state: ExecutionState,
) -> JsonObject:
    _ = state
    return await DocumentsClient().patch_access(
        resource_kind=resource_kind,
        resource_id=resource_id,
        company_visible=company_visible,
        link_enabled=link_enabled,
        link_permission=link_permission,
        members=members,
    )


@tool(
    name="documents_rotate_public_link",
    description=(
        "Rotates the public link token for a catalog or document and returns public_url "
        "(/documents/p/…). Enable link via documents_patch_access first. "
        "Not documents_get_link (SPA editor path)."
    ),
    tags=_TAGS,
    parameters_model=DocumentsAccessArgs,
    permission=_PERM,
)
async def documents_rotate_public_link(
    resource_kind: Literal["catalog", "document"],
    resource_id: str,
    *,
    state: ExecutionState,
) -> JsonObject:
    _ = state
    return await DocumentsClient().rotate_public_link(
        resource_kind=resource_kind,
        resource_id=resource_id,
    )


@tool(
    name="documents_catalog_rag_status",
    description=(
        "Returns catalog RAG index status: enabled, totals, rag_namespace_id. "
        "Use before documents_find(mode=semantic) or after enable/rebuild."
    ),
    tags=_TAGS,
    parameters_model=DocumentsCatalogIdArgs,
    permission=_PERM,
)
async def documents_catalog_rag_status(
    catalog_id: str,
    *,
    state: ExecutionState,
) -> JsonObject:
    _ = state
    return await DocumentsClient().catalog_rag_status(catalog_id)


@tool(
    name="documents_catalog_rag_enable",
    description=(
        "Enables semantic RAG index for a catalog (creates office-catalog-{id} namespace "
        "and enqueues initial index). Then use documents_find(mode=semantic)."
    ),
    tags=_TAGS,
    parameters_model=DocumentsCatalogIdArgs,
    permission=_PERM,
)
async def documents_catalog_rag_enable(
    catalog_id: str,
    *,
    state: ExecutionState,
) -> JsonObject:
    _ = state
    return await DocumentsClient().catalog_rag_enable(catalog_id)


@tool(
    name="documents_catalog_rag_disable",
    description=(
        "Disables catalog RAG index and removes vector index for that catalog namespace. "
        "Use only when the user explicitly asks to turn semantic search off."
    ),
    tags=_TAGS,
    parameters_model=DocumentsCatalogIdArgs,
    permission=_PERM,
)
async def documents_catalog_rag_disable(
    catalog_id: str,
    *,
    state: ExecutionState,
) -> JsonObject:
    _ = state
    return await DocumentsClient().catalog_rag_disable(catalog_id)


@tool(
    name="documents_catalog_rag_rebuild",
    description=(
        "Rebuilds the catalog RAG index (TaskIQ job). Catalog must already have "
        "rag_index_enabled. Returns task_id."
    ),
    tags=_TAGS,
    parameters_model=DocumentsCatalogIdArgs,
    permission=_PERM,
)
async def documents_catalog_rag_rebuild(
    catalog_id: str,
    *,
    state: ExecutionState,
) -> JsonObject:
    _ = state
    return await DocumentsClient().catalog_rag_rebuild(catalog_id)
