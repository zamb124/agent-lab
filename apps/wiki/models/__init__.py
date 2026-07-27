"""Доменные модели wiki."""

from apps.wiki.models.domain import (
    WikiBacklink,
    WikiComment,
    WikiLinkPermission,
    WikiLinkTargetKind,
        WikiPage,
    WikiPageAccess,
    WikiPageLink,
    WikiPageMember,
    WikiPagePermission,
    WikiPageSummary,
    WikiRevision,
    WikiRevisionSummary,
    WikiSearchHit,
    WikiVisibility,
)

__all__ = [
    "WikiBacklink",
    "WikiComment",
    "WikiLinkPermission",
    "WikiLinkTargetKind",
    "WikiPage",
    "WikiPageAccess",
    "WikiPageLink",
    "WikiPageMember",
    "WikiPagePermission",
    "WikiPageSummary",
    "WikiRevision",
    "WikiRevisionSummary",
    "WikiSearchHit",
    "WikiVisibility",
]
