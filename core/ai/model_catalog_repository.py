"""Shared AI provider model catalog repository."""

from __future__ import annotations

from typing import ClassVar, override

from core.ai.models import AIModelRecord
from core.ai.providers import AICapability
from core.db import BaseRepository, Storage


class AIModelCatalogRepository(BaseRepository[AIModelRecord]):
    """One shared provider model catalog for every AI capability."""

    is_global: ClassVar[bool] = True
    owner_service: ClassVar[str] = "core"

    def __init__(self, storage: Storage) -> None:
        super().__init__(storage, AIModelRecord)

    @override
    def _get_key(self, entity_id: str) -> str:
        return f"ai_model_catalog:{entity_id}"

    @override
    def _get_prefix(self) -> str:
        return "ai_model_catalog:"

    @override
    def _extract_entity_id(self, entity: AIModelRecord) -> str:
        return f"{entity.provider}:{entity.model_id}"

    async def list_by_provider(self, provider: str) -> list[AIModelRecord]:
        base_prefix = self._get_prefix()
        final_prefix = self._build_final_key(base_prefix)
        table_name = self._get_table_name()
        raw_rows = await self._storage.get_all_by_prefix_and_table_with_json_eq(
            final_prefix,
            table_name,
            json_field="provider",
            json_value=provider,
            limit=1_000_000,
        )
        return [AIModelRecord.model_validate_json(value) for value in raw_rows.values()]

    async def list_by_provider_capability(
        self,
        provider: str,
        capability: AICapability,
    ) -> list[AIModelRecord]:
        rows = await self.list_by_provider(provider)
        return [row for row in rows if capability in row.capabilities]

    async def get_provider_model(self, provider: str, model_id: str) -> AIModelRecord | None:
        return await self.get(f"{provider}:{model_id}")

    async def delete_by_provider(self, provider: str) -> int:
        models = await self.list_by_provider(provider)
        count = 0
        for model in models:
            deleted = await self.delete(self._extract_entity_id(model))
            if deleted:
                count += 1
        return count


__all__ = ["AIModelCatalogRepository"]
