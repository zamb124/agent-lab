"""
Базовый абстрактный класс для всех агентов.
Определяет общий интерфейс и функциональность для всех типов агентов.
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union

from langchain_core.runnables import Runnable
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.models import AgentConfig
from app.core.variables import set_state_in_context
from app.core.container import get_container
from app.core.context_window_manager import ContextWindowManager
from app.core.context import get_context, set_context
from app.core.checkpointer import get_checkpointer
from langgraph.errors import GraphInterrupt
from langchain_core.messages import HumanMessage
from app.core.checkpointer import update_checkpointer_with_store_changes
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
        self._compiled_graph = None
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
    async def compile_graph(self) -> Runnable:
        """
        Абстрактный метод для компиляции графа агента.
        Каждый подкласс должен реализовать свою логику компиляции.

        Returns:
            Скомпилированный граф LangGraph
        """
        pass

    async def ainvoke(
        self, input_data: Dict[str, Any], config: Optional[Dict[str, Any]] = None
    ) -> Any:
        """
        Унифицированный метод вызова агента.
        Все агенты должны поддерживать этот интерфейс.
        """
        run_config = config or {}

        # Инициализируем store из flow_config (общая память всех агентов)
        context = get_context()

        if "store" not in input_data:
            if context and context.flow_config and context.flow_config.store:
                input_data["store"] = context.flow_config.store.copy()
                logger.debug(f"📦 Store инициализирован из flow_config: {list(input_data['store'].keys())}")
            else:
                input_data["store"] = {}
        else:
            # Store уже есть (продолжение сессии) - мержим недостающие ключи из flow
            if context and context.flow_config and context.flow_config.store:
                for key, value in context.flow_config.store.items():
                    if key not in input_data["store"]:
                        input_data["store"][key] = value

        if "remaining_steps" not in input_data:
            input_data["remaining_steps"] = 25

        if "task_id" not in input_data:
            input_data["task_id"] = run_config.get("task_id", "")

        if "session_id" not in input_data:
            input_data["session_id"] = run_config.get("session_id", "")

        if "user_id" not in input_data:
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

        # Загружаем messages из checkpoint если есть thread_id
        thread_id = run_config.get("configurable", {}).get("thread_id")
        messages_from_input = input_data.get("messages", [])

        if thread_id:
            # Есть thread_id - загружаем полный контекст из checkpoint
            state = await graph.aget_state(run_config)

            if state and state.values:
                # Загружаем store из checkpointer если не передан в input
                if "store" not in input_data or not input_data["store"]:
                    checkpoint_store = state.values.get("store", {})
                    if checkpoint_store:
                        input_data["store"] = checkpoint_store
                        logger.debug(f"✅ Store загружен из checkpointer: {list(checkpoint_store.keys())}")

                if state.values.get("messages"):
                    # Мержим messages из checkpoint + новые из input
                    checkpoint_messages = state.values["messages"]
                    all_messages = checkpoint_messages + messages_from_input
                    logger.info(f"🔍 Загружено из checkpoint: {len(checkpoint_messages)} + новых: {len(messages_from_input)} = {len(all_messages)}")
                else:
                    # Checkpoint пустой - используем только новые
                    all_messages = messages_from_input
                    logger.info(f"🔍 Checkpoint без messages, используем {len(all_messages)} новых")
            else:
                # Checkpoint пустой - используем только новые
                all_messages = messages_from_input
                logger.info(f"🔍 Checkpoint пустой, используем {len(all_messages)} новых сообщений")
        else:
            # Нет thread_id - используем только переданные messages
            all_messages = messages_from_input
            logger.info(f"🔍 Без thread_id, используем {len(all_messages)} сообщений")

        # Проверка и суммаризация контекста ПЕРЕД вызовом графа
        logger.warning(f"🔍 СУММАРИЗАЦИЯ CHECK: agent={self.config.name}, messages={len(all_messages)}, llm_config={self.config.llm_config}")

        if all_messages and self.config.llm_config and len(all_messages) > 1:
            logger.info(f"🔍 Запускаем проверку контекста для агента {self.config.name}")
            manager = ContextWindowManager()

            # НЕ передаем config чтобы manager не обновлял checkpoint
            # Мы обновим его сами после выполнения графа
            summarized_messages, was_summarized = await manager.check_and_summarize_if_needed(
                messages=all_messages,
                llm_config=self.config.llm_config.model_dump() if hasattr(self.config.llm_config, 'model_dump') else self.config.llm_config,
                config=run_config
            )

            if was_summarized:
                # Очищаем checkpoint перед вызовом графа с суммаризированными messages
                checkpointer = await get_checkpointer()

                # Удаляем старый thread чтобы начать с чистого листа
                await checkpointer.adelete_thread(thread_id)
                logger.info(f"🗑️ Старый checkpoint удален для thread_id={thread_id}")

                # Передаем ВСЕ суммаризированные messages (они уже включают новые)
                input_data["messages"] = summarized_messages
                logger.info(f"📚 Контекст агента {self.config.name} суммаризирован: {len(all_messages)} → {len(summarized_messages)} сообщений")
            else:
                logger.info(f"📚 Суммаризация НЕ требуется для агента {self.config.name}")
        else:
            if not all_messages:
                logger.info("📚 Нет сообщений для проверки контекста")
            elif len(all_messages) == 1:
                logger.info("📚 Только одно сообщение, пропускаем проверку")
            if not self.config.llm_config:
                logger.info("📚 Нет llm_config для проверки контекста")

        # Получаем checkpointer для обновления store
        checkpointer = await get_checkpointer()

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

            # Устанавливаем agent_config в контекст для tools
            current_context = get_context()
            if current_context:
                current_context.agent_config = self.config
                set_context(current_context)


            # Загружаем state из checkpointer перед выполнением графа
            # Это нужно для того, чтобы tools могли получить правильный state
            if "configurable" in run_config and "thread_id" in run_config["configurable"]:
                checkpoint_tuple = await checkpointer.aget_tuple(run_config)
                if checkpoint_tuple and checkpoint_tuple.checkpoint:
                    # Обновляем контекст с данными из checkpointer
                    checkpoint_state = checkpoint_tuple.checkpoint.get("channel_values", {})
                    if checkpoint_state:
                        set_state_in_context(checkpoint_state)
                        logger.debug(f"🔄 State загружен из checkpointer в контекст: {list(checkpoint_state.keys())}")

            result = await graph.ainvoke(input_data, config=run_config)

            # Обновляем state в контексте после выполнения графа
            # Граф возвращает актуальный state, который мы устанавливаем в контекст
            if isinstance(result, dict):
                set_state_in_context(result)
                logger.debug(f"🔄 State обновлен в контексте после выполнения графа")

                # Если store изменился вручную в tools, записываем в checkpointer
                # Это лаконичная архитектура для персистентности state
                if "store" in result and result["store"] and "configurable" in run_config and "thread_id" in run_config["configurable"] and run_config["configurable"]["thread_id"] is not None:
                    await update_checkpointer_with_store_changes(checkpointer, run_config, result["store"])

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
    @trace_span(
        name="agent.as_tool",
        span_type=SpanType.OTHER,
        metadata={"component": "agent", "operation": "get_tools"}
    )
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
