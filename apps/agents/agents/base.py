"""
Базовый абстрактный класс для всех агентов.
Определяет общий интерфейс и функциональность для всех типов агентов.
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from apps.agents.models import AgentConfig
from apps.agents.models.core_models import SubAgentMemoryPolicy
from core.variables import set_state_in_context, get_state
from apps.agents.container import get_agents_container
from core.context import get_context, set_context
from apps.agents.services.state_manager import get_state_manager, StoreProxy
# Создаем свой класс для прерываний вместо GraphInterrupt из langgraph
class AgentInterrupt(Exception):
    """Исключение для запроса ввода от пользователя"""
    def __init__(self, message: str):
        self.message = message
        self.value = message  # Для обратной совместимости с GraphInterrupt.value
        super().__init__(message)
from langchain_core.messages import HumanMessage
from apps.agents.services.agent_runner import BaseAgentRunner
from apps.agents.services.tracing.decorators import trace_span
from apps.agents.models.trace_models import SpanType
logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """Единый базовый класс для всех агентов"""

    # Статические атрибуты для миграции из кода
    name: str = "base_agent"
    description: Optional[str] = None
    prompt: Optional[str] = None
    tools: List[Any] = []
    graph_definition: Optional[Dict[str, Any]] = None
    llm_config: Optional[Dict[str, Any]] = None
    history_from: Union[str, List[str], None] = None

    # ВАЖНО: store НЕ должен быть в агенте!
    # Store задается только в FlowConfig - это общая память для всех агентов flow

    def __init__(self, agent_config: Optional[AgentConfig] = None):
        self.config = agent_config
        self._runner = None
        self._tools = None

    @trace_span(
        name="agent.get_tools",
        span_type=SpanType.OTHER,
        metadata={"component": "agent", "operation": "get_tools"}
    )
    async def get_tools(self) -> List[Any]:
        """
        ЕДИНООБРАЗНО собирает инструменты ТОЛЬКО из БД по ссылкам в config.tools.
        Игнорирует tools из кода для единообразия.
        """
        agent_id = self.config.agent_id if self.config else "unknown"
        logger.debug(f"🔥 ВЫЗВАН get_tools для агента {agent_id}")
        logger.debug(f"🔥 config.tools = {self.config.tools if self.config else None}")
        logger.debug(f"🔥 len(config.tools) = {len(self.config.tools or []) if self.config else 0}")

        if not self.config or not self.config.tools:
            logger.warning(f"⚠️ Нет tools в config для агента {agent_id}")
            logger.debug(f"config.tools = {self.config.tools if self.config else None}")
            return []

        logger.info(
            f"🔧 Загружаем {len(self.config.tools)} tools из БД для {self.config.agent_id}"
        )

        # Возвращаем предварительно загруженные tools
        if self._tools is not None:
            return self._tools

        # Загружаем tools через контейнер (без циклических зависимостей)
        container = get_agents_container()
        agent_factory = container.agent_factory

        tools = []
        for tool_ref in self.config.tools:
            tool = await agent_factory._create_tool_from_reference(tool_ref)
            if tool:
                tools.append(tool)

        self._tools = tools
        logger.info(f"🔧 Загружено {len(tools)} tools для агента {self.config.agent_id}")
        return tools

    def set_tools(self, tools: List[Any]):
        """Устанавливает tools для агента (dependency injection)"""
        self._tools = tools
        logger.info(f"🔧 Установлено {len(tools)} tools для агента {self.config.agent_id}")

    @abstractmethod
    async def get_runner(self) -> BaseAgentRunner:
        """
        Абстрактный метод для получения раннера агента.
        Каждый подкласс должен реализовать свою логику создания раннера.

        Returns:
            Раннер для выполнения агента
        """
        pass

    async def compile_graph(self):
        """
        Метод для обратной совместимости.
        Возвращает обертку с методом ainvoke() (раньше возвращал скомпилированный граф LangGraph).
        
        Валидация происходит при вызове get_runner(), поэтому исключения будут выброшены здесь.

        Returns:
            Обертка с методом ainvoke() для выполнения агента

        Note:
            Этот метод существует для обратной совместимости со старым API.
            Рекомендуется использовать agent.ainvoke() напрямую.
        """
        # Валидация происходит здесь через get_runner()
        await self.get_runner()
        
        class CompiledGraphWrapper:
            """Обертка для обратной совместимости с LangGraph API"""
            def __init__(self, agent: "BaseAgent"):
                self._agent = agent
            
            async def ainvoke(self, input_data: Dict[str, Any], config: Optional[Dict[str, Any]] = None):
                """Вызывает agent.ainvoke() для обратной совместимости"""
                return await self._agent.ainvoke(input_data, config)
        
        return CompiledGraphWrapper(self)

    async def ainvoke(
        self, input_data: Dict[str, Any], config: Optional[Dict[str, Any]] = None
    ) -> Any:
        """
        Единообразный рекурсивный метод вызова агента.
        Всегда работает с полным state через StateManager.get_or_create_session().
        """
        
        run_config = config or {}
        state_manager = await get_state_manager()
        
        session_id = (
            input_data.get("session_id")
            or run_config.get("configurable", {}).get("thread_id")
            or run_config.get("session_id")
            or (get_context().session_id if get_context() else None)
        )
        
        logger.info(f"ainvoke: session_id={session_id}, input_data.session_id={input_data.get('session_id')}, config.thread_id={run_config.get('configurable', {}).get('thread_id')}")
        
        parent_session_id = None
        if session_id and ":sub:" in session_id:
            parent_session_id = session_id.split(":sub:")[0]
        
        context = get_context()
        initial_store = context.flow_config.store if context and context.flow_config and hasattr(context.flow_config, 'store') else None
        
        state = await state_manager.get_or_create_session(
            session_id=session_id,
            parent_session_id=parent_session_id,
            agent_id=self.config.agent_id if self.config else None,
            policy=self.config.default_memory_policy if self.config and self.config.default_memory_policy else SubAgentMemoryPolicy.ISOLATED,
            initial_store=initial_store if isinstance(initial_store, dict) else None
        )
        
        interrupt_context = state.get("interrupt_context")
        if interrupt_context:
            interrupted_session_id = interrupt_context.get("interrupted_session_id")
            interrupted_agent_id = interrupt_context.get("agent_id")
            
            interrupted_state = await state_manager.get_or_create_session(interrupted_session_id)
            interrupted_state.pop("interrupt_context", None)
            await state_manager.save_session(interrupted_state)
            
            messages = input_data.get("messages", [])
            
            interrupted_agent = await get_agents_container().agent_factory.get_agent(interrupted_agent_id)
            result = await interrupted_agent.ainvoke(
                {"messages": messages, "session_id": interrupted_session_id},
                config={"configurable": {"thread_id": interrupted_session_id}}
            )
            
            if ":sub:" in interrupted_session_id:
                parent_session_id_for_cleanup = interrupted_session_id.split(":sub:")[0]
                parent_state = await state_manager.get_or_create_session(parent_session_id_for_cleanup)
                parent_state.pop("interrupt_context", None)
                
                result_messages = result.get("messages", [])
                if result_messages:
                    parent_state["messages"].extend(result_messages)
                
                await state_manager.save_session(parent_state)
                return parent_state
            
            state.pop("interrupt_context", None)
            await state_manager.save_session(state)
            return result
        
        messages_from_input = input_data.get("messages", [])
        state["messages"].extend(messages_from_input)
        
        input_store = input_data.get("store")
        if input_store and isinstance(input_store, dict):
            state["store"].update(input_store)
        
        state["task_id"] = input_data.get("task_id", state.get("task_id", ""))
        state["user_id"] = input_data.get("user_id", state.get("user_id", get_context().user.user_id if get_context() and get_context().user else ""))
        
        remaining_from_input = input_data.get("remaining_steps")
        remaining_from_state = state.get("remaining_steps")
        final_remaining = remaining_from_input if remaining_from_input is not None else (remaining_from_state if remaining_from_state is not None else 25)
        state["remaining_steps"] = final_remaining
        logger.info(f"🟠 BaseAgent.ainvoke: remaining_steps - input={remaining_from_input}, state={remaining_from_state}, final={final_remaining}")
        
        if "configurable" not in run_config:
            run_config["configurable"] = {}
        run_config["configurable"]["thread_id"] = state["session_id"]
        
        set_state_in_context(state)
        
        current_context = get_context()
        if current_context:
            current_context.agent_config = self.config
            set_context(current_context)
        
        runner = await self.get_runner()
        
        try:
            final_state = await runner.arun(state)
            
            final_state["session_id"] = final_state.get("session_id") or state["session_id"]
            
            context_state = get_state()
            if context_state and context_state.get("session_id") == state.get("session_id"):
                context_store = context_state.get("store")
                if isinstance(context_store, StoreProxy):
                    await context_store.ensure_saved()
                    await context_store.refresh()
                    final_state["store"] = context_store
                    final_state["store_id"] = context_store.store_id
                else:
                    store = final_state.get("store")
                    if not isinstance(store, StoreProxy):
                        store = state.get("store")
                    
                    if isinstance(store, StoreProxy):
                        await store.ensure_saved()
                        await store.refresh()
                        final_state["store"] = store
                        final_state["store_id"] = store.store_id
                    else:
                        final_state["store"] = state.get("store")
                        final_state["store_id"] = state.get("store_id")
            else:
                store = final_state.get("store")
                if not isinstance(store, StoreProxy):
                    store = state.get("store")
                
                if isinstance(store, StoreProxy):
                    await store.ensure_saved()
                    await store.refresh()
                    final_state["store"] = store
                    final_state["store_id"] = store.store_id
                else:
                    final_state["store"] = state.get("store")
                    final_state["store_id"] = state.get("store_id")
            
            await state_manager.save_session(final_state)
            set_state_in_context(final_state)
            
            return final_state
        except AgentInterrupt as interrupt:
            session_id = state.get("session_id", "")
            if not session_id:
                raise ValueError("session_id не может быть пустым при AgentInterrupt")
            
            if ":sub:" in session_id:
                parent_session_id = session_id.split(":sub:")[0]
                parent_state = await state_manager.get_or_create_session(parent_session_id)
                
                existing_interrupt = parent_state.get("interrupt_context")
                if existing_interrupt and existing_interrupt.get("interrupted_session_id") == session_id:
                    pass
                else:
                    parent_state["interrupt_context"] = {
                        "interrupted_session_id": session_id,
                        "sub_session_id": session_id if ":sub:" in session_id else None,
                        "agent_id": self.config.agent_id
                    }
                    await state_manager.save_session(parent_state)
                
                await state_manager.save_session(state)
            else:
                parent_state_check = await state_manager.get_or_create_session(session_id)
                existing_interrupt_in_parent = parent_state_check.get("interrupt_context")
                if existing_interrupt_in_parent and ":sub:" in existing_interrupt_in_parent.get("interrupted_session_id", ""):
                    pass
                else:
                    state["interrupt_context"] = {
                        "interrupted_session_id": session_id,
                        "sub_session_id": session_id if ":sub:" in session_id else None,
                        "agent_id": self.config.agent_id
                    }
                    await state_manager.save_session(state)
            raise interrupt
    
    @trace_span(
        name="agent.as_tool",
        span_type=SpanType.OTHER,
        metadata={"component": "agent", "operation": "get_tools"}
    )
    def as_tool(self, name: Optional[str] = None, description: Optional[str] = None, memory_policy: Optional[SubAgentMemoryPolicy] = None):
        """
        Превращает агента в инструмент для использования в других агентах.
        Это ключевая функция для создания иерархических агентов.
        
        Args:
            name: Имя инструмента
            description: Описание инструмента
            memory_policy: Политика памяти (по умолчанию ISOLATED)
        """

        class AgentInput(BaseModel):
            request: str = Field(description="Запрос к агенту")
            tool_call_id: Optional[str] = Field(default=None, description="ID вызова инструмента")

        agent_name_tool = self.config.name if self.config else "unknown"
        # Имя инструмента должно быть валидным для Python (без пробелов)
        if name:
            tool_name = name
        elif self.config and self.config.name:
            # Заменяем пробелы и точки на подчеркивания для валидного имени инструмента
            tool_name = self.config.name.replace(" ", "_").replace(".", "_").lower()
        elif self.config:
            tool_name = self.config.agent_id.replace(".", "_").replace(" ", "_").lower()
        else:
            tool_name = "unknown_agent"
        
        # Определяем политику памяти (приоритет: явно указанная > default_memory_policy агента > ISOLATED)
        if memory_policy is not None:
            # Явно указанная при вызове as_tool() - самый высокий приоритет
            policy = memory_policy
        elif self.config and self.config.default_memory_policy is not None:
            # default_memory_policy из AgentConfig - средний приоритет
            policy = self.config.default_memory_policy
        else:
            # ISOLATED по умолчанию - самый низкий приоритет
            policy = SubAgentMemoryPolicy.ISOLATED

        async def agent_func(request: str, tool_call_id: Optional[str] = None) -> str:
            """Единообразная функция-обертка для вызова агента как инструмента"""
            from core.variables import get_state
            
            if isinstance(request, dict):
                input_text = request.get("request", "")
                tool_call_id = request.get("tool_call_id") or tool_call_id
                input_data = request
            else:
                input_text = str(request)
                input_data = {"messages": [HumanMessage(content=input_text)]}
            
            logger.info(f"🔧 [AGENT AS TOOL] {agent_name_tool}: {input_text} (policy: {policy.value})")

            current_state = get_state()
            parent_session_id = current_state.get("session_id") if current_state else None
            
            if not parent_session_id:
                raise ValueError("parent_session_id не может быть определен при вызове агента как инструмента")
            
            if ":sub:" in parent_session_id:
                parent_session_id = parent_session_id.split(":sub:")[0]
            
            state_manager = await get_state_manager()
            parent_state = await state_manager.get_or_create_session(parent_session_id)
            
            parent_interrupt = parent_state.get("interrupt_context", {})
            existing_sub_session_id = (
                parent_interrupt.get("interrupted_session_id")
                if parent_interrupt.get("agent_id") == self.config.agent_id
                else None
            )
            
            if existing_sub_session_id:
                if policy != SubAgentMemoryPolicy.SHARED and ":sub:" not in existing_sub_session_id:
                    logger.warning(f"existing_sub_session_id не содержит :sub:: {existing_sub_session_id}, игнорируем")
                    existing_sub_session_id = None
            
            if existing_sub_session_id:
                sub_session_id = existing_sub_session_id
            else:
                sub_session_id = await state_manager.get_sub_session_id(
                    parent_session_id=parent_session_id,
                    sub_agent_id=self.config.agent_id,
                    policy=policy
                )
            
            if policy != SubAgentMemoryPolicy.SHARED and ":sub:" not in sub_session_id:
                raise ValueError(f"sub_session_id должен содержать :sub:: {sub_session_id} (parent={parent_session_id}, agent={self.config.agent_id}, policy={policy})")
            
            try:
                logger.info(f"Вызываем ainvoke с sub_session_id={sub_session_id}, parent={parent_session_id}")
                result = await self.ainvoke(
                    {"messages": [HumanMessage(content=input_text)], "session_id": sub_session_id},
                    config={"configurable": {"thread_id": sub_session_id}}
                )
                
                result_store = result.get("store")
                if isinstance(result_store, StoreProxy):
                    await result_store.ensure_saved()
                
                parent_state = await state_manager.get_or_create_session(parent_session_id)
                parent_state.pop("interrupt_context", None)
                
                parent_store = parent_state.get("store")
                if isinstance(parent_store, StoreProxy):
                    await parent_store.refresh()
                    result["store"] = parent_store
                    result["store_id"] = parent_store.store_id
                
                await state_manager.save_session(parent_state)
                
                messages = result.get("messages", [])
                return getattr(messages[-1], "content", "") if messages else "Агент выполнен успешно, но не вернул контент."
            except AgentInterrupt as interrupt:
                parent_state = await state_manager.get_or_create_session(parent_session_id)
                if policy != SubAgentMemoryPolicy.SHARED and ":sub:" not in sub_session_id:
                    logger.error(f"Попытка сохранить interrupt_context с неправильным sub_session_id: {sub_session_id} (parent={parent_session_id}, agent={self.config.agent_id}, policy={policy})")
                    raise ValueError(f"sub_session_id должен содержать :sub:: {sub_session_id}")
                
                existing_interrupt = parent_state.get("interrupt_context")
                if existing_interrupt and existing_interrupt.get("interrupted_session_id") == sub_session_id:
                    pass
                else:
                    parent_state["interrupt_context"] = {
                        "interrupted_session_id": sub_session_id,
                        "sub_session_id": sub_session_id,
                        "agent_id": self.config.agent_id
                    }
                    await state_manager.save_session(parent_state)
                
                raise interrupt

        tool_description = description
        if not tool_description and self.config:
            tool_description = self.config.description
        if not tool_description:
            tool_description = f"Агент {agent_name_tool}"
        
        tool_obj = StructuredTool.from_function(
            func=agent_func,
            name=tool_name,
            description=tool_description,
            args_schema=AgentInput,
            coroutine=agent_func,
        )
        tool_obj._is_agent_tool = True
        return tool_obj
    
