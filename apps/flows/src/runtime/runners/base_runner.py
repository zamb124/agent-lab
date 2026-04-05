"""
Базовый runner для LlmNode.

Zero-Guess: все методы работают с ExecutionState.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Dict, List

from a2a.types import Message, Part, Role, TextPart

from apps.flows.src.runtime.a2a_messages import build_user_message
from core.logging import get_logger
from apps.flows.src.models import NodeConfig, ReactLoopMode
from apps.flows.src.models.enums import ReactToolRole

if TYPE_CHECKING:
    from core.state import ExecutionState

logger = get_logger(__name__)


class BaseLlmNodeRunner(ABC):
    """
    Базовый класс для runner'ов LlmNode.
    Runner отвечает за логику выполнения ReAct цикла.
    """

    def __init__(self, node_config: NodeConfig, tools: List[Any], llm, prompt: str, llm_node=None):
        self.node_config = node_config
        self.tools = list(tools) if tools else []
        self.llm = llm
        self.prompt = prompt
        self.llm_node = llm_node
        self.auto_exit_tool_added = False

        self._inject_exit_tool()

    def _inject_exit_tool(self) -> None:
        """Добавляет exit_tool если режим explicit и tool отсутствует."""
        if not self.node_config:
            return

        react_config = self.node_config.react
        if not react_config:
            return

        if react_config.loop_mode != ReactLoopMode.EXPLICIT:
            return

        existing_exit = self._find_tool_by_react_role(ReactToolRole.EXIT)
        if existing_exit:
            logger.debug(f"[node:{self.node_config.name}] exit tool '{existing_exit.name}' already exists")
            return

        exit_tool_name = react_config.exit_tool
        if any(getattr(t, "name", None) == exit_tool_name for t in self.tools):
            logger.debug(f"[node:{self.node_config.name}] exit tool '{exit_tool_name}' already exists (by name)")
            return

        if exit_tool_name == "finish":
            from apps.flows.tools import finish
            self.tools.append(finish)
            self.auto_exit_tool_added = True
            logger.info(f"[node:{self.node_config.name}] finish tool auto-injected for explicit mode")
        else:
            logger.warning(
                f"[node:{self.node_config.name}] EXPLICIT mode requires exit_tool '{exit_tool_name}' "
                f"but it's not in tools and is not 'finish'. The node may not be able to exit."
            )

    def _find_tool_by_react_role(self, react_role: ReactToolRole):
        for tool in self.tools:
            if getattr(tool, "react_role", None) == react_role:
                return tool
        return None

    def _get_reason_tool_name(self) -> str | None:
        tool = self._find_tool_by_react_role(ReactToolRole.REASON)
        return getattr(tool, "name", None) if tool else None

    def _get_exit_tool_name(self) -> str | None:
        tool = self._find_tool_by_react_role(ReactToolRole.EXIT)
        return getattr(tool, "name", None) if tool else None

    @abstractmethod
    async def run(self, input_data: Dict[str, Any], state: "ExecutionState") -> Dict[str, Any]:
        """
        Выполняет LlmNode.

        Args:
            input_data: Входные данные (messages, etc)
            state: ExecutionState

        Returns:
            Результат выполнения
        """
        pass

    def get_variables(self, state: "ExecutionState") -> Dict[str, Any]:
        """Получает переменные из state."""
        return dict(state.variables or {})

    def get_messages(self, state: "ExecutionState") -> List[Message]:
        """Получает историю сообщений."""
        return list(state.messages)

    def add_message(self, state: "ExecutionState", message: Message) -> None:
        """Добавляет Message в state."""
        state.messages.append(message)

    def add_user_message(self, state: "ExecutionState", content: str) -> None:
        """Добавляет сообщение пользователя."""
        if not self.node_config:
            raise ValueError("add_user_message: node_config required")
        message = build_user_message(
            content,
            self.node_config.node_id,
            context_id=state.context_id,
            task_id=state.task_id,
        )
        self.add_message(state, message)

    def add_llm_node_message(
        self,
        state: "ExecutionState",
        content: str,
        tool_calls: List[Dict[str, Any]] | None = None,
    ) -> None:
        """Добавляет сообщение LlmNode."""
        if not self.node_config:
            raise ValueError("add_llm_node_message: node_config required")
        meta: Dict[str, Any] = {"node_id": self.node_config.node_id}
        if tool_calls:
            meta["tool_calls"] = tool_calls
        message = Message(
            messageId=str(uuid.uuid4()),
            role=Role.agent,
            parts=[Part(root=TextPart(text=content))],
            metadata=meta,
            taskId=state.task_id,
        )
        self.add_message(state, message)

    def add_tool_message(self, state: "ExecutionState", tool_call_id: str, content: str) -> None:
        """Добавляет сообщение от tool."""
        if not self.node_config:
            raise ValueError("add_tool_message: node_config required")
        message = Message(
            messageId=str(uuid.uuid4()),
            role=Role.agent,
            parts=[Part(root=TextPart(text=content))],
            metadata={
                "tool_call_id": tool_call_id,
                "node_id": self.node_config.node_id,
            },
            taskId=state.task_id,
        )
        self.add_message(state, message)
