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
        config = await self.agent_repository.get(agent_id)
        
        if not config:
            raise ValueError(f"Агент {agent_id} не найден в БД")

        if config.tools:
            logger.info(f"🔧 get_agent: конфиг загружен, tools в конфиге: {len(config.tools)}, tool_ids: {[t.tool_id for t in config.tools]}")

        agent = await self._create_agent_instance(config)
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
        else:
            if config.graph_definition:
                agent_class = StateGraphAgent
            else:
                agent_class = ReActAgent
            
            agent = agent_class(config)

        # Загружаем tools из БД
        await self._load_tools_from_db(agent, config)

        return agent

    async def _load_tools_from_db(self, agent: BaseAgent, config: AgentConfig):
        """Загружает tools агента из БД"""
        if not config.tools:
            return

        loaded_tools = []
        for tool_ref in config.tools:
            tool = await self._create_tool_from_reference(tool_ref)
            if tool is None:
                raise ValueError(f"Tool {tool_ref.tool_id} не загружен для агента {config.agent_id}")
            loaded_tools.append(tool)

        agent.set_tools(loaded_tools)
        logger.info(f"🔧 _load_tools_from_db: загружено {len(loaded_tools)} tools для агента {config.agent_id}")

    async def _create_tool_from_reference(self, tool_ref):
        """
        Создает tool из ToolReference.
        Делегирует всю логику в ToolFactory.
        """
        logger.debug(f"Создание tool: {tool_ref.tool_id}")

        tool_factory = get_agents_container().tool_factory
        return await tool_factory._create_single_tool(tool_ref)
