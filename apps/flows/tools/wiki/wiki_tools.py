"""Platform Wiki tools — thin wrappers over WikiClient.

Tag: wiki. Namespace from session (`X-Platform-Namespace`). Content for agents
is markdown-first; never invent wiki_page_id.
"""

from __future__ import annotations

from typing import Literal

from apps.flows.src.tools.decorator import tool
from apps.flows.tools.tool_access import STANDARD_USER_TOOL_GROUPS
from core.clients.wiki_client import WikiClient
from core.clients.wiki_models import (
    WikiBacklinksArgs,
    WikiCommentIdArgs,
    WikiCompanyVisibleArgs,
    WikiCreateCommentArgs,
    WikiCreatePageArgs,
    WikiEmptyArgs,
    WikiImportMarkdownArgs,
    WikiListRevisionsArgs,
    WikiMoveNamespaceArgs,
    WikiMovePageArgs,
    WikiPageIdArgs,
    WikiParseMarkdownArgs,
    WikiRemoveMemberArgs,
    WikiResolveCommentArgs,
    WikiRevisionIdArgs,
    WikiRotatePublicLinkArgs,
    WikiSearchArgs,
    WikiSetMemberArgs,
    WikiUpdateMarkdownArgs,
    WikiUpdatePropertiesArgs,
)
from core.state import ExecutionState
from core.types import JsonObject

_TAGS = ["wiki"]
_PERM = list(STANDARD_USER_TOOL_GROUPS)


@tool(
    name="wiki_list_tree",
    description=(
        "Lists the wiki page tree for the active namespace (summaries only). "
        "Use before create/move to find parent_page_id. Returns items[]."
    ),
    tags=_TAGS,
    permission=_PERM,
    parameters_model=WikiEmptyArgs,
    effects=["read"],
)
async def wiki_list_tree(*, state: ExecutionState) -> JsonObject:
    _ = state
    return await WikiClient().list_tree()


@tool(
    name="wiki_list_namespaces",
    description=(
        "Lists company workspace namespaces available in Wiki switcher. "
        "Does not create namespaces. Returns items[{name, is_default}]."
    ),
    tags=_TAGS,
    permission=_PERM,
    parameters_model=WikiEmptyArgs,
    effects=["read"],
)
async def wiki_list_namespaces(*, state: ExecutionState) -> JsonObject:
    _ = state
    return await WikiClient().list_namespaces()


@tool(
    name="wiki_get_page",
    description=(
        "Gets wiki page metadata and permissions (no body). "
        "For content use wiki_get_markdown. Returns page brief + can_edit/can_admin."
    ),
    tags=_TAGS,
    permission=_PERM,
    parameters_model=WikiPageIdArgs,
    effects=["read"],
)
async def wiki_get_page(wiki_page_id: str, *, state: ExecutionState) -> JsonObject:
    _ = state
    return await WikiClient().get_page(wiki_page_id)


@tool(
    name="wiki_get_markdown",
    description=(
        "Reads wiki page body as markdown (no YAML front matter). "
        "Preferred agent read path. Returns wiki_page_id, title, markdown."
    ),
    tags=_TAGS,
    permission=_PERM,
    parameters_model=WikiPageIdArgs,
    effects=["read"],
)
async def wiki_get_markdown(wiki_page_id: str, *, state: ExecutionState) -> JsonObject:
    _ = state
    return await WikiClient().get_markdown(wiki_page_id)


@tool(
    name="wiki_create_page",
    description=(
        "Creates a wiki page with markdown body in the active namespace. "
        "Optional parent_page_id. Returns wiki_page_id and page brief."
    ),
    tags=_TAGS,
    permission=_PERM,
    parameters_model=WikiCreatePageArgs,
    effects=["create"],
    confirmation_floor="preview",
)
async def wiki_create_page(
    title: str = "",
    markdown: str = "",
    parent_page_id: str | None = None,
    icon: str = "",
    *,
    state: ExecutionState,
) -> JsonObject:
    _ = state
    return await WikiClient().create_page(
        title=title,
        markdown=markdown,
        parent_page_id=parent_page_id,
        icon=icon,
    )


@tool(
    name="wiki_update_markdown",
    description=(
        "Replaces wiki page body via markdown (preferred write path). "
        "Optional title; create_revision defaults true."
    ),
    tags=_TAGS,
    permission=_PERM,
    parameters_model=WikiUpdateMarkdownArgs,
    effects=["update"],
    confirmation_floor="preview",
)
async def wiki_update_markdown(
    wiki_page_id: str,
    markdown: str,
    title: str | None = None,
    create_revision: bool = True,
    *,
    state: ExecutionState,
) -> JsonObject:
    _ = state
    return await WikiClient().update_markdown(
        wiki_page_id,
        markdown=markdown,
        title=title,
        create_revision=create_revision,
    )


@tool(
    name="wiki_update_properties",
    description=(
        "Patches wiki page properties: title, icon, cover_url, is_published, "
        "is_template, is_full_width. Does not set company_visible — use wiki_set_company_visible."
    ),
    tags=_TAGS,
    permission=_PERM,
    parameters_model=WikiUpdatePropertiesArgs,
    effects=["update"],
    confirmation_floor="preview",
)
async def wiki_update_properties(
    wiki_page_id: str,
    title: str | None = None,
    icon: str | None = None,
    cover_url: str | None = None,
    is_published: bool | None = None,
    is_template: bool | None = None,
    is_full_width: bool | None = None,
    *,
    state: ExecutionState,
) -> JsonObject:
    _ = state
    return await WikiClient().update_properties(
        wiki_page_id,
        title=title,
        icon=icon,
        cover_url=cover_url,
        is_published=is_published,
        is_template=is_template,
        is_full_width=is_full_width,
    )


@tool(
    name="wiki_move_page",
    description="Moves a wiki page under a new parent (or to root) and optional sibling position.",
    tags=_TAGS,
    permission=_PERM,
    parameters_model=WikiMovePageArgs,
    effects=["update"],
    confirmation_floor="preview",
)
async def wiki_move_page(
    wiki_page_id: str,
    parent_page_id: str | None = None,
    position: int | None = None,
    *,
    state: ExecutionState,
) -> JsonObject:
    _ = state
    return await WikiClient().move_page(
        wiki_page_id,
        parent_page_id=parent_page_id,
        position=position,
    )


@tool(
    name="wiki_move_page_namespace",
    description=(
        "Moves a wiki page subtree into another company workspace namespace. "
        "Requires write on the page; target must be a company workspace."
    ),
    tags=_TAGS,
    permission=_PERM,
    parameters_model=WikiMoveNamespaceArgs,
    effects=["update"],
    confirmation_floor="approval",
)
async def wiki_move_page_namespace(
    wiki_page_id: str,
    target_namespace: str,
    parent_page_id: str | None = None,
    *,
    state: ExecutionState,
) -> JsonObject:
    _ = state
    return await WikiClient().move_to_namespace(
        wiki_page_id,
        target_namespace=target_namespace,
        parent_page_id=parent_page_id,
    )


@tool(
    name="wiki_delete_page",
    description="Soft-deletes a wiki page and its subtree (admin). Recover via wiki_restore_page.",
    tags=_TAGS,
    permission=_PERM,
    parameters_model=WikiPageIdArgs,
    effects=["delete"],
    confirmation_floor="approval",
)
async def wiki_delete_page(wiki_page_id: str, *, state: ExecutionState) -> JsonObject:
    _ = state
    return await WikiClient().delete_page(wiki_page_id)


@tool(
    name="wiki_list_deleted",
    description="Lists soft-deleted wiki pages in the active namespace.",
    tags=_TAGS,
    permission=_PERM,
    parameters_model=WikiEmptyArgs,
)
async def wiki_list_deleted(*, state: ExecutionState) -> JsonObject:
    _ = state
    return await WikiClient().list_deleted()


@tool(
    name="wiki_restore_page",
    description="Restores a soft-deleted wiki page.",
    tags=_TAGS,
    permission=_PERM,
    parameters_model=WikiPageIdArgs,
)
async def wiki_restore_page(wiki_page_id: str, *, state: ExecutionState) -> JsonObject:
    _ = state
    return await WikiClient().restore_page(wiki_page_id)


@tool(
    name="wiki_import_markdown",
    description=(
        "Imports a markdown file: omit wiki_page_id to create, or pass wiki_page_id to replace. "
        "Returns page brief and notices for content that did not map cleanly."
    ),
    tags=_TAGS,
    permission=_PERM,
    parameters_model=WikiImportMarkdownArgs,
)
async def wiki_import_markdown(
    markdown: str,
    wiki_page_id: str | None = None,
    parent_page_id: str | None = None,
    apply_front_matter: bool = True,
    *,
    state: ExecutionState,
) -> JsonObject:
    _ = state
    return await WikiClient().import_markdown(
        markdown,
        wiki_page_id=wiki_page_id,
        parent_page_id=parent_page_id,
        apply_front_matter=apply_front_matter,
    )


@tool(
    name="wiki_parse_markdown",
    description=(
        "Validates markdown without writing a page. Returns notices about dialect gaps; "
        "does not return full ProseMirror document."
    ),
    tags=_TAGS,
    permission=_PERM,
    parameters_model=WikiParseMarkdownArgs,
)
async def wiki_parse_markdown(markdown: str, *, state: ExecutionState) -> JsonObject:
    _ = state
    return await WikiClient().parse_markdown(markdown)


@tool(
    name="wiki_list_revisions",
    description="Lists revision summaries for a wiki page (no bodies).",
    tags=_TAGS,
    permission=_PERM,
    parameters_model=WikiListRevisionsArgs,
)
async def wiki_list_revisions(
    wiki_page_id: str,
    limit: int = 50,
    *,
    state: ExecutionState,
) -> JsonObject:
    _ = state
    return await WikiClient().list_revisions(wiki_page_id, limit=limit)


@tool(
    name="wiki_get_revision",
    description="Gets one revision including text_markdown (no ProseMirror dump).",
    tags=_TAGS,
    permission=_PERM,
    parameters_model=WikiRevisionIdArgs,
)
async def wiki_get_revision(wiki_revision_id: str, *, state: ExecutionState) -> JsonObject:
    _ = state
    return await WikiClient().get_revision(wiki_revision_id)


@tool(
    name="wiki_restore_revision",
    description=(
        "Restores a wiki page to a revision. Current content is saved as a new revision first."
    ),
    tags=_TAGS,
    permission=_PERM,
    parameters_model=WikiRevisionIdArgs,
)
async def wiki_restore_revision(wiki_revision_id: str, *, state: ExecutionState) -> JsonObject:
    _ = state
    return await WikiClient().restore_revision(wiki_revision_id)


@tool(
    name="wiki_list_comments",
    description="Lists comments on a wiki page.",
    tags=_TAGS,
    permission=_PERM,
    parameters_model=WikiPageIdArgs,
)
async def wiki_list_comments(wiki_page_id: str, *, state: ExecutionState) -> JsonObject:
    _ = state
    return await WikiClient().list_comments(wiki_page_id)


@tool(
    name="wiki_create_comment",
    description="Creates a comment on a wiki page (view access is enough).",
    tags=_TAGS,
    permission=_PERM,
    parameters_model=WikiCreateCommentArgs,
)
async def wiki_create_comment(
    wiki_page_id: str,
    body_markdown: str,
    anchor_text: str = "",
    parent_comment_id: str | None = None,
    *,
    state: ExecutionState,
) -> JsonObject:
    _ = state
    return await WikiClient().create_comment(
        wiki_page_id,
        body_markdown=body_markdown,
        anchor_text=anchor_text,
        parent_comment_id=parent_comment_id,
    )


@tool(
    name="wiki_resolve_comment",
    description="Resolves or unresolves a wiki comment.",
    tags=_TAGS,
    permission=_PERM,
    parameters_model=WikiResolveCommentArgs,
)
async def wiki_resolve_comment(
    wiki_comment_id: str,
    resolved: bool = True,
    *,
    state: ExecutionState,
) -> JsonObject:
    _ = state
    return await WikiClient().resolve_comment(wiki_comment_id, resolved=resolved)


@tool(
    name="wiki_delete_comment",
    description="Deletes a wiki comment.",
    tags=_TAGS,
    permission=_PERM,
    parameters_model=WikiCommentIdArgs,
)
async def wiki_delete_comment(wiki_comment_id: str, *, state: ExecutionState) -> JsonObject:
    _ = state
    return await WikiClient().delete_comment(wiki_comment_id)


@tool(
    name="wiki_get_access",
    description=(
        "Gets page access: company_visible, members, inherited_from_page_id, public link flags "
        "(no raw public URL)."
    ),
    tags=_TAGS,
    permission=_PERM,
    parameters_model=WikiPageIdArgs,
)
async def wiki_get_access(wiki_page_id: str, *, state: ExecutionState) -> JsonObject:
    _ = state
    return await WikiClient().get_access(wiki_page_id)


@tool(
    name="wiki_set_company_visible",
    description=(
        "Switches a page between company-wide and members-only access (admin). "
        "Members can only be added while company_visible=false; setting it back to "
        "true clears all explicit members."
    ),
    tags=_TAGS,
    permission=_PERM,
    parameters_model=WikiCompanyVisibleArgs,
)
async def wiki_set_company_visible(
    wiki_page_id: str,
    company_visible: bool,
    *,
    state: ExecutionState,
) -> JsonObject:
    _ = state
    return await WikiClient().set_company_visible(wiki_page_id, company_visible=company_visible)


@tool(
    name="wiki_set_member",
    description=(
        "Adds or updates a page member's relation (admin). Requires company_visible=false "
        "(see wiki_set_company_visible). Resolve user_id via team-directory first."
    ),
    tags=_TAGS,
    permission=_PERM,
    parameters_model=WikiSetMemberArgs,
)
async def wiki_set_member(
    wiki_page_id: str,
    user_id: str,
    relation: Literal["viewer", "editor"] = "viewer",
    *,
    state: ExecutionState,
) -> JsonObject:
    _ = state
    return await WikiClient().set_member(wiki_page_id, user_id=user_id, relation=relation)


@tool(
    name="wiki_remove_member",
    description="Removes a page member (admin). The page stays members-only until you call wiki_set_company_visible.",
    tags=_TAGS,
    permission=_PERM,
    parameters_model=WikiRemoveMemberArgs,
)
async def wiki_remove_member(
    wiki_page_id: str,
    user_id: str,
    *,
    state: ExecutionState,
) -> JsonObject:
    _ = state
    return await WikiClient().remove_member(wiki_page_id, user_id=user_id)


@tool(
    name="wiki_rotate_public_link",
    description=(
        "Enables/rotates or disables the public site link for a page (admin). "
        "Raw url is returned only once when enabled=true. Page must be published for public access."
    ),
    tags=_TAGS,
    permission=_PERM,
    parameters_model=WikiRotatePublicLinkArgs,
)
async def wiki_rotate_public_link(
    wiki_page_id: str,
    enabled: bool,
    permission: Literal["viewer", "editor"] = "viewer",
    *,
    state: ExecutionState,
) -> JsonObject:
    _ = state
    return await WikiClient().rotate_public_link(
        wiki_page_id,
        enabled=enabled,
        permission=permission,
    )


@tool(
    name="wiki_search",
    description=(
        "Searches wiki pages (auto/semantic/lexical). ACL-aware. "
        "Prefer mode=auto. Returns items with snippet and channel."
    ),
    tags=_TAGS,
    permission=_PERM,
    parameters_model=WikiSearchArgs,
)
async def wiki_search(
    query: str,
    mode: Literal["auto", "semantic", "lexical"] = "auto",
    root_page_id: str | None = None,
    published_only: bool = False,
    updated_after_days: int | None = None,
    editor_user_id: str | None = None,
    limit: int = 20,
    *,
    state: ExecutionState,
) -> JsonObject:
    _ = state
    return await WikiClient().search(
        query,
        mode=mode,
        root_page_id=root_page_id,
        published_only=published_only,
        updated_after_days=updated_after_days,
        editor_user_id=editor_user_id,
        limit=limit,
    )


@tool(
    name="wiki_list_backlinks",
    description=(
        "Lists wiki pages that link to a platform entity "
        "(wiki_page/crm_entity/file/work_item/sync_message/url). Cross-namespace, ACL-filtered."
    ),
    tags=_TAGS,
    permission=_PERM,
    parameters_model=WikiBacklinksArgs,
)
async def wiki_list_backlinks(
    target_kind: Literal[
        "wiki_page",
        "crm_entity",
        "file",
        "work_item",
        "sync_message",
        "url",
    ],
    target_id: str,
    limit: int = 50,
    *,
    state: ExecutionState,
) -> JsonObject:
    _ = state
    return await WikiClient().list_backlinks(
        target_kind,
        target_id=target_id,
        limit=limit,
    )
