"""
InterruptManager - управление interrupt/resume для вложенных вызовов.

Работает с любой вложенностью делегирования в другой flow (tool с flow_id / skill_id — исполняется как вложенный subflow):
- flow → нода → subflow → … → ask_user
- flow → граф из нод → нода, внутри которой снова subflow → ask_user
- цепочка из нескольких subflow: каждый уровень — свой снимок в nested_states и сегмент в interrupt_path

При interrupt сохраняется путь (interrupt_path) к месту прерывания.
При resume ответ доставляется по этому пути.

Zero-Guess: все методы работают с ExecutionState, не Dict.
"""

import uuid
from typing import Any, Dict, List, Optional

from a2a.types import Message, Part, Role, TextPart

from core.logging import get_logger
from core.state import (
    ExecutionState,
    InterruptData,
    InterruptPathItem,
)

logger = get_logger(__name__)


def _new_user_message(content: str, task_id: Optional[str] = None) -> Message:
    """Создаёт A2A Message от пользователя."""
    return Message(
        messageId=str(uuid.uuid4()),
        role=Role.user,
        parts=[Part(root=TextPart(text=content))],
        taskId=task_id,
    )


class InterruptManager:
    """
    Управляет interrupt/resume для вложенных вызовов.

    Структура ExecutionState:
    - interrupt: InterruptData с вопросом и контекстом
    - interrupt_path: List[InterruptPathItem] путь к месту прерывания
    - nested_states: Dict[str, Dict] снимки state вложенных subflow (по nested_id)
    """

    @staticmethod
    def save_nested_state(
        parent_state: ExecutionState, nested_id: str, nested_state: ExecutionState
    ) -> None:
        """
        Сохраняет state вложенного вызова в родительский state.

        Args:
            parent_state: State родителя
            nested_id: ID вложенного вызова (flow_id, node_id, etc)
            nested_state: State вложенного вызова
        """
        from apps.flows.src.state.execution_state import NestedStateData
        
        saved = NestedStateData(
            messages=list(nested_state.messages),
            interrupt_path=list(nested_state.interrupt_path),
            nested_states=dict(nested_state.nested_states),
        )

        parent_state.nested_states[nested_id] = saved
        logger.debug(f"save_nested_state: {nested_id}, messages: {len(saved.messages)}")

    @staticmethod
    def load_nested_state(
        parent_state: ExecutionState, nested_id: str
    ) -> ExecutionState:
        """
        Загружает state вложенного вызова из родительского state.

        Args:
            parent_state: State родителя
            nested_id: ID вложенного вызова

        Returns:
            ExecutionState вложенного вызова
        """
        from apps.flows.src.state.execution_state import NestedStateData
        
        saved = parent_state.nested_states.get(nested_id)
        
        if saved is None:
            saved = NestedStateData()
        elif isinstance(saved, dict):
            saved = NestedStateData.model_validate(saved)

        result = ExecutionState(
            task_id=parent_state.task_id,
            context_id=parent_state.context_id,
            session_id=parent_state.session_id,
            user_id=parent_state.user_id,
            messages=list(saved.messages),
            variables=parent_state.variables.copy(),
            interrupt_path=list(saved.interrupt_path),
            nested_states=dict(saved.nested_states),
        )

        logger.debug(f"load_nested_state: {nested_id}, messages: {len(result.messages)}")
        return result

    @staticmethod
    def push_interrupt_path(state: ExecutionState, call_info: InterruptPathItem) -> None:
        """
        Добавляет элемент в НАЧАЛО пути interrupt.
        
        При interrupt исключение пробрасывается снизу вверх, каждый уровень
        добавляет себя. При resume мы идём сверху вниз, поэтому внешние
        уровни должны быть в начале списка.

        Args:
            state: Текущий ExecutionState
            call_info: Информация о вызове
        """
        state.interrupt_path.insert(0, call_info)

    @staticmethod
    def pop_interrupt_path(state: ExecutionState) -> Optional[InterruptPathItem]:
        """
        Извлекает последний элемент из пути interrupt.

        Args:
            state: Текущий ExecutionState

        Returns:
            InterruptPathItem или None
        """
        if state.interrupt_path:
            return state.interrupt_path.pop()
        return None

    @staticmethod
    def get_interrupt_path(state: ExecutionState) -> List[InterruptPathItem]:
        """Возвращает текущий путь interrupt."""
        result = []
        for item in state.interrupt_path:
            if isinstance(item, InterruptPathItem):
                result.append(item)
            elif isinstance(item, dict):
                result.append(InterruptPathItem.model_validate(item))
        return result

    @staticmethod
    def clear_interrupt_path(state: ExecutionState) -> None:
        """Очищает путь interrupt."""
        state.interrupt_path = []

    @staticmethod
    def set_interrupt(
        state: ExecutionState,
        question: str,
        tool_call: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Устанавливает interrupt в state.

        Args:
            state: Текущий ExecutionState
            question: Вопрос для пользователя
            tool_call: Информация о tool_call который вызвал interrupt
        """
        context = {
            "tool_call": tool_call,
            "path": [item.model_dump() for item in state.interrupt_path],
            "task_id": state.task_id,
        }
        state.interrupt = InterruptData(question=question, context=context)

    @staticmethod
    def get_interrupt(state: ExecutionState) -> Optional[InterruptData]:
        """Возвращает информацию об interrupt."""
        return state.interrupt

    @staticmethod
    def clear_interrupt(state: ExecutionState) -> None:
        """Очищает interrupt."""
        state.interrupt = None

    @staticmethod
    def is_resume_for_nested(state: ExecutionState, nested_id: str) -> bool:
        """
        Проверяет нужно ли resume передать в вложенный вызов.

        Args:
            state: Текущий ExecutionState
            nested_id: ID вложенного вызова

        Returns:
            True если первый элемент пути соответствует nested_id
        """
        if state.interrupt_path and len(state.interrupt_path) > 0:
            return state.interrupt_path[0].id == nested_id
        return False

    @staticmethod
    def prepare_nested_resume(
        parent_state: ExecutionState, nested_id: str, user_answer: str
    ) -> ExecutionState:
        """
        Подготавливает state для resume вложенного вызова.

        Args:
            parent_state: State родителя
            nested_id: ID вложенного вызова
            user_answer: Ответ пользователя

        Returns:
            ExecutionState для вложенного вызова с добавленным ответом
        """
        nested_state = InterruptManager.load_nested_state(parent_state, nested_id)

        nested_state.messages.append(_new_user_message(user_answer, nested_state.task_id))

        if parent_state.interrupt_path:
            nested_state.interrupt_path = parent_state.interrupt_path[1:]

        logger.info(f"Подготовлен resume для {nested_id}, ответ: {user_answer[:50]}...")
        return nested_state
