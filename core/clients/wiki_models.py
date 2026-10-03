"""Pydantic input models for Wiki REST client and Flows tools."""

from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field


class WikiEmptyArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")


class WikiPageIdArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    wiki_page_id: str = Field(..., min_length=1, description="wiki_page_id from tools/UI. Never invent.")


class WikiCreatePageArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field("", max_length=500, description="Page title.")
    markdown: str = Field("", description="Initial body as markdown (CommonMark/GFM).")
    parent_page_id: str | None = Field(None, description="Parent wiki_page_id; omit for root.")
    icon: str = Field("", max_length=64, description="Optional emoji/icon.")


class WikiUpdateMarkdownArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    wiki_page_id: str = Field(..., min_length=1, description="wiki_page_id to update.")
    markdown: str = Field(..., min_length=1, description="Full new body as markdown.")
    title: str | None = Field(None, max_length=500, description="Optional new title.")
    create_revision: bool = Field(True, description="Save current state to revision history.")


class WikiUpdatePropertiesArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    wiki_page_id: str = Field(..., min_length=1, description="wiki_page_id.")
    title: str | None = Field(None, max_length=500, description="New page title; omit to keep current.")
    icon: str | None = Field(None, max_length=64, description="New emoji/icon; omit to keep current.")
    cover_url: str | None = Field(
        None,
        description="Cover download URL (/{segment}/api/v1/files/download/{file_id}).",
    )
    is_published: bool | None = Field(
        None,
        description="Publish state; required for public site link. Omit to keep current.",
    )
    is_template: bool | None = Field(None, description="Mark page as a template; omit to keep current.")
    is_full_width: bool | None = Field(None, description="Full-width layout flag; omit to keep current.")


class WikiMovePageArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    wiki_page_id: str = Field(..., min_length=1, description="wiki_page_id of the page to move.")
    parent_page_id: str | None = Field(None, description="New parent; null = root.")
    position: int | None = Field(None, ge=0, description="Sibling order; omit to append.")


class WikiMoveNamespaceArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    wiki_page_id: str = Field(..., min_length=1, description="wiki_page_id of the subtree root to move.")
    target_namespace: str = Field(..., min_length=1, description="Company workspace slug.")
    parent_page_id: str | None = Field(None, description="Parent in target namespace.")


class WikiImportMarkdownArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    markdown: str = Field(
        ...,
        min_length=1,
        description="Full markdown file including optional YAML front matter.",
    )
    wiki_page_id: str | None = Field(
        None,
        description="If set — replace that page; if omit — create a new page.",
    )
    parent_page_id: str | None = Field(
        None,
        description="Parent for create; ignored when replacing an existing page.",
    )
    apply_front_matter: bool = Field(
        True,
        description="Apply title/icon/cover from YAML front matter.",
    )


class WikiParseMarkdownArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    markdown: str = Field(..., min_length=1, description="Markdown to validate without writing.")


class WikiListRevisionsArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    wiki_page_id: str = Field(..., min_length=1, description="wiki_page_id to list revisions for.")
    limit: int = Field(50, ge=1, le=200, description="Max revisions returned (newest first).")


class WikiRevisionIdArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    wiki_revision_id: str = Field(..., min_length=1, description="wiki_revision_id from list.")


class WikiCreateCommentArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    wiki_page_id: str = Field(..., min_length=1, description="wiki_page_id to comment on.")
    body_markdown: str = Field(..., min_length=1, description="Comment text as markdown.")
    anchor_text: str = Field("", description="Quoted fragment in the page.")
    parent_comment_id: str | None = Field(None, description="Reply parent wiki_comment_id.")


class WikiCommentIdArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    wiki_comment_id: str = Field(..., min_length=1, description="wiki_comment_id from wiki_list_comments.")


class WikiResolveCommentArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    wiki_comment_id: str = Field(..., min_length=1, description="wiki_comment_id from wiki_list_comments.")
    resolved: bool = Field(True, description="true — resolve; false — reopen.")


class WikiSetMemberArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    wiki_page_id: str = Field(..., min_length=1, description="wiki_page_id of the page.")
    user_id: str = Field(..., min_length=1, description="From team_resolve_user / team_list_members.")
    relation: Literal["viewer", "editor"] = Field("viewer", description="Member access level.")


class WikiCompanyVisibleArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    wiki_page_id: str = Field(..., min_length=1, description="wiki_page_id of the page.")
    company_visible: bool = Field(
        ..., description="true — вся компания; false — только явные участники."
    )


class WikiRemoveMemberArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    wiki_page_id: str = Field(..., min_length=1, description="wiki_page_id of the page.")
    user_id: str = Field(..., min_length=1, description="User id from team_resolve_user / team_list_members.")


class WikiRotatePublicLinkArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    wiki_page_id: str = Field(..., min_length=1, description="wiki_page_id of the page.")
    enabled: bool = Field(..., description="true — enable/rotate; false — disable.")
    permission: Literal["viewer", "editor"] = Field(
        "viewer",
        description="Access level granted by the public link.",
    )


class WikiSearchArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    query: str = Field(..., min_length=1, max_length=500, description="Search query text.")
    mode: Literal["auto", "semantic", "lexical"] = Field(
        "auto",
        description="auto — pick the best channel; semantic/lexical — force a channel.",
    )
    root_page_id: str | None = Field(None, description="Limit search to a subtree.")
    published_only: bool = Field(False, description="true — only published pages.")
    updated_after_days: int | None = Field(
        None,
        ge=1,
        le=3650,
        description="Only pages updated within the last N days.",
    )
    editor_user_id: str | None = Field(
        None,
        description="Only pages last edited by this user_id.",
    )
    limit: int = Field(20, ge=1, le=50, description="Max results.")


class WikiBacklinksArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    target_kind: Literal[
        "wiki_page",
        "crm_entity",
        "file",
        "work_item",
        "sync_message",
        "url",
    ] = Field(..., description="Linked entity kind.")
    target_id: str = Field(..., min_length=1, description="Entity id or URL.")
    limit: int = Field(50, ge=1, le=200, description="Max backlinks returned.")


__all__ = [
    "WikiEmptyArgs",
    "WikiPageIdArgs",
    "WikiCreatePageArgs",
    "WikiUpdateMarkdownArgs",
    "WikiUpdatePropertiesArgs",
    "WikiMovePageArgs",
    "WikiMoveNamespaceArgs",
    "WikiImportMarkdownArgs",
    "WikiParseMarkdownArgs",
    "WikiListRevisionsArgs",
    "WikiRevisionIdArgs",
    "WikiCreateCommentArgs",
    "WikiCommentIdArgs",
    "WikiResolveCommentArgs",
    "WikiSetMemberArgs",
    "WikiCompanyVisibleArgs",
    "WikiRemoveMemberArgs",
    "WikiRotatePublicLinkArgs",
    "WikiSearchArgs",
    "WikiBacklinksArgs",
]
