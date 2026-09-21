"""Ошибки реестра индексов Search: подклассы границы с `search_index_id`."""

from __future__ import annotations

from core.errors.boundary import PlatformConflictError, PlatformNotFoundError


class SearchIndexNotFoundError(PlatformNotFoundError):
    def __init__(self, search_index_id: str) -> None:
        self.search_index_id: str = search_index_id
        super().__init__(f"search index not found: {search_index_id}")


class SearchIndexSearchDisabledError(PlatformConflictError):
    def __init__(self, search_index_id: str) -> None:
        self.search_index_id: str = search_index_id
        super().__init__(f"search disabled for index: {search_index_id}")
