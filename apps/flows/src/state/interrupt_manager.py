"""
InterruptManager - управление interrupt/resume для nested node-as-tool вызовов.

`FlowNode` исполняется как отдельный durable child workflow и не использует
`nested_states`. Этот менеджер остается только для изолированного `llm_node`,
вызванного как tool через `NodeWrapperTool`: каждый уровень хранит typed snapshot
в `nested_states` и сегмент в `interrupt_path`.

При interrupt сохраняется путь (interrupt_path) к месту прерывания.
При resume ответ доставляется по этому пути.

Zero-Guess: все методы работают с ExecutionState, не Dict.
"""

from uuid import UUID

from apps.flows.src.runtime.a2a_messages import build_user_message
from core.clients.llm import LLMToolCall
from core.logging import get_logger
from core.state import ExecutionState, InterruptData, InterruptPathItem, NestedStateData
from core.state.interrupt import InterruptBody, InterruptSystemContext

logger = get_logger(__name__)


class InterruptManager:
    """
    Управляет interrupt/resume для nested node-as-tool вызовов.

    Структура ExecutionState:
    - interrupt: InterruptData (body + system)
    - interrupt_path: List[InterruptPathItem] путь к месту прерывания
    - nested_states: Dict[str, NestedStateData] снимки isolated llm_node tool state
    """

    @staticmethod
    def save_nested_state(
        parent_state: ExecutionState, nested_id: str, nested_state: ExecutionState
    ) -> None:
        """
        Сохраняет state вложенного вызова в родительский state.

        Аргументы:
            parent_state: State родителя
            nested_id: ID вложенного вызова (flow_id, node_id, etc)
            nested_state: State вложенного вызова
        """
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

        Аргументы:
            parent_state: State родителя
            nested_id: ID вложенного вызова

        Возвращает:
            ExecutionState вложенного вызова
        """
        saved = parent_state.nested_states.get(nested_id)

        if saved is None:
            raise ValueError(
                f"load_nested_state: нет снимка nested_states для nested_id={nested_id!r}"
            )
        if isinstance(saved, dict):
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

        Аргументы:
            state: Текущий ExecutionState
            call_info: Информация о вызове
        """
        state.interrupt_path.insert(0, call_info)

    @staticmethod
    def pop_interrupt_path(state: ExecutionState) -> InterruptPathItem | None:
        """
        Извлекает последний элемент из пути interrupt.

        Аргументы:
            state: Текущий ExecutionState

        Возвращает:
            InterruptPathItem или None
        """
        if state.interrupt_path:
            return state.interrupt_path.pop()
        return None

    @staticmethod
    def get_interrupt_path(state: ExecutionState) -> list[InterruptPathItem]:
        """Возвращает текущий путь interrupt."""
        return list(state.interrupt_path)

    @staticmethod
    def clear_interrupt_path(state: ExecutionState) -> None:
        """Очищает путь interrupt."""
        state.interrupt_path = []

    @staticmethod
    def apply_interrupt(
        state: ExecutionState,
        body: InterruptBody,
        tool_call: LLMToolCall | None = None,
        correlation_id: UUID | None = None,
    ) -> None:
        """
        Единая запись interrupt: тело (union) + системный конверт из текущего state.
        """
        system = InterruptSystemContext(
            tool_call=tool_call,
            path=[item.model_dump(mode="json") for item in state.interrupt_path],
            task_id=state.task_id,
        )
        state.interrupt = InterruptData(
            body=body, system=system, correlation_id=correlation_id
        )

    @staticmethod
    def enrich_system_from_channel(
        state: ExecutionState,
        *,
        context_id: str,
        task_id: str,
    ) -> None:
        """Дополняет system после run (канал передаёт актуальные task_id/context_id)."""
        if state.interrupt is None:
            raise ValueError("enrich_system_from_channel: interrupt отсутствует")
        ir = state.interrupt
        new_system = ir.system.model_copy(
            update={"context_id": context_id, "task_id": task_id}
        )
        state.interrupt = ir.model_copy(update={"system": new_system})

    @staticmethod
    def get_interrupt(state: ExecutionState) -> InterruptData | None:
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

        Аргументы:
            state: Текущий ExecutionState
            nested_id: ID вложенного вызова

        Возвращает:
            True если первый элемент пути соответствует nested_id
        """
        if state.interrupt_path and len(state.interrupt_path) > 0:
            return state.interrupt_path[0].node_id == nested_id
        return False

    @staticmethod
    def prepare_nested_resume(
        parent_state: ExecutionState, nested_id: str, user_answer: str
    ) -> ExecutionState:
        """
        Подготавливает state для resume вложенного вызова.

        Аргументы:
            parent_state: State родителя
            nested_id: ID вложенного вызова
            user_answer: Ответ пользователя

        Возвращает:
            ExecutionState для вложенного вызова с добавленным ответом
        """
        nested_state = InterruptManager.load_nested_state(parent_state, nested_id)

        nested_state.messages.append(
            build_user_message(
                user_answer,
                nested_id,
                context_id=nested_state.context_id,
                task_id=nested_state.task_id,
            )
        )

        if parent_state.interrupt_path:
            nested_state.interrupt_path = parent_state.interrupt_path[1:]

        logger.info(f"Подготовлен resume для {nested_id}, ответ: {user_answer[:50]}...")
        return nested_state
