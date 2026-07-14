"""Репозиторий AgentSkill."""

from typing import ClassVar, override

from apps.flows.src.models.agent_skill import AgentSkill, parse_stored_agent_skill
from core.db import BaseRepository, Storage
from core.logging import get_logger

logger = get_logger(__name__)


class AgentSkillRepository(BaseRepository[AgentSkill]):
    """CRUD catalog Agent Skills (company-scoped KV)."""

    is_global: ClassVar[bool] = False
    owner_service: ClassVar[str] = "flows"

    def __init__(self, storage: Storage) -> None:
        super().__init__(storage, AgentSkill)

    @override
    def _get_key(self, entity_id: str) -> str:
        return f"agent_skill:{entity_id}"

    @override
    def _get_prefix(self) -> str:
        return "agent_skill:"

    @override
    def _get_table_name(self) -> str:
        return "agent_skills"

    @override
    def _extract_entity_id(self, entity: AgentSkill) -> str:
        return entity.agent_skill_id

    @override
    async def get(self, entity_id: str) -> AgentSkill | None:
        base_key = self._get_key(entity_id)
        final_key = self._build_final_key(base_key)
        table_name = self._get_table_name()
        data = await self._storage.get_with_session_and_table(final_key, table_name)
        if data is None:
            return None
        return parse_stored_agent_skill(data)

    @override
    async def list(self, *, limit: int, offset: int = 0) -> list[AgentSkill]:
        base_prefix = self._get_prefix()
        final_prefix = self._build_final_key(base_prefix)
        table_name = self._get_table_name()
        all_data = await self._storage.get_all_by_prefix_and_table(
            final_prefix, table_name, limit, offset
        )
        entities: list[AgentSkill] = []
        for key, data in all_data.items():
            try:
                entities.append(parse_stored_agent_skill(data))
            except Exception as e:
                logger.error(f"Ошибка парсинга {key}: {e}")
                continue
        return entities

    @override
    async def get_many(self, entity_ids: list[str]) -> dict[str, AgentSkill]:
        if not entity_ids:
            return {}
        table_name = self._get_table_name()
        final_keys = [self._build_final_key(self._get_key(eid)) for eid in entity_ids]
        all_data = await self._storage.get_many_with_table(final_keys, table_name)
        result: dict[str, AgentSkill] = {}
        for i, entity_id in enumerate(entity_ids):
            final_key = final_keys[i]
            if final_key in all_data:
                try:
                    result[entity_id] = parse_stored_agent_skill(all_data[final_key])
                except Exception as e:
                    logger.error(f"Ошибка парсинга {entity_id}: {e}")
                    continue
        return result
