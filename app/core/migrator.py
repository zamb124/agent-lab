"""
Migrator - система миграции агентов и флоу из кода в БД.
Оркестратор процесса миграции, использующий Scanner и Persister.
"""

import logging
from typing import List, Optional

from app.db.repositories import Storage
from app.core.migration import CodeScanner, ConfigPersister
from app.models import AgentConfig, FlowConfig, ToolReference
from app.identity.models import Company, User, AuthProvider, UserStatus
from app.core.context import set_context
from app.models.context_models import Context

logger = logging.getLogger(__name__)


class Migrator:
    """Оркестратор миграции агентов и флоу из кода в БД"""

    def __init__(self):
        self.storage = Storage()
        self.scanner = CodeScanner()
        self.persister = ConfigPersister(self.storage)

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
            tool_functions = await self.scanner.find_tool_functions(package_name)
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

        agent_classes = await self.scanner.find_agent_classes()

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

        flow_ids = await self.scanner.find_flow_ids()

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

    async def get_public_flows(self) -> List[tuple[str, FlowConfig]]:
        """
        Находит все публичные FlowConfig объекты в коде.
        
        Returns:
            Список кортежей (full_flow_id, FlowConfig) с is_public=True
        """
        return await self.scanner.find_public_flows()


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
            tool_functions = await self.scanner.find_tool_functions(package_name)
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
