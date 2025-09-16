"""
Единый базовый класс для всех агентов.
Содержит логику для автоматической сборки графов на основе конфигурации.
"""
import logging
import asyncio
import json
from abc import ABC
from typing import Any, Dict, List, Optional, Union

from langgraph.graph import StateGraph, END
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langchain_core.messages import BaseMessage
from langchain_core.runnables import Runnable
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.core.models import AgentConfig, AgentType, GraphDefinition, ToolReference, CodeMode
from app.core.llm_factory import get_llm
from app.core.tool_factory import ToolFactory
from app.core.checkpointer import get_checkpointer
# Избегаем циклических импортов - импортируем внутри функций

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

    def __init__(self, agent_config: AgentConfig):
        self.config = agent_config
        self._compiled_graph = None  # Кэш для скомпилированного графа

    async def get_tools(self) -> List[Any]:
        """
        ЕДИНООБРАЗНО собирает инструменты ТОЛЬКО из БД по ссылкам в config.tools.
        Игнорирует tools из кода для единообразия.
        """
        if not self.config.tools:
            logger.info(f"🔧 Нет tools в config для агента {self.config.agent_id}")
            return []
        
        logger.info(f"🔧 Загружаем {len(self.config.tools)} tools из БД для {self.config.agent_id}")
        
        # Используем AgentFactory для загрузки tools (поддерживает все режимы)
        from app.core.agent_factory import AgentFactory
        factory = AgentFactory()
        
        tools = []
        for i, tool_ref in enumerate(self.config.tools):
            logger.info(f"🔧 Загружаем tool {i+1}: {tool_ref.tool_id}")
            
            # Проверяем есть ли tool в БД как отдельная запись
            if not tool_ref.tool_id.startswith("tool:"):
                # Если это agent:, сразу используем ToolFactory
                if tool_ref.tool_id.startswith("agent:"):
                    logger.info(f"🔧 🤖 Создаем агент-инструмент: {tool_ref.tool_id}")
                    tool = await factory._create_tool_from_reference(tool_ref)
                else:
                    # Это ссылка на code tool, ищем в БД tool:*
                    db_tool_key = f"tool:{tool_ref.tool_id}"
                    tool_data = await factory.storage.get(db_tool_key)
                    
                    if tool_data:
                        logger.info(f"🔧 ✅ Найден tool в БД: {db_tool_key}")
                        # Используем данные из БД вместо config
                        db_tool_ref = ToolReference.model_validate(json.loads(tool_data))
                        tool = await factory._create_tool_from_reference(db_tool_ref)
                    else:
                        logger.info(f"🔧 ❌ Tool НЕ найден в БД: {db_tool_key}, используем config")
                        tool = await factory._create_tool_from_reference(tool_ref)
            else:
                # Это уже ссылка на БД
                tool = await factory._create_tool_from_reference(tool_ref)
            
            if tool:
                tools.append(tool)
                logger.info(f"🔧 ✅ Tool {tool_ref.tool_id} загружен")
            else:
                logger.error(f"🔧 ❌ Tool {tool_ref.tool_id} НЕ ЗАГРУЖЕН")
        
        logger.info(f"🔧 Итого загружено {len(tools)} tools для {self.config.agent_id}")
        return tools

    async def compile_graph(self) -> Runnable:
        """
        Главный метод. Читает self.config и собирает граф заново каждый раз.
        """
        logger.debug(f"Компиляция графа для агента: {self.config.agent_id} (тип: {self.config.type})")
        
        if self.config.type == AgentType.STATEGRAPH:
            return await self._compile_stategraph()
        elif self.config.type == AgentType.REACT:
            return await self._compile_react_graph()
        else:
            raise ValueError(f"Неизвестный тип агента: {self.config.type}")

    async def _compile_react_graph(self) -> Runnable:
        """Собирает стандартный ReAct-граф"""
        if not self.config.prompt:
            raise ValueError(f"ReAct агент {self.config.agent_id} требует prompt")

        # Получаем LLM на основе конфигурации агента
        if self.config.llm_config:
            llm = get_llm(
                provider=self.config.llm_config.provider,
                model=self.config.llm_config.model
            )
        else:
            llm = get_llm()  # Используем дефолтные настройки
        tools = await self.get_tools()
        
        # Создаем ReAct агента с checkpointer для поддержки interrupt/resume
        checkpointer = await get_checkpointer()
        graph = create_react_agent(
            model=llm, 
            tools=tools,
            prompt=self.config.prompt,
            checkpointer=checkpointer
        )
        
        logger.info(f"ReAct граф создан для агента {self.config.agent_id}")
        return graph

    async def _compile_stategraph(self) -> Runnable:
        """Собирает кастомный StateGraph на основе graph_definition"""
        if not self.config.graph_definition:
            raise ValueError(f"StateGraph агент {self.config.agent_id} требует graph_definition")
        
        # Здесь будет сложная логика динамической сборки графа
        # Пока создадим простую заглушку
        from app.core.graph_builder import GraphBuilder
        builder = GraphBuilder()
        graph = await builder.build_from_definition(
            self.config.graph_definition,
            self.config.llm_config
        )
        
        logger.info(f"StateGraph граф создан для агента {self.config.agent_id}")
        return graph

    async def ainvoke(self, input_data: Dict[str, Any], config: Optional[Dict[str, Any]] = None) -> Any:
        """
        Унифицированный метод вызова агента.
        Все агенты должны поддерживать этот интерфейс.
        """
        run_config = config or {}
        
        # Используем кэшированный граф или компилируем новый
        if self._compiled_graph is None:
            self._compiled_graph = await self.compile_graph()
        graph = self._compiled_graph
        
        # Добавляем thread_id только если не передан
        if "configurable" not in run_config:
            run_config["configurable"] = {}
        if "thread_id" not in run_config["configurable"] or run_config["configurable"]["thread_id"] is None:
            # Если thread_id = None (агент внутри flow) - НЕ создаем thread_id
            if run_config["configurable"].get("thread_id") is None:
                # Удаляем thread_id полностью - пусть граф управляет state
                if "thread_id" in run_config["configurable"]:
                    del run_config["configurable"]["thread_id"]
                print(f"🔍 {self.config.agent_id} работает БЕЗ thread_id (внутри flow)")
            else:
                # Создаем дефолтный thread_id только для standalone агентов
                run_config["configurable"]["thread_id"] = f"agent_{self.config.agent_id}"
        
        try:
            # Безопасное извлечение последнего сообщения
            messages = input_data.get('messages', [])
            if messages:
                last_msg = messages[-1]
                if isinstance(last_msg, dict):
                    content = last_msg.get('content', '')
                elif hasattr(last_msg, 'content'):
                    content = last_msg.content
                else:
                    content = str(last_msg)
                logger.info(f"🎯 АГЕНТ {self.config.name} ← Вход: {str(content)[:50]}...")
            else:
                logger.info(f"🎯 АГЕНТ {self.config.name} ← Вход: {str(input_data)[:50]}...")
            result = await graph.ainvoke(input_data, config=run_config)
            logger.info(f"✅ АГЕНТ {self.config.name} → Завершен")
            return result
        except Exception as e:
            # GraphInterrupt должен пробрасываться дальше для корректной обработки
            from langgraph.errors import GraphInterrupt
            if isinstance(e, GraphInterrupt):
                logger.info(f"🟢 Агент {self.config.agent_id} запросил ввод пользователя, пробрасываем GraphInterrupt дальше")
                raise e  # Пробрасываем прерывание дальше
            else:
                logger.error(f"❌ Ошибка выполнения агента {self.config.agent_id}: {e}")
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
            logger.info(f'🛠️ Вызов субагента {self.config.name} с входными данными: {input}')
            
            try:
                # КРИТИЧНО: Вызываем субагент БЕЗ config для правильной работы interrupt
                from langchain_core.messages import HumanMessage
                result = await self.ainvoke({"messages": [HumanMessage(content=input)]})
                
                # ВАЖНО: Проверяем есть ли interrupt в результате
                if isinstance(result, dict) and '__interrupt__' in result:
                    # Субагент запросил пользовательский ввод - пробрасываем interrupt дальше
                    interrupt_value = result['__interrupt__']
                    if isinstance(interrupt_value, list):
                        # Если interrupt как массив символов, соединяем в строку
                        interrupt_text = ''.join(interrupt_value)
                    else:
                        interrupt_text = str(interrupt_value)
                    
                    logger.info(f'🟢 Субагент {self.config.name} запросил ввод пользователя, пробрасываем GraphInterrupt дальше')
                    from langgraph.errors import GraphInterrupt
                    raise GraphInterrupt(interrupt_text)
                
                # Извлекаем ответ из результата
                if result.get('messages'):
                    last_message = result['messages'][-1]
                    content = getattr(last_message, 'content', '')
                    logger.info(f'✅ Субагент {self.config.name} завершен: {content[:100]}...')
                    return content
                else:
                    return 'Агент выполнен успешно'
                    
            except Exception as e:
                # GraphInterrupt от субагента должен пробрасываться дальше
                from langgraph.errors import GraphInterrupt
                if isinstance(e, GraphInterrupt):
                    logger.info(f'🟢 Субагент {self.config.name} запросил ввод пользователя, пробрасываем GraphInterrupt дальше')
                    raise e  # Пробрасываем прерывание дальше в родительский граф
                else:
                    error_msg = f'Ошибка выполнения субагента {self.config.name}: {e}'
                    logger.error(f'❌ {error_msg}')
                    return error_msg
        
        return StructuredTool.from_function(
            func=agent_func,
            name=name or self.config.name,
            description=description or self.config.description or f"Агент {self.config.name}",
            args_schema=AgentInput,
            coroutine=agent_func  # Используем coroutine для async функций
        )
