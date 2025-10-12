"""
Фабрика для создания агентов на основе конфигурации из БД.
"""

import logging
import importlib
import asyncio
import json
import inspect
from langchain_core.tools import tool

from app.models import AgentConfig, CodeMode, ToolReference
from app.agents.base import BaseAgent
from app.core.storage import Storage
from app.core.tool_factory import ToolFactory

logger = logging.getLogger(__name__)


class AgentFactory:
    """Фабрика для создания агентов"""

    def __init__(self):
        self.storage = Storage()

    async def get_agent(self, agent_id: str) -> BaseAgent:
        """
        Получает агента по ID из БД. Каждый раз создает заново.

        Args:
            agent_id: Идентификатор агента

        Returns:
            Экземпляр агента
        """
        logger.debug(f"🔥 ВЫЗВАН AgentFactory.get_agent для {agent_id}")
        
        # Загружаем конфигурацию из БД
        logger.debug(f"🔍 Ищем конфигурацию агента в БД: {agent_id}")
        config = await self.storage.get_agent_config(agent_id)
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

        Args:
            config: Конфигурация агента

        Returns:
            Экземпляр агента
        """
        logger.debug(f"🔥 ВЫЗВАН _create_agent_instance для {config.agent_id}")
        logger.debug(f"🔥 config.function_class = {config.function_class}")
        
        if config.function_class:
            # Агент определен в коде, импортируем класс
            module_path, class_name = config.function_class.rsplit(".", 1)
            module = importlib.import_module(module_path)
            agent_class = getattr(module, class_name)

            if not inspect.isclass(agent_class) or not issubclass(agent_class, BaseAgent):
                raise ValueError(
                    f"Класс {config.function_class} не наследуется от BaseAgent"
                )

            agent = agent_class(config)

            # ВАЖНО: Загружаем tools из БД даже для агентов из кода
            await self._load_tools_from_db(agent, config)

            return agent
        else:
            # Агент создан через UI, используем базовый класс
            agent = BaseAgent(config)

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
        """Создает tool из ToolReference"""
        logger.debug(f"🔥 СОЗДАЕМ ТУЛ: {tool_ref.tool_id}, cost={tool_ref.cost}, billing_name={tool_ref.billing_name}")

        # Проверяем ссылку на tool в БД
        if tool_ref.tool_id.startswith("tool:"):
            # Это ссылка на tool в БД
            db_tool_id = tool_ref.tool_id[5:]  # Убираем префикс "tool:"
            tool_data = await self.storage.get(f"tool:{db_tool_id}")
            if tool_data:
                db_tool_ref = ToolReference.model_validate(json.loads(tool_data))
                return await self._create_tool_from_reference(db_tool_ref)
            else:
                raise ValueError(f"Tool {db_tool_id} не найден в БД")

        # Проверяем ссылку на агента
        if tool_ref.tool_id.startswith("agent:"):
            # Это ссылка на агента - используем ToolFactory
            tool_factory = ToolFactory()
            return await tool_factory._create_agent_tool(tool_ref)

        # Сначала проверяем есть ли тул в БД с метаданными биллинга
        db_tool_data = await self.storage.get(f"tool:{tool_ref.tool_id}")
        if db_tool_data:
            logger.debug(f"🔥 Найден тул в БД: {tool_ref.tool_id}")
            db_tool_ref = ToolReference.model_validate(json.loads(db_tool_data))
            logger.debug(f"🔥 БД тул code_mode={db_tool_ref.code_mode}, cost={db_tool_ref.cost}, billing_name={db_tool_ref.billing_name}")
            
            # Проверяем code_mode из БД
            if db_tool_ref.code_mode == CodeMode.INLINE_CODE:
                # Для INLINE_CODE инструментов используем ToolFactory
                logger.debug("🔥 Используем ToolFactory для INLINE_CODE инструмента")
                tool_factory = ToolFactory()
                return await tool_factory._create_single_tool(db_tool_ref)
            
            # Для CODE_REFERENCE продолжаем как раньше
            if db_tool_ref.code_mode == CodeMode.CODE_REFERENCE:
                # Импортируем функцию из кода
                if db_tool_ref.function_path:
                    module_path, func_name = db_tool_ref.function_path.rsplit(".", 1)
                elif "." in db_tool_ref.tool_id:
                    module_path, func_name = db_tool_ref.tool_id.rsplit(".", 1)
                else:
                    raise ValueError(f"Не удалось определить путь к функции: {db_tool_ref.tool_id}")
                
                # Принудительно перезагружаем модуль
                logger.debug(f"🔥 Импортируем модуль: {module_path}")
                module = importlib.import_module(module_path)
                logger.debug(f"🔥 Модуль загружен: {module}")
                importlib.reload(module)  # Перезагружаем для получения свежего кода
                logger.debug("🔥 Модуль перезагружен")
                tool_function = getattr(module, func_name)
                logger.debug(f"🔥 Функция получена: {tool_function}")
                logger.debug(f"🔥 Тип функции: {type(tool_function)}")
                
                # Проверяем тип функции перед обращением к __code__
                if hasattr(tool_function, '__code__'):
                    logger.debug(f"🔥 Загружена функция {func_name}: async={asyncio.iscoroutinefunction(tool_function)}")
                    logger.debug(f"🔥 Исходный код функции: {tool_function.__code__.co_flags}")
                else:
                    logger.debug(f"🔥 Загружена функция {func_name}: это StructuredTool или другой объект без __code__")
                
                # Оборачиваем в биллинг если есть стоимость
                if db_tool_ref.cost > 0 or db_tool_ref.free_for_plans:
                    tool_factory = ToolFactory()
                    return tool_factory._wrap_tool_with_billing(tool_function, db_tool_ref)
                else:
                    return tool_function
            
            # Фолбек на старую логику если тула нет в БД
            if tool_ref.function_path:
                if "." in tool_ref.function_path:
                    module_path, func_name = tool_ref.function_path.rsplit(".", 1)
                    module = importlib.import_module(module_path)
                    return getattr(module, func_name)
                else:
                    raise ValueError(f"function_path должен содержать модуль: {tool_ref.function_path}")
            else:
                # Fallback на tool_id
                if "." in tool_ref.tool_id:
                    module_path, func_name = tool_ref.tool_id.rsplit(".", 1)
                    module = importlib.import_module(module_path)
                    return getattr(module, func_name)
                else:
                    raise ValueError(f"tool_id должен содержать полный путь к функции: {tool_ref.tool_id}")

        elif tool_ref.code_mode == CodeMode.INLINE_CODE:
            # Создаем tool из inline кода
            if not tool_ref.inline_code:
                raise ValueError(f"Нет inline_code для tool {tool_ref.tool_id}")

            # Выполняем код и извлекаем функцию
            local_namespace = {"tool": tool}  # Добавляем tool decorator
            exec(tool_ref.inline_code, globals(), local_namespace)

            # Ищем любую функцию с атрибутами tool
            for name, obj in local_namespace.items():
                if callable(obj) and hasattr(obj, "name") and not name.startswith("_"):
                    return obj

            # Если не нашли, ищем любую функцию
            for name, obj in local_namespace.items():
                if callable(obj) and not name.startswith("_") and name != "tool":
                    # Это наша функция, оборачиваем в @tool
                    return tool(obj)

            raise ValueError(f"Не найдена функция в inline коде {tool_ref.tool_id}")

        return None
