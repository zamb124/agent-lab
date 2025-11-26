"""
Фабрика для создания агентов на основе конфигурации из БД.
"""

import logging
import importlib
import inspect

from apps.agents.models import AgentConfig
from apps.agents.agents.base import BaseAgent
from apps.agents.agents.react_agent import ReActAgent
from apps.agents.agents.stategraph_agent import StateGraphAgent
from apps.agents.container import get_agents_container

logger = logging.getLogger(__name__)


class AgentFactory:
    """Фабрика для создания агентов"""

    def __init__(self, agent_repository):
        self.agent_repository = agent_repository

    async def get_agent(self, agent_id: str) -> BaseAgent:
        """
        Получает агента по ID из БД. Каждый раз создает заново.

        Args:
            agent_id: Идентификатор агента

        Returns:
            Экземпляр агента
        """
        logger.debug(f"🔥 ВЫЗВАН AgentFactory.get_agent для {agent_id}")
        
        logger.debug(f"🔍 Ищем конфигурацию агента в БД: {agent_id}")
        config = await self.agent_repository.get(agent_id)
        logger.debug(f"🔍 Результат поиска config: {config is not None}")
        
        if not config:
            logger.error(f"❌ Агент {agent_id} не найден в БД")
            raise ValueError(f"Агент {agent_id} не найден в БД")
            
        logger.debug(f"✅ Конфигурация агента {agent_id} загружена из БД")

        # Создаем экземпляр агента заново
        logger.debug(f"🔥 Вызываем _create_agent_instance для {agent_id}")
        agent = await self._create_agent_instance(config)
        logger.debug(f"✅ _create_agent_instance завершен для {agent_id}")

        logger.debug(f"Агент {agent_id} создан из БД")
        return agent

    async def _create_agent_instance(self, config: AgentConfig) -> BaseAgent:
        """
        Создает экземпляр агента на основе конфигурации.
        Выбирает правильный класс агента: ReActAgent или StateGraphAgent.

        Args:
            config: Конфигурация агента

        Returns:
            Экземпляр агента (ReActAgent, StateGraphAgent или кастомный класс)
        """
        logger.debug(f"Создание агента {config.agent_id}, тип: {config.type}")
        
        if config.function_class:
            # Агент определен в коде, импортируем кастомный класс
            module_path, class_name = config.function_class.rsplit(".", 1)
            module = importlib.import_module(module_path)
            agent_class = getattr(module, class_name)

            if not inspect.isclass(agent_class) or not issubclass(agent_class, BaseAgent):
                raise ValueError(
                    f"Класс {config.function_class} не наследуется от BaseAgent"
                )

            agent = agent_class(config)
            logger.info(f"Создан кастомный агент {config.agent_id} из класса {config.function_class}")
        else:
            # Агент создан через UI - определяем тип по graph_definition
            if config.graph_definition:
                agent_class = StateGraphAgent
                logger.info(f"Создание StateGraph агента {config.agent_id}")
            else:
                agent_class = ReActAgent
                logger.info(f"Создание ReAct агента {config.agent_id}")
            
            agent = agent_class(config)

        # Загружаем tools из БД
        await self._load_tools_from_db(agent, config)

        return agent

    async def _load_tools_from_db(self, agent: BaseAgent, config: AgentConfig):
        """Загружает tools агента из БД"""
        logger.info(
            f"🔧 Загружаем tools для агента {config.agent_id}, tools в конфиге: {len(config.tools or [])}"
        )

        if not config.tools:
            logger.info(f"🔧 Нет tools в конфиге для {config.agent_id}")
            return

        loaded_tools = []
        for i, tool_ref in enumerate(config.tools):
            logger.info(
                f"🔧 Загружаем tool {i + 1}/{len(config.tools)}: {tool_ref.tool_id}"
            )
            tool = await self._create_tool_from_reference(tool_ref)
            if tool:
                loaded_tools.append(tool)
                logger.info(f"🔧 ✅ Tool {tool_ref.tool_id} загружен успешно")
            else:
                logger.error(f"🔧 ❌ Tool {tool_ref.tool_id} НЕ ЗАГРУЖЕН")

        # Устанавливаем tools через dependency injection
        agent.set_tools(loaded_tools)
        logger.info(
            f"🔧 Установлено {len(loaded_tools)} tools из БД для агента {config.agent_id}"
        )

    async def _create_tool_from_reference(self, tool_ref):
        """
        Создает tool из ToolReference.
        Делегирует всю логику в ToolFactory.
        """
        logger.debug(f"Создание tool: {tool_ref.tool_id}")

        tool_factory = get_agents_container().tool_factory
        return await tool_factory._create_single_tool(tool_ref)
