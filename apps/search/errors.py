"""Search index registry errors."""

from __future__ import annotations


class SearchIndexError(Exception):
    pass


class SearchIndexNotFoundError(SearchIndexError):
    def __init__(self, search_index_id: str) -> None:
        self.search_index_id: str = search_index_id
        super().__init__(f"search index not found: {search_index_id}")


class SearchIndexSearchDisabledError(SearchIndexError):
    def __init__(self, search_index_id: str) -> None:
        self.search_index_id: str = search_index_id
        super().__init__(f"search disabled for index: {search_index_id}")
