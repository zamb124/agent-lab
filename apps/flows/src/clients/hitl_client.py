"""HitlClient — HITL operator handoff registration for hitl_operator_task."""

from __future__ import annotations

from uuid import UUID

from apps.flows.src.container_state import require_current_container
from apps.flows.src.models.hitl_schemas import HitlHandoffCommand
from apps.flows.src.services.hitl_work_item_service import HitlWorkItemService
from core.state import ExecutionState
from core.state.interrupt import HandoffMode


class HitlClient:
    """Регистрация HITL WorkItem + correlation для operator task interrupt."""

    _service: HitlWorkItemService

    def __init__(self, service: HitlWorkItemService | None = None) -> None:
        self._service = (
            service
            if service is not None
            else require_current_container().hitl_work_item_service
        )

    async def register_handoff(
        self,
        state: ExecutionState,
        *,
        question: str,
        task_title: str,
        assignee_queue_slug: str,
        handoff_mode: HandoffMode,
        command: HitlHandoffCommand,
    ) -> tuple[UUID, str]:
        return await self._service.register_handoff(
            state,
            question=question,
            task_title=task_title,
            assignee_queue_slug=assignee_queue_slug,
            handoff_mode=handoff_mode,
            command=command,
        )
