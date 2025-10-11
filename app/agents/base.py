"""
Единый базовый класс для всех агентов.
Содержит логику для автоматической сборки графов на основе конфигурации.
"""

import logging
from abc import ABC
from typing import Any, Dict, List, Optional, Union

from langgraph.prebuilt import create_react_agent
from langchain_core.runnables import Runnable
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.models import AgentConfig, AgentType
from app.core.llm_factory import get_llm
from app.core.checkpointer import get_checkpointer
from app.core.container import get_container
from app.core.state import State, get_default_state
from app.core.variables import VariableResolver, set_state_in_context
from langgraph.errors import GraphInterrupt
from langchain_core.messages import HumanMessage

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

    def __init__(self, agent_config: Optional[AgentConfig] = None):
        self.config = agent_config
        self._compiled_graph = None
        self._tools = None

    async def get_tools(self) -> List[Any]:
        """
        ЕДИНООБРАЗНО собирает инструменты ТОЛЬКО из БД по ссылкам в config.tools.
        Игнорирует tools из кода для единообразия.
        """
        logger.debug(f"🔥 ВЫЗВАН get_tools для агента {self.config.agent_id}")
        logger.debug(f"🔥 config.tools = {self.config.tools}")
        logger.debug(f"🔥 len(config.tools) = {len(self.config.tools or [])}")
        
        if not self.config.tools:
            logger.warning(f"⚠️ Нет tools в config для агента {self.config.agent_id}")
            logger.debug(f"config.tools = {self.config.tools}")
            return []

        logger.info(
            f"🔧 Загружаем {len(self.config.tools)} tools из БД для {self.config.agent_id}"
        )

        # Возвращаем предварительно загруженные tools
        if self._tools is not None:
            return self._tools
        
        # Загружаем tools через контейнер (без циклических зависимостей)
        container = get_container()
        agent_factory = container.get_agent_factory()
        
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

    async def compile_graph(self) -> Runnable:
        """
        Главный метод. Читает self.config и собирает граф заново каждый раз.
        """
        logger.info(f"🔥 ВЫЗВАН compile_graph для агента: {self.config.agent_id} (тип: {self.config.type})")

        if self.config.type == AgentType.STATEGRAPH:
            return await self._compile_stategraph()
        elif self.config.type == AgentType.REACT:
            return await self._compile_react_graph()
        else:
            raise ValueError(f"Неизвестный тип агента: {self.config.type}")

    async def _compile_react_graph(self) -> Runnable:
        """Собирает стандартный ReAct-граф"""
        logger.info(f"🔥 ВЫЗВАН _compile_react_graph для агента: {self.config.agent_id}")
        
        if not self.config.prompt:
            raise ValueError(f"ReAct агент {self.config.agent_id} требует prompt")

        # Получаем LLM на основе конфигурации агента
        if self.config.llm_config:
            llm_kwargs = {}
            if self.config.llm_config.temperature is not None:
                llm_kwargs["temperature"] = self.config.llm_config.temperature
            if self.config.llm_config.max_tokens is not None:
                llm_kwargs["max_tokens"] = self.config.llm_config.max_tokens

            llm = get_llm(
                provider=self.config.llm_config.provider,
                model=self.config.llm_config.model,
                **llm_kwargs,
            )
        else:
            llm = get_llm()
        tools = await self.get_tools()

        # Рендерим промпт с подстановкой переменных
        local_vars = self.config.local_variables if hasattr(self.config, 'local_variables') else {}
        rendered_prompt = VariableResolver.render_template(
            self.config.prompt,
            local_vars=local_vars
        )
        logger.info(f"📝 Промпт отрендерен с переменными для {self.config.agent_id}")

        # Создаем ReAct агента с State и checkpointer
        checkpointer = await get_checkpointer()
        graph = create_react_agent(
            model=llm,
            tools=tools,
            prompt=rendered_prompt,
            checkpointer=checkpointer,
            state_schema=State
        )

        logger.info(f"ReAct граф создан для агента {self.config.agent_id}")
        return graph

    async def _compile_stategraph(self) -> Runnable:
        """Собирает кастомный StateGraph на основе graph_definition"""
        if not self.config.graph_definition:
            raise ValueError(
                f"StateGraph агент {self.config.agent_id} требует graph_definition"
            )

        # Используем GraphBuilder через контейнер
        container = get_container()
        builder = container.get_graph_builder()
        graph = await builder.build_from_definition(
            self.config.graph_definition, self.config.llm_config
        )

        logger.info(f"StateGraph граф создан для агента {self.config.agent_id}")
        return graph

    async def ainvoke(
        self, input_data: Dict[str, Any], config: Optional[Dict[str, Any]] = None
    ) -> Any:
        """
        Унифицированный метод вызова агента.
        Все агенты должны поддерживать этот интерфейс.
        """
        run_config = config or {}

        # Инициализируем state если это первый вызов
        if "store" not in input_data:
            input_data["store"] = {}
        
        if "remaining_steps" not in input_data:
            input_data["remaining_steps"] = 25
        
        if "task_id" not in input_data:
            input_data["task_id"] = run_config.get("task_id", "")
        
        if "session_id" not in input_data:
            input_data["session_id"] = run_config.get("session_id", "")
        
        if "user_id" not in input_data:
            from app.core.context import get_context
            context = get_context()
            input_data["user_id"] = context.user.user_id if context and context.user else ""

        # Устанавливаем state в контекст для доступа из тулов
        set_state_in_context(input_data)

        # Используем кэшированный граф или компилируем новый
        graph = await self.compile_graph()

        # Добавляем thread_id только если не передан
        if "configurable" not in run_config:
            run_config["configurable"] = {}
        if (
            "thread_id" not in run_config["configurable"]
            or run_config["configurable"]["thread_id"] is None
        ):
            if run_config["configurable"].get("thread_id") is None:
                if "thread_id" in run_config["configurable"]:
                    del run_config["configurable"]["thread_id"]
                logger.debug(f"🔍 {self.config.agent_id} работает БЕЗ thread_id (внутри flow)")
            else:
                run_config["configurable"]["thread_id"] = (
                    f"agent_{self.config.agent_id}"
                )

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
                    f"🎯 АГЕНТ {self.config.name} ← Вход: {str(content)[:50]}..."
                )
            else:
                logger.info(
                    f"🎯 АГЕНТ {self.config.name} ← Вход: {str(input_data)[:50]}..."
                )
            
            result = await graph.ainvoke(input_data, config=run_config)
            
            # Обновляем state в контексте после выполнения
            if isinstance(result, dict):
                set_state_in_context(result)
            
            logger.info(f"✅ АГЕНТ {self.config.name} → Завершен")
            return result
        except Exception as e:
            if isinstance(e, GraphInterrupt):
                logger.info(
                    f"🟢 Агент {self.config.agent_id} запросил ввод пользователя, пробрасываем GraphInterrupt дальше"
                )
                raise e
            else:
                logger.error(
                    f"❌ Ошибка выполнения агента {self.config.agent_id}: {e}",
                    exc_info=True
                )
                raise

    def as_tool(self, name: Optional[str] = None, description: Optional[str] = None):
        """
        Превращает агента в инструмент для использования в других агентах.
        Это ключевая функция для создания иерархических агентов.
        """

        class AgentInput(BaseModel):
            input: str = Field(description="Входные данные для агента")

        async def agent_func(input: str) -> str:
            """Функция-обертка для вызова агента как инструмента"""
            logger.info(f"🔧 [AGENT AS TOOL START] {self.config.name}")
            logger.info(f"   Input: {input}")

            try:
                result = await self.ainvoke({"messages": [HumanMessage(content=input)]})

                if isinstance(result, dict) and "__interrupt__" in result:
                    interrupt_value = result["__interrupt__"]
                    if isinstance(interrupt_value, list):
                        interrupt_text = "".join(interrupt_value)
                    else:
                        interrupt_text = str(interrupt_value)

                    logger.info(
                        f"⏸️  [AGENT AS TOOL INTERRUPT] {self.config.name} запросил ввод пользователя"
                    )
                    raise GraphInterrupt(interrupt_text)

                if result.get("messages"):
                    last_message = result["messages"][-1]
                    content = getattr(last_message, "content", "")
                    logger.info(f"✅ [AGENT AS TOOL SUCCESS] {self.config.name}")
                    logger.info(f"   Result: {content[:200]}...")
                    return content
                else:
                    logger.info(f"✅ [AGENT AS TOOL SUCCESS] {self.config.name}")
                    return "Агент выполнен успешно"

            except Exception as e:
                if isinstance(e, GraphInterrupt):
                    logger.info(
                        f"⏸️  [AGENT AS TOOL INTERRUPT] {self.config.name} пробрасывает GraphInterrupt"
                    )
                    raise e
                else:
                    error_msg = f"Ошибка выполнения субагента {self.config.name}: {e}"
                    logger.error(f"❌ [AGENT AS TOOL ERROR] {self.config.name}: {e}", exc_info=True)
                    return error_msg

        tool_name = name or self.config.agent_id.replace(".", "_")
        
        return StructuredTool.from_function(
            func=agent_func,
            name=tool_name,
            description=description
            or self.config.description
            or f"Агент {self.config.name}",
            args_schema=AgentInput,
            coroutine=agent_func,
        )
