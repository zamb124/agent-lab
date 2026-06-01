"""
Репозиторий для LLMModel.
"""


from typing import ClassVar, override

from apps.flows.src.models import LLMModel
from core.ai_provider_catalog import AICapability
from core.db import BaseRepository, Storage


class LLMModelRepository(BaseRepository[LLMModel]):
    """Репозиторий для работы с LLM моделями."""

    is_global: ClassVar[bool] = True  # Глобальные модели (не изолированы по компаниям)
    owner_service: ClassVar[str] = "flows"

    def __init__(self, storage: Storage):
        super().__init__(storage, LLMModel)

    @override
    def _get_key(self, entity_id: str) -> str:
        return f"llm_model:{entity_id}"

    @override
    def _get_prefix(self) -> str:
        return "llm_model:"

    @override
    def _extract_entity_id(self, entity: LLMModel) -> str:
        """Формирует ID как provider:model_id для уникальности."""
        return f"{entity.provider}:{entity.model_id}"

    async def list_by_provider(self, provider: str) -> list[LLMModel]:
        """
        Возвращает все модели указанного провайдера.

        Раньше делал `list(limit=10000)` + Python-фильтр (full scan по всем
        моделям + сериализация в pydantic + отбрасывание). Теперь фильтр уходит
        в PostgreSQL через `value->>'provider' = ?`: загружаются только нужные
        строки, без артифициального лимита 10000.
        """
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
        return [LLMModel.model_validate_json(value) for value in raw_rows.values()]

    async def list_by_provider_capability(
        self,
        provider: str,
        capability: AICapability,
    ) -> list[LLMModel]:
        """Возвращает модели провайдера, поддерживающие capability."""
        rows = await self.list_by_provider(provider)
        return [row for row in rows if capability in row.capabilities]

    async def get_provider_model(self, provider: str, model_id: str) -> LLMModel | None:
        """Получает запись по каноническому ключу provider:model_id."""
        return await self.get(f"{provider}:{model_id}")

    async def delete_by_provider(self, provider: str) -> int:
        """Удаляет все модели указанного провайдера."""
        models = await self.list_by_provider(provider)
        count = 0
        for model in models:
            deleted = await self.delete(self._extract_entity_id(model))
            if deleted:
                count += 1
        return count
