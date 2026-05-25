"""
Репозиторий для FlowConfig с версионированием.

Две таблицы:
- flows: актуальные конфиги
- flows_versions: история версий
"""

from datetime import datetime, timezone
from typing import ClassVar, override

from pydantic import ValidationError

from apps.flows.src.models import FlowConfig
from core.db import BaseRepository, Storage
from core.logging import get_logger
from core.types import parse_json_object

logger = get_logger(__name__)


def _flow_config_from_storage_json(raw: str) -> FlowConfig:
    payload = parse_json_object(raw, "flow_config")
    return FlowConfig.model_validate(payload)


class FlowRepository(BaseRepository[FlowConfig]):
    """
    Репозиторий для flow с версионированием.
    Данные изолированы по компаниям (is_global=False).
    """

    is_global: ClassVar[bool] = False
    owner_service: ClassVar[str] = "flows"

    def __init__(self, storage: Storage):
        super().__init__(storage, FlowConfig)

    @override
    def _get_key(self, entity_id: str) -> str:
        return f"flow:{entity_id}"

    @override
    def _get_prefix(self) -> str:
        return "flow:"

    @override
    def _get_table_name(self) -> str:
        return "flows"

    def _get_versions_table(self) -> str:
        return "flows_versions"

    @override
    def _extract_entity_id(self, entity: FlowConfig) -> str:
        return entity.flow_id

    @override
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
        _ = await self._storage.set_with_table(final_version_key, data, self._get_versions_table())

        # Сохраняем актуальный конфиг в flows
        _ = await super().set(entity)

        logger.info(f"Flow '{flow_id}' saved as version {new_version}")
        return True

    @override
    async def get(self, entity_id: str) -> FlowConfig | None:
        """Получает последнюю версию агента."""
        return await self.get_latest(entity_id)

    async def get_latest(self, flow_id: str) -> FlowConfig | None:
        """
        Получает последнюю версию из таблицы flows.
        """
        base_key = self._get_key(flow_id)
        final_key = self._build_final_key(base_key)
        table_name = self._get_table_name()
        data = await self._storage.get_with_session_and_table(final_key, table_name)
        if data is None:
            return None
        return _flow_config_from_storage_json(data)

    async def get_latest_by_flow_id_unscoped(
        self, flow_id: str
    ) -> tuple[FlowConfig, str] | None:
        """
        Ищет актуальный flow по flow_id по всем ключам company:*:flow:* без контекста компании.

        Нужен для публичного POST Telegram (в запросе нет company context, как у серверов Telegram).
        Возвращает (config, company_identifier) — идентификатор сегмента company:* из ключа.
        """
        table_name = self._get_table_name()
        all_data = await self._storage.get_all_by_prefix_and_table(
            "company:", table_name, 10_000, 0
        )
        for key, raw in all_data.items():
            if f"flow:{flow_id}_v" in key:
                continue
            if not key.endswith(f"flow:{flow_id}"):
                continue
            parts = key.split(":")
            if len(parts) < 4 or parts[0] != "company" or parts[2] != "flow":
                continue
            if parts[3] != flow_id:
                continue
            company_identifier = parts[1]
            return (_flow_config_from_storage_json(raw), company_identifier)
        return None

    async def list_company_identifiers(
        self,
        *,
        limit: int = 10_000,
        offset: int = 0,
    ) -> list[str]:
        """Вернуть company identifiers из ключей актуальной таблицы flows."""
        table_name = self._get_table_name()
        all_data = await self._storage.get_all_by_prefix_and_table(
            "company:", table_name, limit, offset
        )
        identifiers: set[str] = set()
        for key in all_data.keys():
            parts = key.split(":")
            if len(parts) < 4 or parts[0] != "company" or parts[2] != "flow":
                continue
            identifiers.add(parts[1])
        return sorted(identifiers)

    async def get_version(self, flow_id: str, version: str) -> FlowConfig | None:
        """
        Получает конкретную версию из flows_versions.
        """
        version_key = self._get_key(f"{flow_id}_v{version}")
        final_version_key = self._build_final_key(version_key)
        data = await self._storage.get_with_session_and_table(final_version_key, self._get_versions_table())

        if not data:
            return None

        return _flow_config_from_storage_json(data)

    async def list_versions(self, flow_id: str) -> list[str]:
        """
        Список всех версий (от новых к старым) из flows_versions.
        """
        prefix = self._get_key(f"{flow_id}_v")
        final_prefix = self._build_final_key(prefix)
        all_data = await self._storage.get_all_by_prefix_and_table(final_prefix, self._get_versions_table(), 1000)

        versions: list[str] = []
        for key in all_data.keys():
            # Формат: flow:{flow_id}_v{timestamp} или company:{company_id}:flow:{flow_id}_v{timestamp}
            # Ищем последнее вхождение _v чтобы извлечь timestamp
            parts = key.rsplit("_v", 1)
            if len(parts) == 2:
                versions.append(parts[1])

        return sorted(versions, reverse=True)

    @override
    async def get_many(self, entity_ids: list[str]) -> dict[str, FlowConfig]:
        if not entity_ids:
            return {}
        table_name = self._get_table_name()
        final_keys = [self._build_final_key(self._get_key(eid)) for eid in entity_ids]
        all_data = await self._storage.get_many_with_table(final_keys, table_name)
        result: dict[str, FlowConfig] = {}
        for i, entity_id in enumerate(entity_ids):
            final_key = final_keys[i]
            if final_key in all_data:
                try:
                    result[entity_id] = _flow_config_from_storage_json(all_data[final_key])
                except (ValueError, ValidationError) as e:
                    logger.warning("Failed to parse flow %s: %s", entity_id, e)
        return result

    @override
    async def list(self, *, limit: int, offset: int = 0) -> list[FlowConfig]:
        """Страница flow (последние версии). Читает из таблицы flows."""
        base_prefix = self._get_prefix()
        final_prefix = self._build_final_key(base_prefix)
        all_data = await self._storage.get_all_by_prefix_and_table(
            final_prefix, self._get_table_name(), limit, offset
        )

        items: list[FlowConfig] = []
        for key, value in all_data.items():
            try:
                cfg = _flow_config_from_storage_json(value)
                items.append(cfg)
            except (ValueError, ValidationError) as e:
                logger.warning(f"Failed to parse flow from key {key}: {e}")
                continue

        return items

    @override
    async def delete(self, entity_id: str) -> bool:
        """
        Удаляет flow со всеми версиями из обеих таблиц.
        Возвращает False если запись не существовала.
        """
        flow_id = entity_id
        current = await self.get(flow_id)

        versions = await self.list_versions(flow_id)

        if not current and not versions:
            logger.info(f"Flow '{flow_id}' not found, nothing to delete")
            return False

        if current:
            row_key = self._get_key(flow_id)
            final_flow_key = self._build_final_key(row_key)
            _ = await self._storage.delete_with_table(final_flow_key, self._get_table_name())

        for version in versions:
            version_key = self._get_key(f"{flow_id}_v{version}")
            final_version_key = self._build_final_key(version_key)
            _ = await self._storage.delete_with_table(final_version_key, self._get_versions_table())

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
        _ = await self._storage.set_with_table(final_key, data, self._get_table_name())

        logger.info(f"Flow '{flow_id}' rolled back to version {version}")
        return True
