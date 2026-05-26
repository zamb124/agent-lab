"""Search provider contracts."""

from __future__ import annotations

from typing import Protocol

from core.search import MetaSearchProviderStatus, MetaSearchRequest, WebSearchResult


class SearchProvider(Protocol):
    """Typed adapter contract for external search providers."""

    provider_id: str

    async def search(
        self,
        request: MetaSearchRequest,
    ) -> tuple[list[WebSearchResult], MetaSearchProviderStatus]: ...
