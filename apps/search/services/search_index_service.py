"""Search index registry orchestration."""

from __future__ import annotations

from apps.search.db.search_index_repository import SearchIndexRepository
from core.clients.rag_client import RagClient
from core.search.index_models import (
    SearchIndexCreateRequest,
    SearchIndexDefinition,
    SearchIndexPatchRequest,
)


class SearchIndexService:
    def __init__(
        self,
        search_index_repository: SearchIndexRepository,
        rag_client: RagClient,
    ) -> None:
        self._search_index_repository: SearchIndexRepository = search_index_repository
        self._rag_client: RagClient = rag_client

    async def create(self, body: SearchIndexCreateRequest) -> SearchIndexDefinition:
        definition = await self._search_index_repository.create("system", body)
        _ = await self._rag_client.create_namespace(
            definition.rag_namespace_id,
            description=definition.description or definition.display_name,
        )
        return definition

    async def patch(self, search_index_id: str, body: SearchIndexPatchRequest) -> SearchIndexDefinition:
        return await self._search_index_repository.patch(search_index_id, company_id="system", body=body)

    async def batch_get(self, search_index_ids: list[str]) -> list[SearchIndexDefinition]:
        return await self._search_index_repository.batch_get(search_index_ids, company_id="system")
