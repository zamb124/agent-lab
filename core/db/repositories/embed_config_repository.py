"""
Репозиторий для работы с конфигурациями встраиваемых виджетов.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from core.db.base_repository import BaseRepository
from core.db.storage import Storage
from core.models.embed_models import EmbedConfig

logger = logging.getLogger(__name__)


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
    
    async def increment_usage(self, embed_id: str) -> None:
        """Увеличение счетчика использований виджета"""
        config = await self.get(embed_id)
        if config:
            config.usage_count += 1
            config.last_used_at = datetime.now(timezone.utc)
            await self.set(config)
            logger.debug(f"Увеличен счетчик использований виджета {embed_id}: {config.usage_count}")


