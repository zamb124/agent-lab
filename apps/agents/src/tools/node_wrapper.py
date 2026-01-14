"""
NodeAsToolWrapper - обёртка ноды для использования как tool.

Zero-Guess: все методы работают с ExecutionState.
AgentInterrupt из субноды пробрасывается наверх.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, Optional, Union

from pydantic import BaseModel, Field

from apps.agents.src.agent.exceptions import AgentInterrupt
from apps.agents.src.agent.nodes import create_node
from apps.agents.src.container import get_container
from core.logging import get_logger
from apps.agents.src.mock import get_mock_for_agent
from apps.agents.src.models import NodeConfig
from apps.agents.src.models.enums import NodeType
from apps.agents.src.state.interrupt_manager import InterruptManager
from core.state import ExecutionState, InterruptPathItem
from apps.agents.src.tools.base import BaseTool

if TYPE_CHECKING:
    from apps.agents.src.agent.nodes import BaseNode

logger = get_logger(__name__)


class NodeWrapperArgs(BaseModel):
    """Аргументы для вызова ноды."""

    query: str = Field(description="Запрос для ноды")


class NodeAsToolWrapper(BaseTool):
    """
    Обёртка над любой нодой для использования как tool.

    Поддерживает все типы нод:
    - react_node: LLM агент с ReAct циклом
    - function: Python функция
    - tool: вложенный tool
    """

    args_schema = NodeWrapperArgs

    def __init__(
        self, 
        node_config: Union[NodeConfig, Dict[str, Any]],
        tool_registry: Optional[Any] = None
    ):
        """
        Args:
            node_config: Конфигурация ноды (NodeConfig или dict)
            tool_registry: Опциональный реестр для создания вложенных tools
        """
        if isinstance(node_config, dict):
            self._raw_config = node_config
            node_type = node_config.get("type")
            if not node_type:
                raise ValueError(f"Node config requires 'type' field: {node_config}")
            node_id = node_config.get("tool_id") or node_config.get("node_id")
            if not node_id:
                raise ValueError(f"Node config requires 'tool_id' or 'node_id' field: {node_config}")
            
            self.node_config = NodeConfig(
                node_id=node_id,
                name=node_config.get("name", node_id),
                type=node_type,
                description=node_config.get("description"),
                prompt=node_config.get("prompt"),
                tools=node_config.get("tools", []),
                code=node_config.get("code"),
                tags=node_config.get("tags") or [],
            )
        else:
            self._raw_config = None
            self.node_config = node_config
        
        self._tool_registry = tool_registry
        self.name = self.node_config.node_id
        self.description = self.node_config.description or f"Вызов ноды {self.node_config.name}"
        self.tags = self.node_config.tags or [self.node_config.type]
        self._node: Optional["BaseNode"] = None

    async def _get_node(self) -> "BaseNode":
        """Lazy создание ноды нужного типа."""
        if self._node is None:
            if self._raw_config:
                node_dict = dict(self._raw_config)
            else:
                tools = []
                if self.node_config.tools:
                    for t in self.node_config.tools:
                        if hasattr(t, "model_dump"):
                            tools.append(t.model_dump())
                        elif isinstance(t, dict):
                            tools.append(t)
                        else:
                            tools.append(t)
                
                node_dict = {
                    "type": self.node_config.type,
                    "prompt": self.node_config.prompt,
                    "tools": tools,
                    "llm": self.node_config.llm_override.model_dump() if self.node_config.llm_override else {},
                    "code": self.node_config.code,
                    "react": self.node_config.react.model_dump() if self.node_config.react else None,
                }

            self._node = await create_node(self.node_config.node_id, node_dict)

        return self._node

    async def _run_impl(self, args: Dict[str, Any], state: ExecutionState) -> Any:
        """
        Вызывает субноду.

        Args:
            args: {"query": "запрос для субноды"}
            state: ExecutionState родительской ноды

        Returns:
            Ответ субноды

        Raises:
            AgentInterrupt: Если субнода запрашивает input от пользователя
        """
        node_id = self.node_config.node_id
        node_type = self.node_config.type
        
        mock_result = get_mock_for_agent(state, node_id)
        if mock_result is not None:
            logger.info(f"[subnode:{node_id}] using mock response")
            return mock_result
        
        query = args.get("query", "")
        node = await self._get_node()

        logger.info(f"[subnode:{node_id}] run: type={node_type}, query={query[:50]}...")

        if node_type == NodeType.REACT_NODE.value:
            return await self._execute_react_node(node, node_id, query, state)
        
        return await self._execute_simple_node(node, node_id, query, state)

    async def _execute_react_node(
        self, node: "BaseNode", node_id: str, query: str, state: ExecutionState
    ) -> Any:
        """Выполняет react_node с поддержкой interrupt."""
        nested_state = InterruptManager.load_nested_state(state, node_id)
        
        nested_state.content = query
        nested_state.variables = state.variables.copy()
        nested_state.files = list(state.files)
        
        has_interrupt_path = bool(nested_state.interrupt_path)

        logger.info(
            f"[subnode:{node_id}] Вызов: {self.node_config.name}, "
            f"files={len(nested_state.files)}, "
            f"resume={has_interrupt_path}, "
            f"messages={len(nested_state.messages)}"
        )

        try:
            result = await node.run(nested_state)

            InterruptManager.save_nested_state(state, node_id, nested_state)
            
            response = result.response if isinstance(result, ExecutionState) else str(result)
            logger.info(f"[subnode:{node_id}] Завершил: {response[:100] if response else ''}...")
            return response

        except AgentInterrupt as e:
            InterruptManager.save_nested_state(state, node_id, nested_state)
            
            # Копируем interrupt_path из nested_state в parent state
            for item in nested_state.interrupt_path:
                state.interrupt_path.append(item)
            
            InterruptManager.push_interrupt_path(
                state,
                InterruptPathItem(type="react_node", id=node_id),
            )
            raise

    async def _execute_simple_node(
        self, node: "BaseNode", node_id: str, query: str, state: ExecutionState
    ) -> Any:
        """Выполняет простую ноду (function, tool, etc)."""
        exec_state = ExecutionState(
            task_id=state.task_id,
            context_id=state.context_id,
            session_id=state.session_id,
            user_id=state.user_id,
            content=query,
            variables=state.variables.copy(),
        )

        result = await node.run(exec_state)

        if isinstance(result, ExecutionState):
            return result.response or str(result.model_dump(exclude_none=False))
        if isinstance(result, dict):
            return result.get("response", result.get("result", str(result)))
        return str(result)

    def __repr__(self) -> str:
        return f"NodeAsToolWrapper(node_id={self.node_config.node_id}, type={self.node_config.type})"
