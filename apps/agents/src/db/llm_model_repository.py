"""
Репозиторий для LLMModel.
"""

from typing import List

from apps.agents.src.models import LLMModel

from core.db import BaseRepository
from core.db import Storage


class LLMModelRepository(BaseRepository[LLMModel]):
    """Репозиторий для работы с LLM моделями."""
    
    is_global = True  # Глобальные модели (не изолированы по компаниям)
    owner_service = "agents"

    def __init__(self, storage: Storage):
        super().__init__(storage, LLMModel)

    def _get_key(self, entity_id: str) -> str:
        return f"llm_model:{entity_id}"
    
    def _get_prefix(self) -> str:
        return "llm_model:"

    def _extract_entity_id(self, entity: LLMModel) -> str:
        """Формирует ID как provider:model_id для уникальности."""
        return f"{entity.provider}:{entity.model_id}"

    async def list_by_provider(self, provider: str) -> List[LLMModel]:
        """Возвращает все модели указанного провайдера."""
        # Получаем все модели и фильтруем по провайдеру
        all_models = await self.list_all(limit=10000)
        return [model for model in all_models if model.provider == provider]

    async def delete_by_provider(self, provider: str) -> int:
        """Удаляет все модели указанного провайдера."""
        models = await self.list_by_provider(provider)
        count = 0
        for model in models:
            deleted = await self.delete(self._extract_entity_id(model))
            if deleted:
                count += 1
        return count

