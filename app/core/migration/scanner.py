"""
CodeScanner - компонент для сканирования файловой системы и поиска классов/объектов.
"""

import logging
import importlib
import inspect
import pkgutil
from typing import List, Type, Tuple

import app.agents
import app.flows
import app.custom_flows

from app.agents.base import BaseAgent
from app.models import FlowConfig

logger = logging.getLogger(__name__)


class CodeScanner:
    """Сканер кода для поиска агентов, flows и tools"""

    async def find_agent_classes(self) -> List[Type[BaseAgent]]:
        """
        Находит все классы-наследники BaseAgent в проекте.
        
        Returns:
            Список классов агентов
        """
        agent_classes = []

        modules_to_scan = [app.agents, app.flows, app.custom_flows]

        for base_module in modules_to_scan:
            for importer, modname, ispkg in pkgutil.walk_packages(
                base_module.__path__, base_module.__name__ + "."
            ):
                module = importlib.import_module(modname)

                for name, obj in inspect.getmembers(module, inspect.isclass):
                    if (
                        issubclass(obj, BaseAgent)
                        and obj != BaseAgent
                        and obj.__module__ == modname
                    ):
                        agent_classes.append(obj)
                        logger.info(f"✅ Найден класс агента: {modname}.{name}")

        return agent_classes

    async def find_flow_ids(self) -> List[str]:
        """
        Находит все FlowConfig объекты в коде и возвращает их ID.
        
        Returns:
            Список flow_id (например, ["app.flows.weather_flow.weather_flow_config"])
        """
        flow_ids = []

        modules_to_scan = [app.flows, app.custom_flows]

        for base_module in modules_to_scan:
            for importer, modname, ispkg in pkgutil.walk_packages(
                base_module.__path__, base_module.__name__ + "."
            ):
                module = importlib.import_module(modname)

                for name, obj in inspect.getmembers(module):
                    if isinstance(obj, FlowConfig):
                        flow_id = f"{modname}.{name}"
                        flow_ids.append(flow_id)
                        logger.debug(f"Найден FlowConfig: {flow_id}")

        return flow_ids

    async def find_public_flows(self) -> List[Tuple[str, FlowConfig]]:
        """
        Находит все публичные FlowConfig объекты в коде.
        
        Returns:
            Список кортежей (full_flow_id, FlowConfig) с is_public=True
        """
        public_flows = []

        modules_to_scan = [app.flows, app.custom_flows]

        for base_module in modules_to_scan:
            for importer, modname, ispkg in pkgutil.walk_packages(
                base_module.__path__, base_module.__name__ + "."
            ):
                module = importlib.import_module(modname)

                for name, obj in inspect.getmembers(module):
                    if isinstance(obj, FlowConfig):
                        if getattr(obj, 'is_public', False):
                            full_flow_id = f"{modname}.{name}"
                            public_flows.append((full_flow_id, obj))
                            logger.debug(f"Найден публичный FlowConfig: {full_flow_id}")

        return public_flows

    async def find_tool_functions(self, package_name: str) -> List[Tuple[object, str]]:
        """
        Находит все @tool функции в пакете (рекурсивно).
        
        Args:
            package_name: Имя пакета для сканирования (например, "app.tools")
            
        Returns:
            Список кортежей (tool_object, module_name)
        """
        tool_functions = []

        logger.info(f"Сканируем пакет: {package_name}")

        package = importlib.import_module(package_name)
        
        for importer, modname, ispkg in pkgutil.walk_packages(
            package.__path__, package.__name__ + "."
        ):
            logger.info(f"Загружаем модуль: {modname}")
            module = importlib.import_module(modname)

            all_members = inspect.getmembers(module)
            logger.info(f"Найдено {len(all_members)} объектов в {modname}")

            for name, obj in all_members:
                if name.startswith("_") or name in ["tool", "operator", "re"]:
                    continue

                logger.info(f"Проверяем объект: {name} ({type(obj).__name__})")

                if (
                    hasattr(obj, "name")
                    and hasattr(obj, "description")
                    and (hasattr(obj, "func") or hasattr(obj, "coroutine"))
                ):
                    tool_type = (
                        "async"
                        if (
                            hasattr(obj, "func")
                            and obj.func is None
                            and hasattr(obj, "coroutine")
                        )
                        else "sync"
                    )
                    logger.info(
                        f"✅ Найден @tool ({tool_type}): {name} (tool.name={obj.name})"
                    )
                    tool_functions.append((obj, modname))
                else:
                    logger.info(f"❌ НЕ @tool: {name}")

        logger.info(f"Итого найдено {len(tool_functions)} @tool функций")
        return tool_functions

