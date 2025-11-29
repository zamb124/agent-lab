"""
Базовый абстрактный класс для всех агентов.
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union

from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from apps.agents.models import AgentConfig
from apps.agents.models.core_models import SubAgentMemoryPolicy
from apps.agents.container import get_agents_container
from apps.agents.exceptions import AgentInterrupt
from apps.agents.services.state_manager import get_state_manager, StoreProxy
from apps.agents.services.agent_runner import BaseAgentRunner
from apps.agents.services.tracing.decorators import trace_span
from apps.agents.models.trace_models import SpanType
from core.variables import set_state_in_context, get_state
from core.context import get_context, set_context

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """Единый базовый класс для всех агентов"""

    name: str = "base_agent"
    description: Optional[str] = None
    prompt: Optional[str] = None
    tools: List[Any] = []
    graph_definition: Optional[Dict[str, Any]] = None
    llm_config: Optional[Dict[str, Any]] = None
    history_from: Union[str, List[str], None] = None

    def __init__(self, agent_config: Optional[AgentConfig] = None):
        self.config = agent_config
        self._runner = None
        self._tools = None

    @trace_span(name="agent.get_tools", span_type=SpanType.OTHER, metadata={"component": "agent"})
    async def get_tools(self) -> List[Any]:
        """Собирает инструменты из БД по ссылкам в config.tools"""
        if not self.config or not self.config.tools:
            return []
        if self._tools is not None:
            return self._tools

        agent_factory = get_agents_container().agent_factory
        self._tools = [
            await agent_factory._create_tool_from_reference(ref) or _raise(f"Tool {ref.tool_id} не загружен")
            for ref in self.config.tools
        ]
        return self._tools

    def set_tools(self, tools: List[Any]):
        self._tools = tools

    @abstractmethod
    async def get_runner(self) -> BaseAgentRunner:
        pass

    async def compile_graph(self):
        """Обратная совместимость со старым API"""
        await self.get_runner()
        
        class CompiledGraphWrapper:
            def __init__(self, agent: "BaseAgent"):
                self._agent = agent
            async def ainvoke(self, input_data: Dict[str, Any], config: Optional[Dict[str, Any]] = None):
                return await self._agent.ainvoke(input_data, config)
        
        return CompiledGraphWrapper(self)

    async def ainvoke(self, input_data: Dict[str, Any], config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Единый метод вызова агента.
        Обрабатывает как обычное выполнение, так и resume после interrupt.
        """
        if not self.config:
            raise ValueError("config должен быть установлен")
        
        state_manager = await get_state_manager()
        context = get_context()
        if not context:
            raise ValueError("Контекст отсутствует")
        
        session_id = input_data.get("session_id") or (config or {}).get("configurable", {}).get("session_id") or context.session_id
        if not session_id:
            raise ValueError("session_id не указан")
        
        state = await state_manager.get_or_create_session(
            session_id=session_id,
            agent_id=self.config.agent_id,
            policy=self.config.default_memory_policy or SubAgentMemoryPolicy.ISOLATED,
            initial_store=context.flow_config.store if context.flow_config else None
        )
        
        input_store = input_data.get("store")
        if isinstance(input_store, StoreProxy):
            state["store"] = input_store
            state["store_id"] = input_store.store_id
        
        interrupt_context = state.get("interrupt_context")
        if interrupt_context:
            return await self._handle_resume(state, input_data, config, state_manager, interrupt_context)
        
        return await self._execute(state, input_data, config, context, state_manager)

    async def _handle_resume(
        self, 
        state: Dict[str, Any], 
        input_data: Dict[str, Any], 
        config: Optional[Dict[str, Any]],
        state_manager,
        interrupt_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Обработка resume после interrupt"""
        interrupted_session_id = interrupt_context.get("interrupted_session_id")
        interrupted_agent_id = interrupt_context.get("agent_id")
        
        if not interrupted_session_id or not interrupted_agent_id:
            raise ValueError("interrupt_context неполный: нужны interrupted_session_id и agent_id")
        
        interrupted_state = await state_manager.get_or_create_session(interrupted_session_id)
        interrupted_state.pop("interrupt_context", None)
        await state_manager.save_session(interrupted_state)
        
        interrupted_agent = await get_agents_container().agent_factory.get_agent(interrupted_agent_id)
        result = await interrupted_agent.ainvoke(
            {"messages": input_data.get("messages", []), "session_id": interrupted_session_id},
            config={"configurable": {"session_id": interrupted_session_id}}
        )
        
        if ":sub:" not in interrupted_session_id:
            state.pop("interrupt_context", None)
            await state_manager.save_session(state)
            return result
        
        tool_call_id = interrupt_context.get("tool_call_id")
        if not tool_call_id:
            raise ValueError("tool_call_id отсутствует в interrupt_context для субагента")
        
        result_messages = result.get("messages", [])
        if not result_messages:
            raise ValueError("Субагент не вернул сообщения после interrupt")
        
        tool_message = ToolMessage(
            content=result_messages[-1].content,
            tool_call_id=tool_call_id,
            name=interrupt_context.get("tool_name", interrupted_agent_id)
        )
        
        result_store = result.get("store")
        if isinstance(result_store, StoreProxy):
            await result_store.ensure_saved()
        
        state_store = state.get("store")
        if isinstance(state_store, StoreProxy):
            await state_store.refresh()
        
        state["messages"].append(tool_message)
        state.pop("interrupt_context", None)
        await state_manager.save_session(state)
        
        return await self.ainvoke(
            {"session_id": state["session_id"], "remaining_steps": state.get("remaining_steps", 25)},
            config
        )

    async def _execute(
        self,
        state: Dict[str, Any],
        input_data: Dict[str, Any],
        config: Optional[Dict[str, Any]],
        context,
        state_manager
    ) -> Dict[str, Any]:
        """Основное выполнение агента"""
        state["messages"].extend(input_data.get("messages", []))
        
        input_store = input_data.get("store")
        if isinstance(input_store, dict) and not isinstance(input_store, StoreProxy):
            state["store"].update(input_store)
        
        state["task_id"] = input_data.get("task_id", state.get("task_id", ""))
        state["user_id"] = input_data.get("user_id") or state.get("user_id") or (context.user.user_id if context.user else None)
        if not state["user_id"]:
            raise ValueError("user_id не указан")
        
        state["remaining_steps"] = input_data.get("remaining_steps") or state.get("remaining_steps")
        if state["remaining_steps"] is None:
            raise ValueError("remaining_steps должен быть указан")
        
        set_state_in_context(state)
        context.agent_config = self.config
        set_context(context)
        
        runner = await self.get_runner()
        store_proxy = state["store"]
        
        try:
            final_state = await runner.arun(state)
            final_state["session_id"] = state["session_id"]
            final_state["store"] = store_proxy
            final_state["store_id"] = store_proxy.store_id
            
            await store_proxy.ensure_saved()
            await state_manager.save_session(final_state)
            set_state_in_context(final_state)
            await store_proxy.refresh()
            
            return dict(final_state)
            
        except AgentInterrupt as interrupt:
            await self._handle_interrupt(state, state_manager)
            raise interrupt

    async def _handle_interrupt(self, state: Dict[str, Any], state_manager) -> None:
        """Сохранение состояния при interrupt"""
        session_id = state.get("session_id")
        if not session_id:
            raise ValueError("session_id отсутствует в state")
        
        existing = state.get("interrupt_context")
        if existing and existing.get("type") == "stategraph_node":
            await state_manager.save_session(state)
            return
        
        if ":sub:" in session_id:
            await state_manager.save_session(state)
            return
        
        reloaded = await state_manager.get_or_create_session(session_id)
        existing_interrupt = reloaded.get("interrupt_context")
        
        if existing_interrupt and ":sub:" in (existing_interrupt.get("interrupted_session_id") or ""):
            state["interrupt_context"] = existing_interrupt
        else:
            state["interrupt_context"] = {
                "interrupted_session_id": session_id,
                "agent_id": self.config.agent_id
            }
        
        await state_manager.save_session(state)

    @trace_span(name="agent.as_tool", span_type=SpanType.OTHER, metadata={"component": "agent"})
    def as_tool(
        self, 
        name: Optional[str] = None, 
        description: Optional[str] = None, 
        memory_policy: Optional[SubAgentMemoryPolicy] = None
    ) -> StructuredTool:
        """Превращает агента в инструмент для использования в других агентах"""
        if not self.config:
            raise ValueError("config должен быть установлен")
        
        tool_name = name or self.config.name.replace(" ", "_").replace(".", "_").lower() if self.config.name else self.config.agent_id.replace(".", "_").lower()
        tool_description = description or self.config.description
        if not tool_description:
            raise ValueError("description должен быть указан")
        
        policy = memory_policy or self.config.default_memory_policy or SubAgentMemoryPolicy.ISOLATED

        class AgentInput(BaseModel):
            request: str = Field(description="Запрос к агенту")
            tool_call_id: Optional[str] = Field(default=None, description="ID вызова инструмента")

        async def agent_func(request: str, tool_call_id: Optional[str] = None) -> str:
            current_state = get_state()
            if not current_state:
                raise ValueError("state отсутствует")
            
            raw_session_id = current_state.get("session_id")
            if not raw_session_id:
                raise ValueError("session_id отсутствует в state")
            
            parent_session_id = raw_session_id.split(":sub:")[0]
            
            state_manager = await get_state_manager()
            parent_state = await state_manager.get_or_create_session(parent_session_id)
            
            parent_interrupt = parent_state.get("interrupt_context", {})
            existing_sub = parent_interrupt.get("interrupted_session_id") if parent_interrupt.get("agent_id") == self.config.agent_id else None
            
            sub_session_id = (
                existing_sub if existing_sub and (policy == SubAgentMemoryPolicy.SHARED or ":sub:" in existing_sub)
                else await state_manager.get_sub_session_id(parent_session_id, self.config.agent_id, policy)
            )
            
            try:
                result = await self.ainvoke(
                    {"messages": [HumanMessage(content=request)], "session_id": sub_session_id}
                )
                
                await self._sync_store(result, parent_session_id, state_manager)
                
                messages = result.get("messages", [])
                if not messages:
                    raise ValueError("Агент не вернул сообщения")
                return messages[-1].content
                
            except AgentInterrupt as interrupt:
                if not tool_call_id:
                    raise ValueError("tool_call_id обязателен при interrupt")
                
                parent_state = await state_manager.get_or_create_session(parent_session_id)
                parent_state["interrupt_context"] = {
                    "interrupted_session_id": sub_session_id,
                    "agent_id": self.config.agent_id,
                    "tool_call_id": tool_call_id,
                    "tool_name": tool_name
                }
                await state_manager.save_session(parent_state)
                raise interrupt

        tool_obj = StructuredTool.from_function(
            func=agent_func,
            name=tool_name,
            description=tool_description,
            args_schema=AgentInput,
            coroutine=agent_func,
        )
        tool_obj._is_agent_tool = True
        return tool_obj

    async def _sync_store(self, result: Dict[str, Any], parent_session_id: str, state_manager) -> None:
        """Синхронизация store между субагентом и родителем"""
        result_store = result.get("store")
        if not isinstance(result_store, StoreProxy):
            return
        
        await result_store.ensure_saved()
        
        parent_state = await state_manager.get_or_create_session(parent_session_id)
        parent_state.pop("interrupt_context", None)
        
        parent_store = parent_state.get("store")
        if isinstance(parent_store, StoreProxy):
            if result_store.store_id == parent_store.store_id:
                parent_store.clear()
                parent_store.update(dict(result_store))
                parent_store._dirty = False
            else:
                await parent_store.refresh()
        
        await state_manager.save_session(parent_state)
        result["store"] = parent_store
        result["store_id"] = parent_store.store_id


def _raise(msg: str):
    raise ValueError(msg)
