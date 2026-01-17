"""
NodeAsToolWrapper - обёртка ноды для использования как tool.

Простая логика:
1. Создает args_schema для LLM из конфига ноды
2. Записывает args в state
3. Вызывает node.run(state)

Нода сама берет нужные данные через input_mapping.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, Optional, Union

from pydantic import Field, create_model

from apps.agents.src.agent.nodes import create_node
from core.logging import get_logger
from apps.agents.src.mock import get_mock_for_agent
from apps.agents.src.models import NodeConfig
from apps.agents.src.tools.base import BaseTool, sanitize_tool_name
from core.state import ExecutionState

if TYPE_CHECKING:
    from apps.agents.src.agent.nodes import BaseNode

logger = get_logger(__name__)


def _build_pydantic_schema(args_schema_dict: Optional[Dict[str, Any]]) -> type:
    """Строит Pydantic модель из args_schema для OpenAI tools."""
    if not args_schema_dict:
        return create_model("EmptyArgs")
    
    fields = {}
    for name, schema in args_schema_dict.items():
        field_type = str
        type_str = schema.get("type", "string")
        
        if type_str == "integer":
            field_type = int
        elif type_str == "number":
            field_type = float
        elif type_str == "boolean":
            field_type = bool
        elif type_str == "array":
            field_type = list
        elif type_str == "object":
            field_type = dict
        
        description = schema.get("description", "")
        default = schema.get("default", ...)
        
        if default is ...:
            fields[name] = (field_type, Field(description=description))
        else:
            fields[name] = (field_type, Field(default=default, description=description))
    
    return create_model("DynamicArgs", **fields)


class NodeAsToolWrapper(BaseTool):
    """
    Обёртка над любой нодой для использования как tool.
    
    Поддерживает все типы нод.
    Args записываются в state, нода берет их через input_mapping.
    """

    def __init__(
        self, 
        node_config: Union[NodeConfig, Dict[str, Any]],
        tool_registry: Optional[Any] = None
    ):
        if isinstance(node_config, dict):
            self._raw_config = node_config
            node_type = node_config.get("type")
            if not node_type:
                raise ValueError(f"Node config requires 'type' field: {node_config}")
            node_id = node_config.get("tool_id") or node_config.get("node_id")
            if not node_id:
                raise ValueError(f"Node config requires 'tool_id' or 'node_id' field: {node_config}")
            
            self._args_schema_dict = node_config.get("args_schema")
            
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
            self._args_schema_dict = None
            self.node_config = node_config
        
        self.name = sanitize_tool_name(self.node_config.node_id)
        self.description = self.node_config.description or f"Вызов ноды {self.node_config.name}"
        self.tags = self.node_config.tags or [self.node_config.type]
        self._node: Optional["BaseNode"] = None
        
        self.args_schema = _build_pydantic_schema(self._args_schema_dict)

    async def _get_node(self) -> "BaseNode":
        """Lazy создание ноды."""
        if self._node is None:
            if self._raw_config:
                node_dict = dict(self._raw_config)
                node_dict.pop("tool_id", None)
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
        Записывает args в state и вызывает node.run(state).
        Нода сама возьмет данные через input_mapping.
        """
        node_id = self.node_config.node_id
        
        mock_result = get_mock_for_agent(state, node_id)
        if mock_result is not None:
            logger.info(f"[wrapper:{node_id}] mock response")
            return mock_result
        
        # Записываем args в state
        for key, value in args.items():
            setattr(state, key, value)
        
        node = await self._get_node()
        logger.info(f"[wrapper:{node_id}] run with args in state: {list(args.keys())}")
        
        # Вызываем ноду - она сама разберется через input_mapping
        result = await node.run(state)
        
        # Возвращаем response
        if isinstance(result, ExecutionState):
            return result.response or str(result.model_dump(exclude_none=False))
        if isinstance(result, dict):
            return result.get("response", result.get("result", str(result)))
        return str(result)

    def __repr__(self) -> str:
        return f"NodeAsToolWrapper({self.node_config.node_id})"
