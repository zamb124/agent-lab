"""
Фабрика для создания агентов на основе конфигурации из БД.
"""
import logging
import importlib
import json
import types
from typing import Optional, Dict, Any
from langchain_core.tools import tool

from app.core.models import AgentConfig, CodeMode, ToolReference
from app.agents.base import BaseAgent
from app.core.storage import Storage

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
        # Загружаем конфигурацию из БД
        config = await self.storage.get_agent_config(agent_id)
        if not config:
            raise ValueError(f"Агент {agent_id} не найден в БД")
        
        # Создаем экземпляр агента заново
        agent = await self._create_agent_instance(config)
        
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
        if config.function_class:
            # Агент определен в коде, импортируем класс
            try:
                module_path, class_name = config.function_class.rsplit('.', 1)
                module = importlib.import_module(module_path)
                agent_class = getattr(module, class_name)
                
                if not issubclass(agent_class, BaseAgent):
                    raise ValueError(f"Класс {config.function_class} не наследуется от BaseAgent")
                
                agent = agent_class(config)
                
                # ВАЖНО: Загружаем tools из БД даже для агентов из кода
                await self._load_tools_from_db(agent, config)
                
                return agent
                
            except Exception as e:
                logger.error(f"Ошибка импорта класса агента {config.function_class}: {e}")
                raise
        else:
            # Агент создан через UI, используем базовый класс
            agent = BaseAgent(config)
            
            # Загружаем tools из БД
            await self._load_tools_from_db(agent, config)
            
            return agent
    
    async def _load_tools_from_db(self, agent: BaseAgent, config: AgentConfig):
        """Загружает tools агента из БД"""
        logger.info(f"🔧 Загружаем tools для агента {config.agent_id}, tools в конфиге: {len(config.tools or [])}")
        
        if not config.tools:
            logger.info(f"🔧 Нет tools в конфиге для {config.agent_id}")
            return
        
        loaded_tools = []
        for i, tool_ref in enumerate(config.tools):
            logger.info(f"🔧 Загружаем tool {i+1}/{len(config.tools)}: {tool_ref.tool_id}")
            tool = await self._create_tool_from_reference(tool_ref)
            if tool:
                loaded_tools.append(tool)
                logger.info(f"🔧 ✅ Tool {tool_ref.tool_id} загружен успешно")
            else:
                logger.error(f"🔧 ❌ Tool {tool_ref.tool_id} НЕ ЗАГРУЖЕН")
        
        # ПРИНУДИТЕЛЬНО устанавливаем tools из БД (перезаписываем tools из кода)
        agent.tools = loaded_tools  # Устанавливаем даже если пустой список
        logger.info(f"🔧 Установлено {len(loaded_tools)} tools из БД для агента {config.agent_id}")
    
    async def _create_tool_from_reference(self, tool_ref):
        """Создает tool из ToolReference"""
        
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
            from app.core.tool_factory import ToolFactory
            tool_factory = ToolFactory()
            return await tool_factory._create_agent_tool(tool_ref)
        
        if tool_ref.code_mode == CodeMode.CODE_REFERENCE:
            # Импортируем tool из кода
            if tool_ref.function_path:
                if '.' in tool_ref.function_path:
                    module_path, func_name = tool_ref.function_path.rsplit('.', 1)
                    module = importlib.import_module(module_path)
                    return getattr(module, func_name)
                else:
                    # Простое имя функции без модуля
                    raise ValueError(f"function_path должен содержать модуль: {tool_ref.function_path}")
            else:
                # Fallback на tool_id
                if '.' in tool_ref.tool_id:
                    module_path, func_name = tool_ref.tool_id.rsplit('.', 1)
                    module = importlib.import_module(module_path)
                    return getattr(module, func_name)
                else:
                    # Простой tool_id без модуля - это ошибка конфигурации
                    raise ValueError(f"tool_id должен содержать полный путь к функции: {tool_ref.tool_id}")
                
        elif tool_ref.code_mode == CodeMode.INLINE_CODE:
            # Создаем tool из inline кода
            if not tool_ref.inline_code:
                raise ValueError(f"Нет inline_code для tool {tool_ref.tool_id}")
            
            # Выполняем код и извлекаем функцию
            local_namespace = {'tool': tool}  # Добавляем tool decorator
            exec(tool_ref.inline_code, globals(), local_namespace)
            
            # Ищем любую функцию с атрибутами tool
            for name, obj in local_namespace.items():
                if callable(obj) and hasattr(obj, 'name') and not name.startswith('_'):
                    return obj
            
            # Если не нашли, ищем любую функцию
            for name, obj in local_namespace.items():
                if callable(obj) and not name.startswith('_') and name != 'tool':
                    # Это наша функция, оборачиваем в @tool
                    return tool(obj)
            
            raise ValueError(f"Не найдена функция в inline коде {tool_ref.tool_id}")
        
        return None
    
