"""
Базовый runner для LlmNode.

Zero-Guess: все методы работают с ExecutionState.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator, Sequence
from typing import TYPE_CHECKING, Literal, Protocol

from a2a.types import Message, Part
from a2a.types.a2a_pb2 import ROLE_AGENT

from apps.flows.src.models import NodeConfig, ReactLoopMode
from apps.flows.src.models.enums import ReactToolRole
from apps.flows.src.runtime.a2a_messages import build_user_message
from apps.flows.src.runtime.message_author import build_flow_message_author
from apps.flows.src.streaming.base import BaseEmitter, StreamEvent
from apps.flows.src.tools.base import BaseTool
from apps.flows.tools.misc.finish_tool import finish
from core.a2a import struct_from_mapping
from core.clients.llm import LLMClient, LLMToolCall, MockLLM
from core.logging import get_logger
from core.types import JsonObject, require_json_object

if TYPE_CHECKING:
    from apps.flows.src.state import ExecutionState

logger = get_logger(__name__)


class LlmNodeRunnerHost(Protocol):
    """Структурный контракт, который runner ожидает от владеющего LlmNode."""

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
            logger.debug("flows.runner.exit_tool_exists", node_name=self.node_config.name, tool_name=existing_exit.name)
            return

        exit_tool_name = react_config.exit_tool
        if any(t.name == exit_tool_name for t in self.tools):
            logger.debug("flows.runner.exit_tool_name_exists", node_name=self.node_config.name, tool_name=exit_tool_name)
            return

        if exit_tool_name == "finish":
            self.tools.append(finish)
            self.auto_exit_tool_added = True
            logger.info("flows.runner.finish_tool_injected", node_name=self.node_config.name)
        else:
            logger.warning(
                "flows.runner.exit_tool_missing",
                node_name=self.node_config.name,
                exit_tool_name=exit_tool_name,
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

        Аргументы:
            input_data: Входные данные (messages, etc)
            state: ExecutionState

        Возвращает:
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
        meta: JsonObject = {
            "node_id": self.node_config.node_id,
            "author": build_flow_message_author(
                state,
                node_id=self.node_config.node_id,
            ),
        }
        if tool_calls:
            meta["tool_calls"] = [
                tool_call.model_dump(mode="json", exclude_none=True)
                for tool_call in tool_calls
            ]
        message = Message(
            message_id=str(uuid.uuid4()),
            role=ROLE_AGENT,
            parts=[Part(text=content)],
            metadata=struct_from_mapping(meta),
            task_id=state.task_id,
        )
        self.add_message(state, message)

    def add_tool_message(
        self,
        state: "ExecutionState",
        tool_call_id: str,
        content: str,
        *,
        extra_parts: Sequence[Part] | None = None,
    ) -> None:
        """Добавляет сообщение от tool (text + optional multimodal Parts)."""
        if not self.node_config:
            raise ValueError("add_tool_message: node_config required")
        parts: list[Part] = [Part(text=content)]
        if extra_parts:
            parts.extend(extra_parts)
        message = Message(
            message_id=str(uuid.uuid4()),
            role=ROLE_AGENT,
            parts=parts,
            metadata=struct_from_mapping(
                {
                    "tool_call_id": tool_call_id,
                    "node_id": self.node_config.node_id,
                    "author": build_flow_message_author(
                        state,
                        node_id=self.node_config.node_id,
                    ),
                }
            ),
            task_id=state.task_id,
        )
        self.add_message(state, message)
