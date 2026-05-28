"""Контракты search-провайдеров."""

from __future__ import annotations

from typing import Protocol

from core.search import MetaSearchProviderStatus, MetaSearchRequest, WebSearchResult


class SearchProvider(Protocol):
    """Типизированный контракт адаптера для внешних search-провайдеров."""

    provider_id: str

    async def search(
        self,
        request: MetaSearchRequest,
    ) -> tuple[list[WebSearchResult], MetaSearchProviderStatus]: ...
