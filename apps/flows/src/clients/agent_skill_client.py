"""AgentSkillClient — catalog access for load_agent_skill / read_agent_skill_reference."""

from __future__ import annotations

from apps.flows.src.container_state import require_current_container
from apps.flows.src.models.agent_skill import AgentSkill
from apps.flows.src.services.agent_skill_service import AgentSkillService


class AgentSkillClient:
    """Чтение Agent Skill из каталога компании."""

    _service: AgentSkillService

    def __init__(self, service: AgentSkillService | None = None) -> None:
        self._service = (
            service
            if service is not None
            else require_current_container().agent_skill_service
        )

    async def get(self, agent_skill_id: str) -> AgentSkill:
        return await self._service.get(agent_skill_id)
