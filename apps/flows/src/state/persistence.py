"""
State persistence - управление состоянием сессий.

Объединяет функциональность store.py и manager.py.
"""

import json
import uuid
from typing import TYPE_CHECKING, Any

from a2a.types import Message, Part, Role, TextPart

from apps.flows.src.runtime.message_metadata import MESSAGE_SOURCE_CHANNEL
from core.context import get_context
from core.logging import get_logger
from core.state import TERMINAL_TASK_STATES, ExecutionState, ExecutionTaskState

if TYPE_CHECKING:
    from apps.flows.src.db import BaseStateRepository

logger = get_logger(__name__)

HOT_STATE_TTL_SECONDS = 7 * 24 * 60 * 60
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

    def __init__(
        self,
        state_repository: "BaseStateRepository",
        redis_client: Any,
    ):
        self._repository = state_repository
        self._redis = redis_client

    def _company_scope(self) -> str:
        context = get_context()
        if not context or not context.active_company:
            raise ValueError("StateManager requires active company context for Redis state")
        company = context.active_company
        return company.subdomain or company.company_id

    def _state_key(self, session_id: str) -> str:
        return f"flows:state:{self._company_scope()}:session:{session_id}"

    def _index_keys(self, state: ExecutionState) -> tuple[str, str]:
        scope = self._company_scope()
        flow_id = state.session_flow_id
        return (
            f"flows:state:{scope}:task:{flow_id}:{state.task_id}",
            f"flows:state:{scope}:context:{flow_id}:{state.context_id}",
        )

    @staticmethod
    def _dump_state(session_id: str, state: ExecutionState) -> str:
        payload = state.model_dump(mode="json", exclude_none=False)
        payload.pop("flow_config", None)
        return json.dumps(
            {"session_id": session_id, "data": payload},
            ensure_ascii=False,
            separators=(",", ":"),
        )

    @staticmethod
    def _load_state(raw: str) -> ExecutionState:
        payload = json.loads(raw)
        data = payload.get("data", payload)
        if isinstance(data, dict):
            fc = data.pop("flow_config", None)
            if (
                isinstance(fc, dict)
                and fc.get("version")
                and not data.get("flow_config_version")
            ):
                data["flow_config_version"] = str(fc["version"])
        return ExecutionState.model_validate(data)

    async def _get_hot_state(self, session_id: str) -> ExecutionState | None:
        raw = await self._redis.get(self._state_key(session_id))
        if not raw:
            return None
        return self._load_state(raw)

    async def _save_hot_state(self, session_id: str, state: ExecutionState) -> bool:
        raw = self._dump_state(session_id, state)
        ok = await self._redis.set(
            self._state_key(session_id),
            raw,
            ttl=HOT_STATE_TTL_SECONDS,
        )
        if not ok:
            raise RuntimeError("Redis hot-state save failed")

        task_key, context_key = self._index_keys(state)
        await self._redis.set(task_key, session_id, ttl=HOT_STATE_TTL_SECONDS)
        await self._redis.set(context_key, session_id, ttl=HOT_STATE_TTL_SECONDS)
        return True

    async def _delete_hot_state(
        self,
        session_id: str,
        state: ExecutionState | None = None,
    ) -> None:
        keys = [self._state_key(session_id)]
        hot_state = await self._get_hot_state(session_id)
        if hot_state is not None:
            keys.extend(self._index_keys(hot_state))
        if state is not None:
            keys.extend(self._index_keys(state))
        await self._redis.delete(*dict.fromkeys(keys))

    async def get_state(self, session_id: str) -> ExecutionState | None:
        """Получает hot state из Redis, terminal snapshot — из БД."""
        hot = await self._get_hot_state(session_id)
        if hot is not None:
            return hot
        terminal = await self._repository.get(session_id)
        if terminal is not None and not terminal.terminal_task_state:
            return None
        return terminal

    async def save_state(
        self, session_id: str, state: ExecutionState | dict[str, Any]
    ) -> bool:
        """Сохраняет промежуточный state в Redis."""
        st = ExecutionState.model_validate(state) if isinstance(state, dict) else state
        return await self._save_hot_state(session_id, st)

    async def save_terminal_state(
        self,
        session_id: str,
        state: ExecutionState | dict[str, Any],
        terminal_task_state: ExecutionTaskState,
        *,
        error: str | None = None,
    ) -> bool:
        """Фиксирует terminal snapshot в БД и убирает hot state из Redis."""
        if terminal_task_state not in TERMINAL_TASK_STATES:
            raise ValueError(f"Unknown terminal task state: {terminal_task_state!r}")
        st = ExecutionState.model_validate(state) if isinstance(state, dict) else state
        st.terminal_task_state = terminal_task_state
        st.terminal_task_error = error
        ok = await self._repository.set(session_id, st)
        await self._delete_hot_state(session_id, st)
        return ok

    async def delete_state(self, session_id: str) -> bool:
        """Удаляет state сессии."""
        state = await self._get_hot_state(session_id)
        if state is None:
            state = await self._repository.get(session_id)
        await self._delete_hot_state(session_id, state)
        return await self._repository.delete(session_id)

    async def resolve_session_id_by_flow_and_identifier(
        self, flow_id: str, lookup_id: str
    ) -> str | None:
        """Находит ``session_id`` (`flow_id:context_id`) по ``task_id`` или ``context_id``."""
        scope = self._company_scope()
        for key in (
            f"flows:state:{scope}:task:{flow_id}:{lookup_id}",
            f"flows:state:{scope}:context:{flow_id}:{lookup_id}",
        ):
            session_id = await self._redis.get(key)
            if session_id:
                return session_id
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
