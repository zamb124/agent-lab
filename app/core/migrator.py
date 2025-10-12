"""
Migrator - система миграции агентов и флоу из кода в БД.
Сканирует папки /flows и /agents, читает Python-объекты и сохраняет в БД.
"""

import logging
import importlib
import inspect
import pkgutil
from typing import List, Type, Optional

import app.agents
import app.flows
import app.custom_flows

from app.core.storage import Storage
from app.models import (
    AgentConfig,
    FlowConfig,
    ToolReference,
)
from app.agents.base import BaseAgent
from app.identity.models import Company, User, AuthProvider, UserStatus
from app.core.context import set_context
from app.models.context_models import Context

logger = logging.getLogger(__name__)


class Migrator:
    """Мигратор для переноса агентов и флоу из кода в БД"""

    def __init__(self):
        self.storage = Storage()

    async def run_full_migration(self):
        """
        Запускает полную миграцию для системной компании.
        
        Мигрирует ВСЕ flows, агентов и tools (игнорирует is_public).
        """
        logger.info("Запуск полной миграции для системной компании...")

        await self._ensure_system_company()
        await self._set_system_context()
        
        await self._migrate_all_tools()
        await self._migrate_all_agents()
        await self._migrate_all_flows()
        
        logger.info("Полная миграция завершена успешно")

    async def _ensure_system_company(self):
        """Создает системную компанию если не существует"""
        logger.info("Проверка системной компании...")
        
        # Проверяем существует ли системная компания
        company_data = await self.storage.get("company:system", force_global=True)
        if company_data:
            logger.info("Системная компания уже существует")
            return
        
        # Создаем системную компанию
        system_company = Company(
            company_id="system",
            subdomain="system", 
            name="System Company",
            status="active"
        )
        
        await self.storage.set("company:system", system_company.model_dump_json(), force_global=True)
        await self.storage.set("subdomain:system", '"system"', force_global=True)
        
        logger.info("✅ Создана системная компания: system")

    async def _migrate_all_tools(self):
        """
        Мигрирует ВСЕ @tool функции из кода в текущую компанию.
        
        Сканирует код и вызывает ToolReference.migrate для каждого.
        """
        logger.info("Миграция всех tools...")

        packages_to_scan = ["app.tools", "app.custom_flows"]

        all_tool_functions = []
        for package_name in packages_to_scan:
            tool_functions = await self._find_tool_functions(package_name)
            all_tool_functions.extend(tool_functions)

        logger.info(f"Найдено {len(all_tool_functions)} tool функций")

        migrated_count = 0
        for tool_obj, module_name in all_tool_functions:
            tool_ref = await ToolReference.migrate(source=tool_obj, migrator=self)
            logger.info(f"Tool {tool_ref.tool_id} мигрирован")
            migrated_count += 1

        logger.info(f"Мигрировано {migrated_count} tools")

    async def _migrate_all_agents(self):
        """
        Мигрирует ВСЕ агентов из кода в текущую компанию с зависимостями.
        
        Сканирует код и вызывает AgentConfig.migrate для каждого.
        Рекурсивно мигрирует все tools агента.
        """
        logger.info("Миграция всех агентов...")

        agent_classes = await self._find_agent_classes()

        migrated_count = 0
        for agent_class in agent_classes:
            agent_id = f"{agent_class.__module__}.{agent_class.__name__}"
            await AgentConfig.migrate(agent_id, migrator=self, with_tools=True)
            logger.info(f"Агент {agent_id} мигрирован")
            migrated_count += 1

        logger.info(f"Мигрировано {migrated_count} агентов")

    async def _migrate_all_flows(self):
        """
        Мигрирует ВСЕ flows из кода в текущую компанию с зависимостями.
        
        Сканирует код и вызывает FlowConfig.migrate для каждого.
        Рекурсивно мигрирует entry_point_agent и все его зависимости.
        """
        logger.info("Миграция всех flows...")

        flow_ids = await self._find_flow_ids()

        migrated_count = 0
        for flow_id in flow_ids:
            await FlowConfig.migrate(flow_id, migrator=self, with_dependencies=True)
            logger.info(f"Flow {flow_id} мигрирован")
            migrated_count += 1

        logger.info(f"Мигрировано {migrated_count} flows")

    async def _set_system_context(self):
        """Устанавливает контекст системной компании для миграции"""
        # Получаем системную компанию
        company_data = await self.storage.get("company:system", force_global=True)
        system_company = Company.model_validate_json(company_data)
        
        # Используем общий метод
        await self._set_company_context(system_company)
        logger.info("✅ Установлен контекст системной компании для миграции")

    async def _set_company_context(self, company: Company):
        """
        Устанавливает контекст указанной компании для миграции.
        
        Args:
            company: Компания для которой устанавливается контекст
        """
        system_user = User(
            user_id="system_migrator",
            provider=AuthProvider.YANDEX,
            provider_user_id="system_migrator", 
            email="system@agents-lab.ru",
            name="System Migrator",
            status=UserStatus.ACTIVE,
            groups=["system"],
            companies={company.company_id: ["admin"]},
            active_company_id=company.company_id
        )
        
        context = Context(
            user=system_user,
            platform="migration",
            active_company=company,
            user_companies=[company]
        )
        
        set_context(context)
        logger.info(f"✅ Установлен контекст компании {company.company_id} для миграции")

    async def _find_agent_classes(self) -> List[Type[BaseAgent]]:
        """Находит все классы-наследники BaseAgent в проекте"""
        agent_classes = []

        # Сканируем папки где могут быть агенты
        modules_to_scan = []

        # 1. Сканируем app.agents
        modules_to_scan.append(app.agents)

        # 2. Сканируем app.flows (для StateGraph агентов)
        modules_to_scan.append(app.flows)

        # 3. Сканируем app.custom_flows (для кастомных агентов)
        modules_to_scan.append(app.custom_flows)

        # Обходим все найденные модули
        for base_module in modules_to_scan:
            # Рекурсивно обходим все подмодули
            for importer, modname, ispkg in pkgutil.walk_packages(
                base_module.__path__, base_module.__name__ + "."
            ):
                module = importlib.import_module(modname)

                # Ищем классы-наследники BaseAgent
                for name, obj in inspect.getmembers(module, inspect.isclass):
                    if (
                        issubclass(obj, BaseAgent)
                        and obj != BaseAgent
                        and obj.__module__ == modname
                    ):
                        agent_classes.append(obj)
                        logger.info(f"✅ Найден класс агента: {modname}.{name}")
                    elif issubclass(obj, BaseAgent):
                        logger.debug(
                            f"🔍 Пропущен класс BaseAgent: {modname}.{name}"
                        )
                    elif obj.__module__ != modname:
                        logger.debug(
                            f"🔍 Пропущен класс из другого модуля: {modname}.{name} (модуль: {obj.__module__})"
                        )

        return agent_classes

    async def _find_flow_ids(self) -> List[str]:
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

    async def get_public_flows(self) -> List[tuple[str, FlowConfig]]:
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


    async def remigrate_flow(self, flow_id: str, company: Company):
        """Перемигрирует flow в указанной компании"""
        logger.info(f"Перемиграция flow {flow_id} для компании {company.company_id}...")
        await self._set_company_context(company)
        await FlowConfig.migrate(flow_id, migrator=self, with_dependencies=False)

    async def remigrate_agent(self, agent_id: str, company: Company):
        """Перемигрирует агента в указанной компании"""
        logger.info(f"Перемиграция агента {agent_id} для компании {company.company_id}...")
        await self._set_company_context(company)
        await AgentConfig.migrate(agent_id, migrator=self, with_tools=False)

    async def remigrate_tool(self, tool_id: str, company: Company):
        """Перемигрирует tool в указанной компании"""
        logger.info(f"Перемиграция tool {tool_id} для компании {company.company_id}...")
        await self._set_company_context(company)
        await ToolReference.migrate(tool_id, migrator=self)

    async def migrate_defaults_for_company(self, company: Company):
        """
        Мигрирует ТОЛЬКО публичные tools для новой компании.
        
        Flows НЕ мигрируются - устанавливаются через Store.
        
        Args:
            company: Компания для миграции
        """
        logger.info(f"Миграция публичных tools для {company.company_id}...")
        
        await self._set_company_context(company)

        packages_to_scan = ["app.tools", "app.custom_flows"]
        all_tool_functions = []
        
        for package_name in packages_to_scan:
            tool_functions = await self._find_tool_functions(package_name)
            all_tool_functions.extend(tool_functions)

        migrated_count = 0
        for tool_obj, module_name in all_tool_functions:
            is_public = getattr(tool_obj, '_platform_is_public', False)
            if is_public:
                await ToolReference.migrate(source=tool_obj, migrator=self)
                migrated_count += 1

        logger.info(f"Мигрировано {migrated_count} публичных tools")

    async def migrate_for_company(
        self,
        company: Company,
        flows: Optional[List[str]] = None,
        agents: Optional[List[str]] = None,
        tools: Optional[List[str]] = None,
        with_dependencies: bool = True
    ):
        """
        Мигрирует выбранные сущности в компанию (установка из Store).
        
        Используется для установки конкретных flows/agents/tools.
        Игнорирует is_public - мигрирует всё что указано.
        
        Args:
            company: Целевая компания
            flows: Список flow_id для миграции
            agents: Список agent_id для миграции  
            tools: Список tool_id для миграции
            with_dependencies: Мигрировать ли зависимости рекурсивно
        """
        logger.info(f"Миграция выбранных сущностей для {company.company_id}...")
        
        await self._set_company_context(company)
        
        if flows:
            for flow_id in flows:
                await FlowConfig.migrate(flow_id, migrator=self, with_dependencies=with_dependencies)
        
        if agents:
            for agent_id in agents:
                await AgentConfig.migrate(agent_id, migrator=self, with_tools=with_dependencies)
        
        if tools:
            for tool_id in tools:
                await ToolReference.migrate(tool_id, migrator=self)
        
        logger.info("✅ Миграция завершена")

    async def _find_tool_functions(self, package_name: str):
        """Находит все @tool функции в пакете (рекурсивно)"""
        tool_functions = []

        logger.info(f"🔧 Сканируем пакет: {package_name}")

        package = importlib.import_module(package_name)
        
        # Используем pkgutil для рекурсивного обхода всех подмодулей
        for importer, modname, ispkg in pkgutil.walk_packages(
            package.__path__, package.__name__ + "."
        ):
            logger.info(f"🔧 Загружаем модуль: {modname}")
            module = importlib.import_module(modname)

            # Ищем StructuredTool объекты (результат @tool декоратора)
            all_members = inspect.getmembers(module)
            logger.info(f"🔧 Найдено {len(all_members)} объектов в {modname}")

            for name, obj in all_members:
                # Пропускаем служебные объекты
                if name.startswith("_") or name in ["tool", "operator", "re"]:
                    continue

                logger.info(f"🔧 Проверяем объект: {name} ({type(obj).__name__})")

                # Ищем StructuredTool объекты
                if (
                    hasattr(obj, "name")
                    and hasattr(obj, "description")
                    and (hasattr(obj, "func") or hasattr(obj, "coroutine"))
                ):
                    # Это LangChain StructuredTool (результат @tool)
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
                        f"🔧 ✅ Найден @tool ({tool_type}): {name} (tool.name={obj.name})"
                    )
                    tool_functions.append((obj, modname))
                else:
                    logger.info(f"🔧 ❌ НЕ @tool: {name}")

        logger.info(f"🔧 Итого найдено {len(tool_functions)} @tool функций")
        return tool_functions

