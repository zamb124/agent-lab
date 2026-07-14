"""Репозиторий AgentSkill."""

from typing import ClassVar, override

from apps.flows.src.models.agent_skill import AgentSkill
from core.db import BaseRepository, Storage


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
