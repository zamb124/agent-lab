"""
Базовый абстрактный класс для всех агентов.
Определяет общий интерфейс и функциональность для всех типов агентов.
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.models import AgentConfig
from app.models.core_models import SubAgentMemoryPolicy
from app.core.variables import set_state_in_context, get_state
from app.core.container import get_container
from app.core.context_window_manager import ContextWindowManager
from app.core.context import get_context, set_context
from app.core.state_manager import get_state_manager
# Создаем свой класс для прерываний вместо GraphInterrupt из langgraph
class AgentInterrupt(Exception):
    """Исключение для запроса ввода от пользователя"""
    def __init__(self, message: str):
        self.message = message
        self.value = message  # Для обратной совместимости с GraphInterrupt.value
        super().__init__(message)
from langchain_core.messages import HumanMessage
from app.core.agent_runner import BaseAgentRunner
from app.core.state import State
from app.core.tracing.decorators import trace_span
from app.models.trace_models import SpanType
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
        container = get_container()
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
        Унифицированный метод вызова агента.
        Все агенты должны поддерживать этот интерфейс.
        """
        session_id = input_data.get("session_id")
        if not session_id:
            context = get_context()
            session_id = context.session_id if context else None
            if session_id:
                input_data["session_id"] = session_id
        
        run_config = config or ({"configurable": {"thread_id": session_id}} if session_id else {})

        if "remaining_steps" not in input_data:
            input_data["remaining_steps"] = 25

        if "task_id" not in input_data:
            input_data["task_id"] = run_config.get("task_id", "")

        # Определяем session_id для персистентности (до установки в input_data)
        session_id = (
            input_data.get("session_id") 
            or run_config.get("session_id")
            or run_config.get("configurable", {}).get("thread_id")
        )
        if not session_id:
            session_id = f"agent_{self.config.agent_id}"
        
        # Устанавливаем session_id в input_data
        if "session_id" not in input_data:
            input_data["session_id"] = session_id

        if "user_id" not in input_data:
            context = get_context()
            input_data["user_id"] = context.user.user_id if context and context.user else ""

        # Получаем раннер агента
        runner = await self.get_runner()

        messages_from_input = input_data.get("messages", [])
        
        # Для sub-сессий получаем parent_state из контекста ДО вызова load_state
        parent_state_for_load = None
        if session_id and ":sub:" in session_id:
            context_state = get_state()
            if context_state and context_state.get("session_id") and ":sub:" not in context_state.get("session_id", ""):
                parent_state_for_load = context_state
        
        state_manager = await get_state_manager()
        saved_state = await state_manager.load_state(session_id, parent_state=parent_state_for_load) if session_id else None
        
        interrupt_context = saved_state.get("interrupt_context") if saved_state else None
        if interrupt_context and interrupt_context.get("type") == "tool_call":
            sub_result = await self._resume_nested_sub_agent(saved_state, input_data, config, state_manager)
            if "__interrupt__" in sub_result or not isinstance(sub_result, dict):
                return sub_result
            
            from langchain_core.messages import ToolMessage
            last_message = sub_result.get("messages", [])[-1]
            saved_state.pop("interrupt_context")
            saved_state["messages"].append(ToolMessage(
                content=getattr(last_message, "content", str(last_message)),
                tool_call_id=interrupt_context.get("tool_call_id", ""),
                name=interrupt_context.get("tool_name", "")
            ))
            return await self.ainvoke(saved_state, config)
        
        # store всегда загружается из Stores по store_id через load_state
        # Если в input_data есть store, используем его (для инициализации или перезаписи)
        saved_store = saved_state.get("store", {}) if saved_state else {}
        if "store" in input_data:
            # Если в input_data есть store, мержим с saved_store (input_data имеет приоритет)
            input_store = input_data.get("store", {})
            if input_store:
                saved_store = {**saved_store, **input_store}
            else:
                # Если input_data содержит пустой store, используем его (сброс)
                saved_store = {}

        saved_messages = saved_state.get("messages") if saved_state else None
        if saved_messages:
            all_messages = saved_messages + messages_from_input if messages_from_input and messages_from_input is not saved_messages else saved_messages
        else:
            all_messages = messages_from_input

        # Проверка и суммаризация контекста ПЕРЕД вызовом графа
        agent_name = self.config.name if self.config else "unknown"
        llm_config = self.config.llm_config if self.config else None
        logger.warning(f"🔍 СУММАРИЗАЦИЯ CHECK: agent={agent_name}, messages={len(all_messages)}, llm_config={llm_config}")

        if all_messages and self.config and self.config.llm_config and len(all_messages) > 1:
            logger.info(f"🔍 Запускаем проверку контекста для агента {agent_name}")
            manager = ContextWindowManager()

            # НЕ передаем config чтобы manager не обновлял checkpoint
            # Мы обновим его сами после выполнения графа
            summarized_messages, was_summarized = await manager.check_and_summarize_if_needed(
                messages=all_messages,
                llm_config=self.config.llm_config.model_dump() if hasattr(self.config.llm_config, 'model_dump') else self.config.llm_config,
                config=run_config
            )

            if was_summarized:
                # Очищаем состояние перед вызовом раннера с суммаризированными messages
                if session_id:
                    await state_manager.delete_state(session_id)
                    logger.info(f"🗑️ Старое состояние удалено для session_id={session_id}")

                # Передаем ВСЕ суммаризированные messages (они уже включают новые)
                input_data["messages"] = summarized_messages
                logger.info(f"📚 Контекст агента {agent_name} суммаризирован: {len(all_messages)} → {len(summarized_messages)} сообщений")
            else:
                logger.info(f"📚 Суммаризация НЕ требуется для агента {agent_name}")
        else:
            if not all_messages:
                logger.info("📚 Нет сообщений для проверки контекста")
            elif len(all_messages) == 1:
                logger.info("📚 Только одно сообщение, пропускаем проверку")
            if not self.config or not self.config.llm_config:
                logger.info("📚 Нет llm_config для проверки контекста")

        try:
            messages = input_data.get("messages", [])
            if messages:
                last_msg = messages[-1]
                if isinstance(last_msg, dict):
                    content = last_msg.get("content", "")
                elif hasattr(last_msg, "content"):
                    content = last_msg.content
                else:
                    content = str(last_msg)
                logger.info(
                    f"🎯 АГЕНТ {agent_name} ← Вход: {str(content)[:50]}..."
                )
            else:
                logger.info(
                    f"🎯 АГЕНТ {agent_name} ← Вход: {str(input_data)[:50]}..."
                )

            # Устанавливаем agent_config в контекст для tools
            current_context = get_context()
            if current_context:
                current_context.agent_config = self.config
                set_context(current_context)

            # Для sub-сессий сохраняем parent_state из контекста ДО установки initial_state
            parent_state_before = None
            store_for_sub = None
            if session_id and ":sub:" in session_id:
                context_state = get_state()
                if context_state and context_state.get("session_id") and ":sub:" not in context_state.get("session_id", ""):
                    parent_state_before = context_state
                    # Для sub-сессий используем store из parent_state как ссылку (единый для flow)
                    # Инициализируем store если его нет
                    if "store" not in parent_state_before:
                        parent_state_before["store"] = {}
                    store_for_sub = parent_state_before["store"]  # Прямая ссылка, не копия
            
            # Подготавливаем начальное состояние для раннера
            # store всегда загружается из Stores по store_id через load_state
            # Для sub-сессий используем store из parent_state (ссылка для единого flow)
            initial_state: State = {
                "messages": all_messages,
                "store": store_for_sub if store_for_sub is not None else saved_store,
                "task_id": input_data.get("task_id", saved_state.get("task_id", "") if saved_state else ""),
                "session_id": input_data.get("session_id", ""),
                "user_id": input_data.get("user_id", saved_state.get("user_id", "") if saved_state else ""),
                "remaining_steps": input_data.get("remaining_steps", saved_state.get("remaining_steps", 25) if saved_state else 25),
            }
            
            # Устанавливаем store_id из saved_state если есть (для сохранения в Stores)
            if saved_state and "store_id" in saved_state:
                initial_state["store_id"] = saved_state["store_id"]
            elif parent_state_before and "store_id" in parent_state_before:
                # Для sub-сессий наследуем store_id от родителя
                initial_state["store_id"] = parent_state_before["store_id"]

            # Устанавливаем state в контекст для доступа из тулов
            set_state_in_context(initial_state)
            
            # Выполняем раннер
            final_state = await runner.arun(initial_state)

            # Получаем актуальный store из контекста (обновлен через session_set)
            # Используем store из контекста только если контекст соответствует текущей сессии
            context_state = get_state()
            if context_state and "store" in context_state:
                context_session_id = context_state.get("session_id")
                # Для текущей сессии используем store из контекста если session_id совпадает
                # Для sub-сессий используем store из контекста родителя (не sub-сессия)
                if (context_session_id == session_id or 
                    (":sub:" in session_id and context_session_id and ":sub:" not in context_session_id)):
                    final_state["store"] = context_state["store"]
            
            # Устанавливаем store_id из initial_state для сохранения в Stores
            if "store_id" in initial_state:
                final_state["store_id"] = initial_state["store_id"]

            # Сохраняем состояние в StateManager
            # StateManager автоматически:
            # 1. Получает store из контекста (обновлен через session_set)
            # 2. Сохраняет store в БД по store_id
            # 3. Синхронизирует parent_state["store"] в контексте для sub-сессий
            if session_id:
                await state_manager.save_state(session_id, final_state)

            # Восстанавливаем state в контексте после выполнения
            if parent_state_before:
                set_state_in_context(parent_state_before)
            else:
                set_state_in_context(final_state)

            logger.info(f"✅ АГЕНТ {agent_name} → Завершен")
            return final_state
        except AgentInterrupt as interrupt:
            if session_id:
                state = await state_manager.load_state(session_id) or get_state() or initial_state
                if state.get("interrupt_context", {}).get("type") != "tool_call":
                    state["interrupt_context"] = {
                        "type": "agent",
                        "agent_id": self.config.agent_id,
                        "agent_type": runner.__class__.__name__,
                        "interrupt_message": interrupt.value
                    }
                    await state_manager.save_state(session_id, state)
            raise interrupt
        except Exception as e:
            agent_id = self.config.agent_id if self.config else "unknown"
            logger.error(
                f"❌ Ошибка выполнения агента {agent_id}: {e}",
                exc_info=True
            )
            raise
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
            """Функция-обертка для вызова агента как инструмента"""
            from app.core.variables import get_state
            from app.core.state_manager import get_state_manager
            
            if isinstance(request, dict):
                input_text = request.get("request", "")
                tool_call_id = request.get("tool_call_id") or tool_call_id
            else:
                input_text = str(request)
            
            logger.info(f"🔧 [AGENT AS TOOL] {agent_name_tool}: {input_text} (policy: {policy.value})")

            parent_state = get_state()
            if not parent_state or not parent_state.get("session_id"):
                raise ValueError("parent_session_id не может быть пустым для создания sub_session_id")
            
            parent_session_id = parent_state["session_id"]
            state_manager = await get_state_manager()
            
            parent_interrupt = parent_state.get("interrupt_context", {})
            if (parent_interrupt.get("type") == "tool_call" and
                parent_interrupt.get("sub_agent_id") == self.config.agent_id and
                parent_interrupt.get("tool_name") == tool_name):
                sub_session_id = parent_interrupt.get("sub_session_id")
            else:
                sub_session_id = None
            
            if not sub_session_id:
                sub_session_id = await state_manager.get_sub_session_id(
                    parent_session_id=parent_session_id,
                    sub_agent_id=self.config.agent_id,
                    policy=policy
                )
            
            from app.core.variables import set_state_in_context
            set_state_in_context(parent_state)
            
            try:
                result = await self.ainvoke(
                    {"messages": [HumanMessage(content=input_text)], "session_id": sub_session_id},
                    config={"configurable": {"thread_id": sub_session_id}}
                )
            except AgentInterrupt as interrupt:
                parent_state["interrupt_context"] = {
                    "type": "tool_call",
                    "sub_agent_id": self.config.agent_id,
                    "tool_name": tool_name,
                    "sub_session_id": sub_session_id,
                    "tool_call_id": tool_call_id,
                    "interrupt_message": interrupt.value
                }
                await state_manager.save_state(parent_session_id, parent_state)
                raise interrupt
            finally:
                # Обновляем parent_state из контекста после синхронизации store
                # StateManager.save_state уже синхронизировал parent_state["store"] в контексте
                updated_context_state = get_state()
                if updated_context_state and ":sub:" not in updated_context_state.get("session_id", ""):
                    # Обновляем parent_state из синхронизированного контекста
                    if parent_state and updated_context_state.get("session_id") == parent_state.get("session_id"):
                        parent_state["store"] = updated_context_state.get("store", {})
                        parent_state["store_id"] = updated_context_state.get("store_id")
                
                # Восстанавливаем parent_state в контексте
                set_state_in_context(parent_state)

            if parent_state and parent_state.get("interrupt_context", {}).get("sub_session_id") == sub_session_id:
                parent_state.pop("interrupt_context", None)
            
            # Возвращаем только контент последнего сообщения как результат для ToolMessage
            if result and result.get("messages"):
                # Проверяем что messages не пустой список
                if result["messages"]:
                    return getattr(result["messages"][-1], "content", "")
            return "Агент выполнен успешно, но не вернул контент."

        tool_description = description
        if not tool_description and self.config:
            tool_description = self.config.description
        if not tool_description:
            tool_description = f"Агент {agent_name_tool}"
        
        return StructuredTool.from_function(
            func=agent_func,
            name=tool_name,
            description=tool_description,
            args_schema=AgentInput,
            coroutine=agent_func,
        )
    
    async def _resume_nested_sub_agent(self, saved_state, input_data, config, state_manager):
        """Рекурсивно восстанавливает выполнение субагента после interrupt"""
        from langchain_core.messages import HumanMessage
        
        interrupt_context = saved_state.get("interrupt_context")
        sub_agent_state = await state_manager.load_state(interrupt_context["sub_session_id"])
        sub_agent_state["messages"].append(HumanMessage(content=input_data.get("messages", [])[-1].content))
        
        sub_agent = await get_container().agent_factory.get_agent(interrupt_context["sub_agent_id"])
        return await sub_agent.ainvoke(sub_agent_state, config=config)
