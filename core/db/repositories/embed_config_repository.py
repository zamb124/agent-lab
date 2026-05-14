"""
Репозиторий для работы с конфигурациями встраиваемых виджетов.
"""

from datetime import datetime, timezone
from typing import List, Optional

from core.db.base_repository import BaseRepository
from core.db.storage import Storage
from core.logging import get_logger
from core.models.embed_models import EmbedConfig

logger = get_logger(__name__)
class EmbedConfigRepository(BaseRepository[EmbedConfig]):
    """
    Репозиторий для работы с конфигурациями встраиваемых виджетов.
    is_global=False - виджеты изолированы по компаниям.

    Ключи: company:{company_id}:embed_config:{embed_id}
    """

    is_global = False

    def __init__(self, storage: Storage):
        super().__init__(storage=storage, model_class=EmbedConfig)

    def _get_key(self, embed_id: str) -> str:
        return f"embed_config:{embed_id}"

    def _get_prefix(self) -> str:
        return "embed_config:"

    def _get_table_name(self) -> str:
        return "storage"

    def _extract_entity_id(self, entity: EmbedConfig) -> str:
        return entity.embed_id

    def _final_key_for_company_identifier(self, company_identifier: str, embed_id: str) -> str:
        base_key = self._get_key(embed_id)
        return f"company:{company_identifier}:{base_key}"

    def _final_prefix_for_company_identifier(self, company_identifier: str) -> str:
        base_prefix = self._get_prefix()
        return f"company:{company_identifier}:{base_prefix}"

    async def get_for_company_identifier(
        self, company_identifier: str, embed_id: str
    ) -> Optional[EmbedConfig]:
        final_key = self._final_key_for_company_identifier(company_identifier.strip(), embed_id)
        table_name = self._get_table_name()
        data = await self._storage._get_with_session_and_table(final_key, table_name)
        if data is None:
            return None
        return self.model_class.model_validate_json(data)

    async def list_for_company_identifier(
        self, company_identifier: str, *, limit: int, offset: int = 0
    ) -> List[EmbedConfig]:
        final_prefix = self._final_prefix_for_company_identifier(company_identifier.strip())
        table_name = self._get_table_name()
        all_data = await self._storage._get_all_by_prefix_and_table(
            final_prefix, table_name, limit, offset
        )
        entities: List[EmbedConfig] = []
        for key, data in all_data.items():
            try:
                entity = self.model_class.model_validate_json(data)
                entities.append(entity)
            except Exception as e:
                logger.error(f"Ошибка парсинга {key}: {e}")
                continue
        return entities

    async def increment_usage(self, embed_id: str) -> None:
        """Увеличение счетчика использований виджета"""
        config = await self.get(embed_id)
        if config:
            config.usage_count += 1
            config.last_used_at = datetime.now(timezone.utc)
            await self.set(config)
            logger.debug(f"Увеличен счетчик использований виджета {embed_id}: {config.usage_count}")

