"""
Базовый runner для LlmNode.

Zero-Guess: все методы работают с ExecutionState.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Literal, Protocol

from a2a.types import Message, Part, Role, TextPart

from apps.flows.src.models import NodeConfig, ReactLoopMode
from apps.flows.src.models.enums import ReactToolRole
from apps.flows.src.runtime.a2a_messages import build_user_message
from apps.flows.src.streaming.base import BaseEmitter, StreamEvent
from apps.flows.src.tools.base import BaseTool
from apps.flows.tools.finish_tool import finish
from core.clients.llm import LLMClient, LLMToolCall, MockLLM
from core.logging import get_logger
from core.types import JsonObject, require_json_object

if TYPE_CHECKING:
    from core.state import ExecutionState

logger = get_logger(__name__)


class LlmNodeRunnerHost(Protocol):
    """Structural contract the runner needs from its owning LlmNode."""

    messages_filter: Literal["all", "own"] | list[str]

    def get_filtered_messages(self, state: ExecutionState) -> list[Message]: ...

    async def before_prompt_render(
        self,
        prompt_template: str,
        state: ExecutionState,
        variables: JsonObject,
    ) -> tuple[str, JsonObject]: ...

    async def after_prompt_render(
        self,
        rendered_prompt: str,
        state: ExecutionState,
    ) -> str: ...


class BaseLlmNodeRunner(ABC):
    """
    Базовый класс для runner'ов LlmNode.
    Runner отвечает за логику выполнения ReAct цикла.
    """

    def __init__(
        self,
        node_config: NodeConfig,
        tools: list[BaseTool],
        llm: LLMClient | MockLLM | None,
        prompt: str,
        llm_node: LlmNodeRunnerHost | None = None,
    ):
        self.node_config: NodeConfig = node_config
        self.tools: list[BaseTool] = list(tools) if tools else []
        self.llm: LLMClient | MockLLM | None = llm
        self.prompt: str = prompt
        self.llm_node: LlmNodeRunnerHost | None = llm_node
        self.auto_exit_tool_added: bool = False

        self._inject_exit_tool()

    def _inject_exit_tool(self) -> None:
        """Добавляет exit_tool если режим explicit и tool отсутствует."""
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
        if any(t.name == exit_tool_name for t in self.tools):
            logger.debug(f"[node:{self.node_config.name}] exit tool '{exit_tool_name}' already exists (by name)")
            return

        if exit_tool_name == "finish":
            self.tools.append(finish)
            self.auto_exit_tool_added = True
            logger.info(f"[node:{self.node_config.name}] finish tool auto-injected for explicit mode")
        else:
            logger.warning(
                f"[node:{self.node_config.name}] EXPLICIT mode requires exit_tool '{exit_tool_name}' "
                + "but it's not in tools and is not 'finish'. The node may not be able to exit."
            )

    def _find_tool_by_react_role(self, react_role: ReactToolRole) -> BaseTool | None:
        for tool in self.tools:
            if tool.react_role == react_role:
                return tool
        return None

    def _get_reason_tool_name(self) -> str | None:
        tool = self._find_tool_by_react_role(ReactToolRole.REASON)
        return tool.name if tool else None

    def _get_exit_tool_name(self) -> str | None:
        tool = self._find_tool_by_react_role(ReactToolRole.EXIT)
        return tool.name if tool else None

    @abstractmethod
    def run(
        self,
        input_data: JsonObject,
        state: "ExecutionState",
        emitter: BaseEmitter | None = None,
    ) -> AsyncGenerator[StreamEvent, None]:
        """
        Выполняет LlmNode.

        Args:
            input_data: Входные данные (messages, etc)
            state: ExecutionState

        Returns:
            Результат выполнения
        """
        raise NotImplementedError

    def get_variables(self, state: "ExecutionState") -> JsonObject:
        """Получает переменные из state."""
        return require_json_object(state.variables or {}, "state.variables")

    def get_messages(self, state: "ExecutionState") -> list[Message]:
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
        tool_calls: list[LLMToolCall] | None = None,
    ) -> None:
        """Добавляет сообщение LlmNode."""
        if not self.node_config:
            raise ValueError("add_llm_node_message: node_config required")
        meta: JsonObject = {"node_id": self.node_config.node_id}
        if tool_calls:
            meta["tool_calls"] = [
                tool_call.model_dump(mode="json", exclude_none=True)
                for tool_call in tool_calls
            ]
        message = Message(
            message_id=str(uuid.uuid4()),
            role=Role.agent,
            parts=[Part(root=TextPart(text=content))],
            metadata=meta,
            task_id=state.task_id,
        )
        self.add_message(state, message)

    def add_tool_message(self, state: "ExecutionState", tool_call_id: str, content: str) -> None:
        """Добавляет сообщение от tool."""
        if not self.node_config:
            raise ValueError("add_tool_message: node_config required")
        message = Message(
            message_id=str(uuid.uuid4()),
            role=Role.agent,
            parts=[Part(root=TextPart(text=content))],
            metadata={
                "tool_call_id": tool_call_id,
                "node_id": self.node_config.node_id,
            },
            task_id=state.task_id,
        )
        self.add_message(state, message)
