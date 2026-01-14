"""
State persistence - управление состоянием сессий.

Объединяет функциональность store.py и manager.py.
"""

import uuid
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from a2a.types import Message, Part, Role, TextPart

from core.state import ExecutionState
from core.logging import get_logger

if TYPE_CHECKING:
    from apps.agents.src.db import BaseStateRepository

logger = get_logger(__name__)


def create_initial_state(
    task_id: str,
    context_id: str,
    user_id: str,
    session_id: str,
    content: str = "",
    skill_id: str = "default",
) -> ExecutionState:
    """Создает начальный ExecutionState."""
    return ExecutionState(
        task_id=task_id,
        context_id=context_id,
        user_id=user_id,
        session_id=session_id,
        content=content,
        skill_id=skill_id,
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

    async def get_state(self, session_id: str) -> Optional[ExecutionState]:
        """Получает state сессии из БД."""
        return await self._repository.get(session_id)

    async def get_state_for_update(
        self, session_id: str, conn: Any = None
    ) -> Optional[ExecutionState]:
        """Получает state с блокировкой."""
        return await self._repository.get_for_update(session_id, conn)

    async def save_state(self, session_id: str, state: ExecutionState) -> bool:
        """Сохраняет state сессии в БД."""
        return await self._repository.set(session_id, state)

    async def save_state_in_transaction(
        self, session_id: str, state: ExecutionState, conn: Any = None
    ) -> bool:
        """Сохраняет state в рамках транзакции."""
        return await self._repository.set_in_transaction(session_id, state, conn)

    async def delete_state(self, session_id: str) -> bool:
        """Удаляет state сессии."""
        return await self._repository.delete(session_id)
    
    def get_messages(self, state: ExecutionState) -> List[Message]:
        """Получает историю сообщений из ExecutionState."""
        return list(state.messages)
    
    def add_message(self, state: ExecutionState, message: Message) -> None:
        """Добавляет Message в ExecutionState."""
        state.messages.append(message)
    
    def add_user_message(self, state: ExecutionState, content: str) -> None:
        """Добавляет сообщение пользователя в ExecutionState."""
        message = Message(
            messageId=str(uuid.uuid4()),
            role=Role.user,
            parts=[Part(root=TextPart(text=content))],
            taskId=state.task_id,
        )
        self.add_message(state, message)
    
    def add_agent_message(self, state: ExecutionState, content: str) -> None:
        """Добавляет сообщение агента в ExecutionState."""
        message = Message(
            messageId=str(uuid.uuid4()),
            role=Role.agent,
            parts=[Part(root=TextPart(text=content))],
            taskId=state.task_id,
        )
        self.add_message(state, message)

