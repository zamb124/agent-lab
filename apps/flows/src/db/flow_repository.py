"""
Репозиторий для FlowConfig с версионированием.

Две таблицы:
- flows: актуальные конфиги
- flows_versions: история версий
"""

import json
from datetime import datetime, timezone
from typing import List, Optional

from apps.flows.src.models import FlowConfig

from core.db import BaseRepository
from core.db import Storage
from core.logging import get_logger

logger = get_logger(__name__)


class FlowRepository(BaseRepository[FlowConfig]):
    """
    Репозиторий для flow с версионированием.
    Данные изолированы по компаниям (is_global=False).
    """
    
    is_global = False
    owner_service = "flows"

    def __init__(self, storage: Storage):
        super().__init__(storage, FlowConfig)

    def _get_key(self, entity_id: str) -> str:
        return f"flow:{entity_id}"
    
    def _get_prefix(self) -> str:
        return "flow:"
    
    def _get_table_name(self) -> str:
        return "flows"

    def _get_versions_table(self) -> str:
        return "flows_versions"

    def _extract_entity_id(self, entity: FlowConfig) -> str:
        return entity.flow_id

    async def set(self, entity: FlowConfig) -> bool:
        """
        Сохраняет новую версию агента.
        
        Генерирует timestamp версию и сохраняет:
        - Версию в flows_versions
        - Актуальный конфиг в flows
        """
        flow_id = entity.flow_id
        
        # Генерируем timestamp версию
        new_version = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
        entity.version = new_version
        
        data = entity.model_dump_json()
        
        # Сохраняем версию в flows_versions
        version_key = self._get_key(f"{flow_id}_v{new_version}")
        final_version_key = self._build_final_key(version_key)
        await self._storage._set_with_table(final_version_key, data, self._get_versions_table())
        
        # Сохраняем актуальный конфиг в flows
        await super().set(entity)
        
        logger.info(f"Flow '{flow_id}' saved as version {new_version}")
        return True

    async def get(self, flow_id: str) -> Optional[FlowConfig]:
        """Получает последнюю версию агента."""
        return await self.get_latest(flow_id)

    async def get_latest(self, flow_id: str) -> Optional[FlowConfig]:
        """
        Получает последнюю версию из таблицы flows.
        """
        # Используем базовый метод get из BaseRepository
        return await super().get(flow_id)

    async def get_version(self, flow_id: str, version: str) -> Optional[FlowConfig]:
        """
        Получает конкретную версию из flows_versions.
        """
        version_key = self._get_key(f"{flow_id}_v{version}")
        final_version_key = self._build_final_key(version_key)
        data = await self._storage._get_with_session_and_table(final_version_key, self._get_versions_table())
        
        if not data:
            return None
            
        return self.model_class.model_validate_json(data)

    async def list_versions(self, flow_id: str) -> List[str]:
        """
        Список всех версий (от новых к старым) из flows_versions.
        """
        prefix = self._get_key(f"{flow_id}_v")
        final_prefix = self._build_final_key(prefix)
        all_data = await self._storage._get_all_by_prefix_and_table(final_prefix, self._get_versions_table(), 1000)
        
        versions = []
        for key in all_data.keys():
            # Формат: flow:{flow_id}_v{timestamp} или company:{company_id}:flow:{flow_id}_v{timestamp}
            # Ищем последнее вхождение _v чтобы извлечь timestamp
            parts = key.rsplit("_v", 1)
            if len(parts) == 2:
                versions.append(parts[1])
        
        return sorted(versions, reverse=True)

    async def list_all(self, limit: int = 100) -> List[FlowConfig]:
        """
        Список всех flow (последние версии).
        
        Читает из таблицы flows.
        """
        # Получаем все ключи из flows (не flows_versions)
        base_prefix = self._get_prefix()
        final_prefix = self._build_final_key(base_prefix)
        all_data = await self._storage._get_all_by_prefix_and_table(
            final_prefix, self._get_table_name(), limit
        )
        
        items: List[FlowConfig] = []
        for key, value in all_data.items():
            try:
                cfg = self.model_class.model_validate_json(value)
                items.append(cfg)
            except Exception as e:
                logger.warning(f"Failed to parse flow from key {key}: {e}")
                continue
        
        return items

    async def delete(self, flow_id: str) -> bool:
        """
        Удаляет flow со всеми версиями из обеих таблиц.
        Возвращает False если запись не существовала.
        """
        current = await self.get(flow_id)
        
        versions = await self.list_versions(flow_id)
        
        if not current and not versions:
            logger.info(f"Flow '{flow_id}' not found, nothing to delete")
            return False
        
        if current:
            row_key = self._get_key(flow_id)
            final_flow_key = self._build_final_key(row_key)
            await self._storage._delete_with_table(final_flow_key, self._get_table_name())
        
        for version in versions:
            version_key = self._get_key(f"{flow_id}_v{version}")
            final_version_key = self._build_final_key(version_key)
            await self._storage._delete_with_table(final_version_key, self._get_versions_table())
        
        logger.info(f"Flow '{flow_id}' deleted with {len(versions)} versions")
        return True

    async def rollback_to_version(self, flow_id: str, version: str) -> bool:
        """
        Откатывает flow к указанной версии.
        
        Копирует указанную версию из flows_versions в flows.
        """
        snapshot = await self.get_version(flow_id, version)
        if snapshot is None:
            return False
        
        data = snapshot.model_dump_json()
        key = self._get_key(flow_id)
        final_key = self._build_final_key(key)
        await self._storage._set_with_table(final_key, data, self._get_table_name())
        
        logger.info(f"Flow '{flow_id}' rolled back to version {version}")
        return True
