"""Wiki SDK capabilities: definitions + WikiClient invoke helper."""

from __future__ import annotations

from collections.abc import Awaitable
from typing import TypeAlias

from pydantic import BaseModel, ValidationError

from core.capabilities import CAPABILITY_LANGUAGES, CapabilityDefinition
from core.clients.service_client import ServiceClientError
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
from core.types import JsonObject, JsonValue, require_json_object

WikiArgsModel: TypeAlias = type[BaseModel]

_WIKI_OUTPUT_SCHEMA: JsonObject = {
    "type": "object",
    "description": "Brief JSON from WikiClient (product-level fields, no HTTP envelope).",
}


def _input_schema(model: WikiArgsModel) -> JsonObject:
    return require_json_object(model.model_json_schema(), f"{model.__name__}.json_schema")


def _definition(
    *,
    method: str,
    title: str,
    description: str,
    args_model: WikiArgsModel,
) -> CapabilityDefinition:
    return CapabilityDefinition(
        name=f"wiki.{method}",
        title=title,
        description=description,
        input_schema=_input_schema(args_model),
        output_schema=_WIKI_OUTPUT_SCHEMA,
        languages=list(CAPABILITY_LANGUAGES),
        tags=["wiki"],
        sdk_namespace="wiki",
        sdk_method=method,
    )


WIKI_CAPABILITY_SPECS: tuple[tuple[str, str, str, WikiArgsModel], ...] = (
    (
        "list_tree",
        "List wiki page tree",
        "Lists page summaries for the active namespace. Use before create/move to find parent_page_id.",
        WikiEmptyArgs,
    ),
    (
        "list_namespaces",
        "List wiki namespaces",
        "Lists company workspace namespaces available for wiki.",
        WikiEmptyArgs,
    ),
    (
        "get_page",
        "Get wiki page",
        "Returns page brief plus can_edit / can_admin for wiki_page_id.",
        WikiPageIdArgs,
    ),
    (
        "get_markdown",
        "Get wiki page markdown",
        "Returns page title and markdown body. Preferred read path for agents.",
        WikiPageIdArgs,
    ),
    (
        "create_page",
        "Create wiki page",
        "Creates a wiki page with markdown body in the active namespace.",
        WikiCreatePageArgs,
    ),
    (
        "update_markdown",
        "Update wiki page markdown",
        "Replaces page body via markdown. Optional title; create_revision defaults true.",
        WikiUpdateMarkdownArgs,
    ),
    (
        "update_properties",
        "Update wiki page properties",
        "Patches title, icon, cover_url, is_published, is_template, is_full_width.",
        WikiUpdatePropertiesArgs,
    ),
    (
        "move_page",
        "Move wiki page",
        "Moves a page under a new parent (or to root) with optional sibling position.",
        WikiMovePageArgs,
    ),
    (
        "move_to_namespace",
        "Move wiki page to namespace",
        "Moves a page (and subtree) into another company workspace namespace.",
        WikiMoveNamespaceArgs,
    ),
    (
        "delete_page",
        "Delete wiki page",
        "Soft-deletes a wiki page. Use restore_page to undo.",
        WikiPageIdArgs,
    ),
    (
        "list_deleted",
        "List deleted wiki pages",
        "Lists soft-deleted pages in the active namespace.",
        WikiEmptyArgs,
    ),
    (
        "restore_page",
        "Restore wiki page",
        "Restores a soft-deleted wiki page.",
        WikiPageIdArgs,
    ),
    (
        "import_markdown",
        "Import markdown into wiki",
        "Creates or replaces a page from a full markdown document (optional YAML front matter).",
        WikiImportMarkdownArgs,
    ),
    (
        "parse_markdown",
        "Parse wiki markdown",
        "Validates markdown without writing. Returns notices only.",
        WikiParseMarkdownArgs,
    ),
    (
        "list_revisions",
        "List wiki revisions",
        "Lists revision history for a page.",
        WikiListRevisionsArgs,
    ),
    (
        "get_revision",
        "Get wiki revision",
        "Returns one revision payload by wiki_revision_id.",
        WikiRevisionIdArgs,
    ),
    (
        "restore_revision",
        "Restore wiki revision",
        "Restores page content from a revision.",
        WikiRevisionIdArgs,
    ),
    (
        "list_comments",
        "List wiki comments",
        "Lists comments on a page.",
        WikiPageIdArgs,
    ),
    (
        "create_comment",
        "Create wiki comment",
        "Creates a comment (optional anchor_text / parent reply).",
        WikiCreateCommentArgs,
    ),
    (
        "resolve_comment",
        "Resolve wiki comment",
        "Marks a comment resolved or unresolved.",
        WikiResolveCommentArgs,
    ),
    (
        "delete_comment",
        "Delete wiki comment",
        "Deletes a comment by wiki_comment_id.",
        WikiCommentIdArgs,
    ),
    (
        "get_access",
        "Get wiki page access",
        "Returns company_visible, members, and public-link flags for a page.",
        WikiPageIdArgs,
    ),
    (
        "set_company_visible",
        "Set wiki page company visibility",
        "Switches a page between company-wide and members-only access.",
        WikiCompanyVisibleArgs,
    ),
    (
        "set_member",
        "Set wiki page member",
        "Grants a viewer/editor relation to a user on a page (requires company_visible=false).",
        WikiSetMemberArgs,
    ),
    (
        "remove_member",
        "Remove wiki page member",
        "Removes a member grant from a page.",
        WikiRemoveMemberArgs,
    ),
    (
        "rotate_public_link",
        "Rotate wiki public link",
        "Enables/rotates or disables the public link. Raw URL returned once when enabled.",
        WikiRotatePublicLinkArgs,
    ),
    (
        "search",
        "Search wiki pages",
        "Lexical/semantic/auto search in the active namespace.",
        WikiSearchArgs,
    ),
    (
        "list_backlinks",
        "List wiki backlinks",
        "Lists pages linking to a target entity (wiki_page, crm_entity, file, …).",
        WikiBacklinksArgs,
    ),
)


def wiki_capability_definitions() -> dict[str, CapabilityDefinition]:
    return {
        f"wiki.{method}": _definition(
            method=method,
            title=title,
            description=description,
            args_model=args_model,
        )
        for method, title, description, args_model in WIKI_CAPABILITY_SPECS
    }


def wiki_args_model_for(method: str) -> WikiArgsModel:
    for spec_method, _title, _description, args_model in WIKI_CAPABILITY_SPECS:
        if spec_method == method:
            return args_model
    raise ValueError(f"Unknown wiki capability method: {method}")


def _wiki_method_call(method: str, args: BaseModel) -> Awaitable[JsonObject]:
    client = WikiClient()
    if isinstance(args, WikiEmptyArgs):
        if method == "list_tree":
            return client.list_tree()
        if method == "list_namespaces":
            return client.list_namespaces()
        if method == "list_deleted":
            return client.list_deleted()
        raise ValueError(f"Unsupported wiki empty-args method: {method}")
    if method == "get_page" and isinstance(args, WikiPageIdArgs):
        return client.get_page(args)
    if method == "get_markdown" and isinstance(args, WikiPageIdArgs):
        return client.get_markdown(args)
    if method == "create_page" and isinstance(args, WikiCreatePageArgs):
        return client.create_page(args)
    if method == "update_markdown" and isinstance(args, WikiUpdateMarkdownArgs):
        return client.update_markdown(args)
    if method == "update_properties" and isinstance(args, WikiUpdatePropertiesArgs):
        return client.update_properties(args)
    if method == "move_page" and isinstance(args, WikiMovePageArgs):
        return client.move_page(args)
    if method == "move_to_namespace" and isinstance(args, WikiMoveNamespaceArgs):
        return client.move_to_namespace(args)
    if method == "delete_page" and isinstance(args, WikiPageIdArgs):
        return client.delete_page(args)
    if method == "restore_page" and isinstance(args, WikiPageIdArgs):
        return client.restore_page(args)
    if method == "import_markdown" and isinstance(args, WikiImportMarkdownArgs):
        return client.import_markdown(args)
    if method == "parse_markdown" and isinstance(args, WikiParseMarkdownArgs):
        return client.parse_markdown(args)
    if method == "list_revisions" and isinstance(args, WikiListRevisionsArgs):
        return client.list_revisions(args)
    if method == "get_revision" and isinstance(args, WikiRevisionIdArgs):
        return client.get_revision(args)
    if method == "restore_revision" and isinstance(args, WikiRevisionIdArgs):
        return client.restore_revision(args)
    if method == "list_comments" and isinstance(args, WikiPageIdArgs):
        return client.list_comments(args)
    if method == "create_comment" and isinstance(args, WikiCreateCommentArgs):
        return client.create_comment(args)
    if method == "resolve_comment" and isinstance(args, WikiResolveCommentArgs):
        return client.resolve_comment(args)
    if method == "delete_comment" and isinstance(args, WikiCommentIdArgs):
        return client.delete_comment(args)
    if method == "get_access" and isinstance(args, WikiPageIdArgs):
        return client.get_access(args)
    if method == "set_company_visible" and isinstance(args, WikiCompanyVisibleArgs):
        return client.set_company_visible(args)
    if method == "set_member" and isinstance(args, WikiSetMemberArgs):
        return client.set_member(args)
    if method == "remove_member" and isinstance(args, WikiRemoveMemberArgs):
        return client.remove_member(args)
    if method == "rotate_public_link" and isinstance(args, WikiRotatePublicLinkArgs):
        return client.rotate_public_link(args)
    if method == "search" and isinstance(args, WikiSearchArgs):
        return client.search(args)
    if method == "list_backlinks" and isinstance(args, WikiBacklinksArgs):
        return client.list_backlinks(args)
    raise ValueError(f"Unsupported wiki capability invoke: {method}")


async def invoke_wiki_client(method: str, kwargs: JsonObject) -> JsonValue:
    """Parse kwargs with the method's model and call WikiClient (Context must be active)."""
    args_model = wiki_args_model_for(method)
    try:
        args = args_model.model_validate(kwargs)
    except ValidationError as exc:
        raise ValueError(str(exc)) from exc
    try:
        return await _wiki_method_call(method, args)
    except ServiceClientError as exc:
        raise ValueError(str(exc)) from exc
