"""HTTP client for Wiki API on top of ServiceClient."""

from __future__ import annotations

from typing import Literal
from urllib.parse import quote

from core.clients.service_client import NAMESPACE_HEADER, ServiceClient
from core.clients.wiki_models import (
    WikiBacklinksArgs,
    WikiCommentIdArgs,
    WikiCreateCommentArgs,
    WikiCreatePageArgs,
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
from core.context import resolve_namespace_or_raise
from core.types import JsonObject, JsonValue, require_json_array, require_json_object

_API = "/wiki/api/v1"


class WikiClient:
    """REST client for wiki service; namespace from context via X-Platform-Namespace."""

    def __init__(self, service_client: ServiceClient | None = None) -> None:
        self._http: ServiceClient = (
            service_client if service_client is not None else ServiceClient()
        )

    def _ns_headers(self) -> dict[str, str]:
        return {NAMESPACE_HEADER: resolve_namespace_or_raise()}

    @staticmethod
    def _as_objects(value: object, label: str) -> list[JsonObject]:
        items = require_json_array(value, label)
        return [require_json_object(item, f"{label}[{index}]") for index, item in enumerate(items)]

    @staticmethod
    def _page_brief(page: JsonObject) -> JsonObject:
        return {
            "wiki_page_id": page.get("wiki_page_id"),
            "namespace": page.get("namespace"),
            "parent_page_id": page.get("parent_page_id"),
            "root_page_id": page.get("root_page_id"),
            "depth": page.get("depth"),
            "position": page.get("position"),
            "title": page.get("title"),
            "icon": page.get("icon"),
            "cover_url": page.get("cover_url"),
            "visibility": page.get("visibility"),
            "is_published": page.get("is_published"),
            "is_template": page.get("is_template"),
            "is_full_width": page.get("is_full_width"),
            "updated_at": page.get("updated_at"),
            "last_edited_by_user_id": page.get("last_edited_by_user_id"),
        }

    @staticmethod
    def _summary_brief(item: JsonObject) -> JsonObject:
        return {
            "wiki_page_id": item.get("wiki_page_id"),
            "parent_page_id": item.get("parent_page_id"),
            "title": item.get("title"),
            "icon": item.get("icon"),
            "depth": item.get("depth"),
            "position": item.get("position"),
            "visibility": item.get("visibility"),
            "is_published": item.get("is_published"),
            "has_children": item.get("has_children"),
            "updated_at": item.get("updated_at"),
        }

    @staticmethod
    def _unwrap_page_response(raw: object) -> tuple[JsonObject, bool, bool]:
        body = require_json_object(raw, "wiki.page_response")
        page = require_json_object(body.get("page"), "wiki.page_response.page")
        return page, body.get("can_edit") is True, body.get("can_administer") is True

    @staticmethod
    def _access_brief(body: JsonObject) -> JsonObject:
        members_raw = body.get("members")
        members: list[JsonObject] = []
        if isinstance(members_raw, list):
            for index, item in enumerate(members_raw):
                member = require_json_object(item, f"wiki.access.members[{index}]")
                members.append(
                    {
                        "user_id": member.get("user_id"),
                        "permission": member.get("permission"),
                    }
                )
        return {
            "wiki_page_id": body.get("wiki_page_id"),
            "visibility": body.get("visibility"),
            "inherited_from_page_id": body.get("inherited_from_page_id"),
            "members": members,
            "link_enabled": body.get("link_enabled"),
            "link_permission": body.get("link_permission"),
        }

    @staticmethod
    def _page_id(wiki_page_id: str | WikiPageIdArgs) -> str:
        if isinstance(wiki_page_id, WikiPageIdArgs):
            return wiki_page_id.wiki_page_id.strip()
        return wiki_page_id.strip()

    @staticmethod
    def _revision_id(wiki_revision_id: str | WikiRevisionIdArgs) -> str:
        if isinstance(wiki_revision_id, WikiRevisionIdArgs):
            return wiki_revision_id.wiki_revision_id.strip()
        return wiki_revision_id.strip()

    @staticmethod
    def _comment_id(wiki_comment_id: str | WikiCommentIdArgs) -> str:
        if isinstance(wiki_comment_id, WikiCommentIdArgs):
            return wiki_comment_id.wiki_comment_id.strip()
        return wiki_comment_id.strip()

    async def list_tree(self) -> JsonObject:
        raw = await self._http.get("wiki", f"{_API}/pages", headers=self._ns_headers())
        body = require_json_object(raw, "wiki.list_tree")
        items = [
            self._summary_brief(item)
            for item in self._as_objects(body.get("items"), "wiki.list_tree.items")
        ]
        return {
            "namespace": body.get("namespace"),
            "count": len(items),
            "items": items,
        }

    async def list_namespaces(self) -> JsonObject:
        raw = await self._http.get("wiki", f"{_API}/namespaces", headers=self._ns_headers())
        body = require_json_object(raw, "wiki.namespaces")
        items = self._as_objects(body.get("items"), "wiki.namespaces.items")
        return {"count": len(items), "items": items, "total": body.get("total")}

    async def get_page(self, wiki_page_id: str | WikiPageIdArgs) -> JsonObject:
        page_id = self._page_id(wiki_page_id)
        raw = await self._http.get(
            "wiki",
            f"{_API}/pages/{quote(page_id, safe='')}",
            headers=self._ns_headers(),
        )
        page, can_edit, can_administer = self._unwrap_page_response(raw)
        return {
            "page": self._page_brief(page),
            "can_edit": can_edit,
            "can_administer": can_administer,
        }

    async def get_markdown(self, wiki_page_id: str | WikiPageIdArgs) -> JsonObject:
        page_id = self._page_id(wiki_page_id)
        raw = await self._http.get(
            "wiki",
            f"{_API}/pages/{quote(page_id, safe='')}/markdown",
            headers=self._ns_headers(),
        )
        body = require_json_object(raw, "wiki.markdown")
        return {
            "wiki_page_id": body.get("wiki_page_id"),
            "title": body.get("title"),
            "markdown": body.get("markdown"),
        }

    async def create_page(
        self,
        title: str | WikiCreatePageArgs = "",
        markdown: str = "",
        parent_page_id: str | None = None,
        icon: str = "",
    ) -> JsonObject:
        if isinstance(title, WikiCreatePageArgs):
            args = title
        else:
            args = WikiCreatePageArgs(
                title=title,
                markdown=markdown,
                parent_page_id=parent_page_id,
                icon=icon,
            )
        payload: JsonObject = {
            "title": args.title,
            "icon": args.icon,
            "markdown": args.markdown,
        }
        if args.parent_page_id is not None and args.parent_page_id.strip() != "":
            payload["parent_page_id"] = args.parent_page_id.strip()
        raw = await self._http.post(
            "wiki",
            f"{_API}/pages",
            headers=self._ns_headers(),
            json=payload,
        )
        page, can_edit, can_administer = self._unwrap_page_response(raw)
        return {
            "wiki_page_id": page.get("wiki_page_id"),
            "page": self._page_brief(page),
            "can_edit": can_edit,
            "can_administer": can_administer,
        }

    async def update_markdown(
        self,
        wiki_page_id: str | WikiUpdateMarkdownArgs,
        markdown: str = "",
        title: str | None = None,
        create_revision: bool = True,
    ) -> JsonObject:
        if isinstance(wiki_page_id, WikiUpdateMarkdownArgs):
            args = wiki_page_id
        else:
            args = WikiUpdateMarkdownArgs(
                wiki_page_id=wiki_page_id,
                markdown=markdown,
                title=title,
                create_revision=create_revision,
            )
        page_id = args.wiki_page_id.strip()
        payload: JsonObject = {
            "markdown": args.markdown,
            "create_revision": args.create_revision,
        }
        if args.title is not None:
            payload["title"] = args.title
        raw = await self._http.put(
            "wiki",
            f"{_API}/pages/{quote(page_id, safe='')}/content",
            headers=self._ns_headers(),
            json=payload,
        )
        page, can_edit, can_administer = self._unwrap_page_response(raw)
        return {
            "wiki_page_id": page.get("wiki_page_id"),
            "page": self._page_brief(page),
            "can_edit": can_edit,
            "can_administer": can_administer,
        }

    async def update_properties(
        self,
        wiki_page_id: str | WikiUpdatePropertiesArgs,
        title: str | None = None,
        icon: str | None = None,
        cover_url: str | None = None,
        is_published: bool | None = None,
        is_template: bool | None = None,
        is_full_width: bool | None = None,
    ) -> JsonObject:
        if isinstance(wiki_page_id, WikiUpdatePropertiesArgs):
            args = wiki_page_id
        else:
            args = WikiUpdatePropertiesArgs(
                wiki_page_id=wiki_page_id,
                title=title,
                icon=icon,
                cover_url=cover_url,
                is_published=is_published,
                is_template=is_template,
                is_full_width=is_full_width,
            )
        page_id = args.wiki_page_id.strip()
        payload: JsonObject = {}
        if args.title is not None:
            payload["title"] = args.title
        if args.icon is not None:
            payload["icon"] = args.icon
        if args.cover_url is not None:
            payload["cover_url"] = args.cover_url
        if args.is_published is not None:
            payload["is_published"] = args.is_published
        if args.is_template is not None:
            payload["is_template"] = args.is_template
        if args.is_full_width is not None:
            payload["is_full_width"] = args.is_full_width
        if not payload:
            raise ValueError("Provide at least one property to patch")
        raw = await self._http.patch(
            "wiki",
            f"{_API}/pages/{quote(page_id, safe='')}",
            headers=self._ns_headers(),
            json=payload,
        )
        page, can_edit, can_administer = self._unwrap_page_response(raw)
        return {
            "wiki_page_id": page.get("wiki_page_id"),
            "page": self._page_brief(page),
            "can_edit": can_edit,
            "can_administer": can_administer,
        }

    async def move_page(
        self,
        wiki_page_id: str | WikiMovePageArgs,
        parent_page_id: str | None = None,
        position: int | None = None,
    ) -> JsonObject:
        if isinstance(wiki_page_id, WikiMovePageArgs):
            args = wiki_page_id
        else:
            args = WikiMovePageArgs(
                wiki_page_id=wiki_page_id,
                parent_page_id=parent_page_id,
                position=position,
            )
        page_id = args.wiki_page_id.strip()
        payload: JsonObject = {"parent_page_id": args.parent_page_id}
        if args.position is not None:
            payload["position"] = args.position
        raw = await self._http.post(
            "wiki",
            f"{_API}/pages/{quote(page_id, safe='')}/move",
            headers=self._ns_headers(),
            json=payload,
        )
        page, can_edit, can_administer = self._unwrap_page_response(raw)
        return {
            "wiki_page_id": page.get("wiki_page_id"),
            "page": self._page_brief(page),
            "can_edit": can_edit,
            "can_administer": can_administer,
        }

    async def move_to_namespace(
        self,
        wiki_page_id: str | WikiMoveNamespaceArgs,
        target_namespace: str = "",
        parent_page_id: str | None = None,
    ) -> JsonObject:
        if isinstance(wiki_page_id, WikiMoveNamespaceArgs):
            args = wiki_page_id
        else:
            args = WikiMoveNamespaceArgs(
                wiki_page_id=wiki_page_id,
                target_namespace=target_namespace,
                parent_page_id=parent_page_id,
            )
        page_id = args.wiki_page_id.strip()
        payload: JsonObject = {"target_namespace": args.target_namespace.strip()}
        if args.parent_page_id is not None:
            payload["parent_page_id"] = args.parent_page_id
        raw = await self._http.post(
            "wiki",
            f"{_API}/pages/{quote(page_id, safe='')}/move-namespace",
            headers=self._ns_headers(),
            json=payload,
        )
        page, can_edit, can_administer = self._unwrap_page_response(raw)
        return {
            "wiki_page_id": page.get("wiki_page_id"),
            "page": self._page_brief(page),
            "can_edit": can_edit,
            "can_administer": can_administer,
        }

    async def delete_page(self, wiki_page_id: str | WikiPageIdArgs) -> JsonObject:
        page_id = self._page_id(wiki_page_id)
        _ = await self._http.delete(
            "wiki",
            f"{_API}/pages/{quote(page_id, safe='')}",
            headers=self._ns_headers(),
        )
        return {"wiki_page_id": page_id, "deleted": True}

    async def list_deleted(self) -> JsonObject:
        raw = await self._http.get("wiki", f"{_API}/pages/deleted", headers=self._ns_headers())
        body = require_json_object(raw, "wiki.list_deleted")
        items = [
            self._summary_brief(item)
            for item in self._as_objects(body.get("items"), "wiki.list_deleted.items")
        ]
        return {
            "namespace": body.get("namespace"),
            "count": len(items),
            "items": items,
        }

    async def restore_page(self, wiki_page_id: str | WikiPageIdArgs) -> JsonObject:
        page_id = self._page_id(wiki_page_id)
        raw = await self._http.post(
            "wiki",
            f"{_API}/pages/{quote(page_id, safe='')}/restore",
            headers=self._ns_headers(),
        )
        page, can_edit, can_administer = self._unwrap_page_response(raw)
        return {
            "wiki_page_id": page.get("wiki_page_id"),
            "page": self._page_brief(page),
            "can_edit": can_edit,
            "can_administer": can_administer,
        }

    async def import_markdown(
        self,
        markdown: str | WikiImportMarkdownArgs,
        wiki_page_id: str | None = None,
        parent_page_id: str | None = None,
        apply_front_matter: bool = True,
    ) -> JsonObject:
        if isinstance(markdown, WikiImportMarkdownArgs):
            args = markdown
        else:
            args = WikiImportMarkdownArgs(
                markdown=markdown,
                wiki_page_id=wiki_page_id,
                parent_page_id=parent_page_id,
                apply_front_matter=apply_front_matter,
            )
        payload: JsonObject = {
            "markdown": args.markdown,
            "apply_front_matter": args.apply_front_matter,
        }
        if args.parent_page_id is not None and args.parent_page_id.strip() != "":
            payload["parent_page_id"] = args.parent_page_id.strip()
        page_id = (
            args.wiki_page_id.strip()
            if isinstance(args.wiki_page_id, str) and args.wiki_page_id.strip()
            else None
        )
        path = (
            f"{_API}/pages/{quote(page_id, safe='')}/import/markdown"
            if page_id is not None
            else f"{_API}/pages/import/markdown"
        )
        raw = await self._http.post("wiki", path, headers=self._ns_headers(), json=payload)
        body = require_json_object(raw, "wiki.import_markdown")
        page = require_json_object(body.get("page"), "wiki.import_markdown.page")
        notices = body.get("notices")
        notices_list: list[JsonValue] = notices if isinstance(notices, list) else []
        return {
            "wiki_page_id": page.get("wiki_page_id"),
            "page": self._page_brief(page),
            "notices": notices_list,
        }

    async def parse_markdown(self, markdown: str | WikiParseMarkdownArgs) -> JsonObject:
        if isinstance(markdown, WikiParseMarkdownArgs):
            args = markdown
        else:
            args = WikiParseMarkdownArgs(markdown=markdown)
        raw = await self._http.post(
            "wiki",
            f"{_API}/pages/markdown/parse",
            headers=self._ns_headers(),
            json={"markdown": args.markdown},
        )
        body = require_json_object(raw, "wiki.parse_markdown")
        notices = body.get("notices")
        notices_list: list[JsonValue] = notices if isinstance(notices, list) else []
        return {
            "notices": notices_list,
            "notice_count": len(notices_list),
        }

    async def list_revisions(
        self,
        wiki_page_id: str | WikiListRevisionsArgs,
        limit: int = 50,
    ) -> JsonObject:
        if isinstance(wiki_page_id, WikiListRevisionsArgs):
            args = wiki_page_id
        else:
            args = WikiListRevisionsArgs(wiki_page_id=wiki_page_id, limit=limit)
        page_id = args.wiki_page_id.strip()
        raw = await self._http.get(
            "wiki",
            f"{_API}/pages/{quote(page_id, safe='')}/revisions",
            headers=self._ns_headers(),
            params={"limit": str(args.limit)},
        )
        items = self._as_objects(raw, "wiki.revisions") if isinstance(raw, list) else []
        briefs: list[JsonObject] = [
            {
                "wiki_revision_id": item.get("wiki_revision_id"),
                "wiki_page_id": item.get("wiki_page_id"),
                "title": item.get("title"),
                "author_user_id": item.get("author_user_id"),
                "created_at": item.get("created_at"),
            }
            for item in items
        ]
        return {"wiki_page_id": page_id, "count": len(briefs), "items": briefs}

    async def get_revision(self, wiki_revision_id: str | WikiRevisionIdArgs) -> JsonObject:
        revision_id = self._revision_id(wiki_revision_id)
        raw = await self._http.get(
            "wiki",
            f"{_API}/revisions/{quote(revision_id, safe='')}",
            headers=self._ns_headers(),
        )
        body = require_json_object(raw, "wiki.revision")
        return {
            "wiki_revision_id": body.get("wiki_revision_id"),
            "wiki_page_id": body.get("wiki_page_id"),
            "title": body.get("title"),
            "text_markdown": body.get("text_markdown"),
            "author_user_id": body.get("author_user_id"),
            "created_at": body.get("created_at"),
        }

    async def restore_revision(self, wiki_revision_id: str | WikiRevisionIdArgs) -> JsonObject:
        revision_id = self._revision_id(wiki_revision_id)
        raw = await self._http.post(
            "wiki",
            f"{_API}/revisions/{quote(revision_id, safe='')}/restore",
            headers=self._ns_headers(),
        )
        page, can_edit, can_administer = self._unwrap_page_response(raw)
        return {
            "wiki_revision_id": revision_id,
            "wiki_page_id": page.get("wiki_page_id"),
            "page": self._page_brief(page),
            "can_edit": can_edit,
            "can_administer": can_administer,
        }

    async def list_comments(self, wiki_page_id: str | WikiPageIdArgs) -> JsonObject:
        page_id = self._page_id(wiki_page_id)
        raw = await self._http.get(
            "wiki",
            f"{_API}/pages/{quote(page_id, safe='')}/comments",
            headers=self._ns_headers(),
        )
        body = require_json_object(raw, "wiki.comments")
        items = self._as_objects(body.get("items"), "wiki.comments.items")
        briefs: list[JsonObject] = [
            {
                "wiki_comment_id": item.get("wiki_comment_id"),
                "parent_comment_id": item.get("parent_comment_id"),
                "author_user_id": item.get("author_user_id"),
                "body_markdown": item.get("body_markdown"),
                "anchor_text": item.get("anchor_text"),
                "resolved_at": item.get("resolved_at"),
                "created_at": item.get("created_at"),
            }
            for item in items
        ]
        return {"wiki_page_id": page_id, "count": len(briefs), "items": briefs}

    async def create_comment(
        self,
        wiki_page_id: str | WikiCreateCommentArgs,
        body_markdown: str = "",
        anchor_text: str = "",
        parent_comment_id: str | None = None,
    ) -> JsonObject:
        if isinstance(wiki_page_id, WikiCreateCommentArgs):
            args = wiki_page_id
        else:
            args = WikiCreateCommentArgs(
                wiki_page_id=wiki_page_id,
                body_markdown=body_markdown,
                anchor_text=anchor_text,
                parent_comment_id=parent_comment_id,
            )
        page_id = args.wiki_page_id.strip()
        payload: JsonObject = {
            "body_markdown": args.body_markdown,
            "anchor_text": args.anchor_text,
        }
        if args.parent_comment_id is not None and args.parent_comment_id.strip() != "":
            payload["parent_comment_id"] = args.parent_comment_id.strip()
        raw = await self._http.post(
            "wiki",
            f"{_API}/pages/{quote(page_id, safe='')}/comments",
            headers=self._ns_headers(),
            json=payload,
        )
        body = require_json_object(raw, "wiki.create_comment")
        return {
            "wiki_comment_id": body.get("wiki_comment_id"),
            "wiki_page_id": body.get("wiki_page_id"),
            "body_markdown": body.get("body_markdown"),
        }

    async def resolve_comment(
        self,
        wiki_comment_id: str | WikiResolveCommentArgs,
        resolved: bool = True,
    ) -> JsonObject:
        if isinstance(wiki_comment_id, WikiResolveCommentArgs):
            args = wiki_comment_id
        else:
            args = WikiResolveCommentArgs(
                wiki_comment_id=wiki_comment_id,
                resolved=resolved,
            )
        comment_id = args.wiki_comment_id.strip()
        raw = await self._http.post(
            "wiki",
            f"{_API}/comments/{quote(comment_id, safe='')}/resolve",
            headers=self._ns_headers(),
            json={"resolved": args.resolved},
        )
        body = require_json_object(raw, "wiki.resolve_comment")
        return {
            "wiki_comment_id": body.get("wiki_comment_id"),
            "resolved_at": body.get("resolved_at"),
            "resolved_by_user_id": body.get("resolved_by_user_id"),
        }

    async def delete_comment(self, wiki_comment_id: str | WikiCommentIdArgs) -> JsonObject:
        comment_id = self._comment_id(wiki_comment_id)
        _ = await self._http.delete(
            "wiki",
            f"{_API}/comments/{quote(comment_id, safe='')}",
            headers=self._ns_headers(),
        )
        return {"wiki_comment_id": comment_id, "deleted": True}

    async def get_access(self, wiki_page_id: str | WikiPageIdArgs) -> JsonObject:
        page_id = self._page_id(wiki_page_id)
        raw = await self._http.get(
            "wiki",
            f"{_API}/pages/{quote(page_id, safe='')}/access",
            headers=self._ns_headers(),
        )
        body = require_json_object(raw, "wiki.access")
        return self._access_brief(body)

    async def set_member(
        self,
        wiki_page_id: str | WikiSetMemberArgs,
        user_id: str = "",
        permission: Literal["read", "write", "admin"] = "read",
    ) -> JsonObject:
        if isinstance(wiki_page_id, WikiSetMemberArgs):
            args = wiki_page_id
        else:
            args = WikiSetMemberArgs(
                wiki_page_id=wiki_page_id,
                user_id=user_id,
                permission=permission,
            )
        page_id = args.wiki_page_id.strip()
        raw = await self._http.post(
            "wiki",
            f"{_API}/pages/{quote(page_id, safe='')}/access/members",
            headers=self._ns_headers(),
            json={"user_id": args.user_id.strip(), "permission": args.permission},
        )
        body = require_json_object(raw, "wiki.set_member")
        return self._access_brief(body)

    async def remove_member(
        self,
        wiki_page_id: str | WikiRemoveMemberArgs,
        user_id: str = "",
    ) -> JsonObject:
        if isinstance(wiki_page_id, WikiRemoveMemberArgs):
            args = wiki_page_id
        else:
            args = WikiRemoveMemberArgs(wiki_page_id=wiki_page_id, user_id=user_id)
        page_id = args.wiki_page_id.strip()
        member_id = args.user_id.strip()
        raw = await self._http.delete(
            "wiki",
            f"{_API}/pages/{quote(page_id, safe='')}/access/members/{quote(member_id, safe='')}",
            headers=self._ns_headers(),
        )
        body = require_json_object(raw, "wiki.remove_member")
        return self._access_brief(body)

    async def rotate_public_link(
        self,
        wiki_page_id: str | WikiRotatePublicLinkArgs,
        enabled: bool = False,
        permission: Literal["view", "comment"] = "view",
    ) -> JsonObject:
        if isinstance(wiki_page_id, WikiRotatePublicLinkArgs):
            args = wiki_page_id
        else:
            args = WikiRotatePublicLinkArgs(
                wiki_page_id=wiki_page_id,
                enabled=enabled,
                permission=permission,
            )
        page_id = args.wiki_page_id.strip()
        raw = await self._http.post(
            "wiki",
            f"{_API}/pages/{quote(page_id, safe='')}/access/link",
            headers=self._ns_headers(),
            json={"enabled": args.enabled, "permission": args.permission},
        )
        body = require_json_object(raw, "wiki.rotate_public_link")
        return {
            "wiki_page_id": page_id,
            "enabled": body.get("enabled"),
            "permission": body.get("permission"),
            "url": body.get("url"),
        }

    async def search(
        self,
        query: str | WikiSearchArgs,
        mode: Literal["auto", "semantic", "lexical"] = "auto",
        root_page_id: str | None = None,
        published_only: bool = False,
        updated_after_days: int | None = None,
        editor_user_id: str | None = None,
        limit: int = 20,
    ) -> JsonObject:
        if isinstance(query, WikiSearchArgs):
            args = query
        else:
            args = WikiSearchArgs(
                query=query,
                mode=mode,
                root_page_id=root_page_id,
                published_only=published_only,
                updated_after_days=updated_after_days,
                editor_user_id=editor_user_id,
                limit=limit,
            )
        payload: JsonObject = {
            "query": args.query,
            "mode": args.mode,
            "published_only": args.published_only,
            "limit": args.limit,
        }
        if args.root_page_id is not None and args.root_page_id.strip() != "":
            payload["root_page_id"] = args.root_page_id.strip()
        if args.updated_after_days is not None:
            payload["updated_after_days"] = args.updated_after_days
        if args.editor_user_id is not None and args.editor_user_id.strip() != "":
            payload["editor_user_id"] = args.editor_user_id.strip()
        raw = await self._http.post(
            "wiki",
            f"{_API}/search",
            headers=self._ns_headers(),
            json=payload,
        )
        body = require_json_object(raw, "wiki.search")
        items = self._as_objects(body.get("items"), "wiki.search.items")
        briefs: list[JsonObject] = [
            {
                "wiki_page_id": item.get("wiki_page_id"),
                "namespace": item.get("namespace"),
                "title": item.get("title"),
                "icon": item.get("icon"),
                "snippet": item.get("snippet"),
                "heading_path": item.get("heading_path"),
                "score": item.get("score"),
                "channel": item.get("channel"),
                "updated_at": item.get("updated_at"),
            }
            for item in items
        ]
        return {"count": len(briefs), "items": briefs, "mode": args.mode}

    async def list_backlinks(
        self,
        target_kind: (
            Literal[
                "wiki_page",
                "crm_entity",
                "file",
                "work_item",
                "sync_message",
                "url",
            ]
            | WikiBacklinksArgs
        ),
        target_id: str = "",
        limit: int = 50,
    ) -> JsonObject:
        if isinstance(target_kind, WikiBacklinksArgs):
            args = target_kind
        else:
            args = WikiBacklinksArgs(
                target_kind=target_kind,
                target_id=target_id,
                limit=limit,
            )
        raw = await self._http.get(
            "wiki",
            f"{_API}/backlinks",
            headers=self._ns_headers(),
            params={
                "target_kind": args.target_kind,
                "target_id": args.target_id.strip(),
                "limit": str(args.limit),
            },
        )
        body = require_json_object(raw, "wiki.backlinks")
        items = self._as_objects(body.get("items"), "wiki.backlinks.items")
        briefs: list[JsonObject] = [
            {
                "wiki_page_id": item.get("wiki_page_id"),
                "namespace": item.get("namespace"),
                "title": item.get("title"),
                "icon": item.get("icon"),
                "url": item.get("url"),
                "updated_at": item.get("updated_at"),
            }
            for item in items
        ]
        return {
            "target_kind": args.target_kind,
            "target_id": args.target_id,
            "count": len(briefs),
            "items": briefs,
        }


__all__ = ["WikiClient"]
