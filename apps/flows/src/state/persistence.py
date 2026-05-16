"""
State persistence - управление состоянием сессий.

Объединяет функциональность store.py и manager.py.
"""

import uuid
from typing import TYPE_CHECKING, Any

from a2a.types import Message, Part, Role, TextPart

from apps.flows.src.runtime.message_metadata import MESSAGE_SOURCE_CHANNEL
from core.logging import get_logger
from core.state import ExecutionState

if TYPE_CHECKING:
    from apps.flows.src.db import BaseStateRepository

logger = get_logger(__name__)


def create_initial_state(
    task_id: str,
    context_id: str,
    user_id: str,
    session_id: str,
    content: str = "",
    branch_id: str = "default",
) -> ExecutionState:
    """Создает начальный ExecutionState."""
    return ExecutionState(
        task_id=task_id,
        context_id=context_id,
        user_id=user_id,
        session_id=session_id,
        content=content,
        branch_id=branch_id,
    )


# =============================================================================
# StateManager
# =============================================================================


class StateManager:
    """
    Менеджер состояния сессий.

    Работает с ExecutionState напрямую.
    Получается через container.state_manager.
    """

    def __init__(self, state_repository: "BaseStateRepository"):
        self._repository = state_repository

    async def get_state(self, session_id: str) -> ExecutionState | None:
        """Получает state сессии из БД."""
        return await self._repository.get(session_id)

    async def get_state_for_update(
        self, session_id: str, conn: Any
    ) -> ExecutionState | None:
        """Получает state с блокировкой."""
        return await self._repository.get_for_update(session_id, conn)

    async def save_state(
        self, session_id: str, state: ExecutionState | dict[str, Any]
    ) -> bool:
        """Сохраняет state сессии в БД."""
        st = ExecutionState.model_validate(state) if isinstance(state, dict) else state
        return await self._repository.set(session_id, st)

    async def save_state_in_transaction(
        self,
        session_id: str,
        state: ExecutionState | dict[str, Any],
        conn: Any,
    ) -> bool:
        """Сохраняет state в рамках транзакции."""
        st = ExecutionState.model_validate(state) if isinstance(state, dict) else state
        return await self._repository.set_in_transaction(session_id, st, conn)

    async def delete_state(self, session_id: str) -> bool:
        """Удаляет state сессии."""
        return await self._repository.delete(session_id)

    async def resolve_session_id_by_flow_and_identifier(
        self, flow_id: str, lookup_id: str
    ) -> str | None:
        """Находит ``session_id`` (`flow_id:context_id`) по ``task_id`` или ``context_id``."""
        return await self._repository.resolve_session_id_by_flow_and_identifier(
            flow_id, lookup_id
        )

    async def get_messages(self, state: ExecutionState) -> list[Message]:
        """Получает историю сообщений из ExecutionState."""
        return list(state.messages)

    def add_message(self, state: ExecutionState, message: Message) -> None:
        """Добавляет Message в ExecutionState."""
        state.messages.append(message)

    def add_user_message(self, state: ExecutionState, content: str) -> None:
        """Добавляет сообщение пользователя в ExecutionState."""
        message = Message(
            message_id=str(uuid.uuid4()),
            role=Role.user,
            parts=[Part(root=TextPart(text=content))],
            task_id=state.task_id,
            metadata={"node_id": MESSAGE_SOURCE_CHANNEL},
        )
        self.add_message(state, message)

    def add_agent_message(self, state: ExecutionState, content: str) -> None:
        """Добавляет сообщение агента в ExecutionState."""
        message = Message(
            message_id=str(uuid.uuid4()),
            role=Role.agent,
            parts=[Part(root=TextPart(text=content))],
            task_id=state.task_id,
            metadata={"node_id": MESSAGE_SOURCE_CHANNEL},
        )
        self.add_message(state, message)
