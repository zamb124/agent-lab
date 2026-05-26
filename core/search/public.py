"""Public search embed constants."""

from __future__ import annotations

from typing import Final, Literal

PublicSearchMode = Literal["quick", "deep", "research", "source"]

PUBLIC_SEARCH_FLOW_ID: Final = "public_search"
PUBLIC_SEARCH_SESSION_ISSUER: Final = "frontend.public_search"

PUBLIC_SEARCH_EMBED_ID_BY_MODE: Final[dict[PublicSearchMode, str]] = {
    "quick": "public_search_quick",
    "deep": "public_search_deep",
    "research": "public_search_research",
    "source": "public_search_source",
}

PUBLIC_SEARCH_BRANCH_ID_BY_MODE: Final[dict[PublicSearchMode, str]] = {
    "quick": "quick",
    "deep": "deep",
    "research": "research",
    "source": "source",
}


def public_search_embed_id(mode: PublicSearchMode) -> str:
    return PUBLIC_SEARCH_EMBED_ID_BY_MODE[mode]


def public_search_branch_id(mode: PublicSearchMode) -> str:
    return PUBLIC_SEARCH_BRANCH_ID_BY_MODE[mode]
