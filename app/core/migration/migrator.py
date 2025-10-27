"""
Migrator - система миграции агентов и флоу из кода в БД.
Оркестратор процесса миграции, использующий Scanner и Persister.
"""

import logging
from typing import List, Optional

from app.db.repositories import Storage
from app.db.repositories.mcp_repository import MCPServerRepository
from app.core.migration.scanner import CodeScanner
from app.core.migration.persister import ConfigPersister
from app.core.container import get_container
from app.models import AgentConfig, FlowConfig, ToolReference
from app.models.mcp_models import MCPServerConfig, MCPTransportType
from app.identity.models import Company, User, AuthProvider, UserStatus
from app.core.context import set_context
from app.models.context_models import Context
from app.services.variables_service import get_variables_service

logger = logging.getLogger(__name__)


class Migrator:
    """Оркестратор миграции агентов и флоу из кода в БД"""

    def __init__(self):
        self.scanner = CodeScanner()
        self.persister = ConfigPersister()

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
        company_data = await get_container().storage.get("company:system", force_global=True)
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
        
        await get_container().storage.set("company:system", system_company.model_dump_json(), force_global=True)
        await get_container().storage.set("subdomain:system", '"system"', force_global=True)
        
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
        company_data = await get_container().storage.get("company:system", force_global=True)
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
        
        await set_context(context)
        logger.info(f"✅ Установлен контекст компании {company.company_id} для миграции")

    async def _create_default_mcp_servers(self, company: Company):
        """
        Создает дефолтные MCP серверы для новой компании:
        - Context7
        - GitHub Copilot
        
        Также создает переменные для API ключей.
        """
        logger.info(f"Создание дефолтных MCP серверов для {company.company_id}...")
        
        mcp_repo = MCPServerRepository(get_container().storage)
        variables_service = get_variables_service()
        
        # 1. Context7
        context7_var_key = "mcp_context7_api_key"
        await variables_service.set_var(
            key=context7_var_key,
            value="",
            is_secret=True,
            description="API ключ для Context7 MCP",
            groups=["mcp", "mcp:context7"]
        )
        
        context7_server = MCPServerConfig(
            server_id="context7",
            company_id=company.company_id,
            name="Context7 Documentation",
            description="AI-powered documentation search",
            url="https://mcp.context7.com/mcp",
            transport_type=MCPTransportType.HTTP,
            headers={"Authorization": "Bearer @var:mcp_context7_api_key"},
            use_proxy=False,
            is_active=False,
            auto_sync_tools=True
        )
        await mcp_repo.set(context7_server)
        logger.info(f"✅ Создан MCP сервер: context7")
        
        # 2. GitHub Copilot
        copilot_var_key = "mcp_copilot_api_key"
        await variables_service.set_var(
            key=copilot_var_key,
            value="",
            is_secret=True,
            description="API ключ для GitHub Copilot MCP",
            groups=["mcp", "mcp:copilot"]
        )
        
        copilot_server = MCPServerConfig(
            server_id="copilot",
            company_id=company.company_id,
            name="GitHub Copilot",
            description="GitHub Copilot MCP server",
            url="https://api.githubcopilot.com/mcp",
            transport_type=MCPTransportType.HTTP,
            headers={"Authorization": "Bearer @var:mcp_copilot_api_key"},
            use_proxy=True,
            is_active=False,
            auto_sync_tools=True
        )
        await mcp_repo.set(copilot_server)
        logger.info(f"✅ Создан MCP сервер: copilot")
        
        logger.info(f"✅ Создано 2 дефолтных MCP сервера для {company.company_id}")

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
        Мигрирует дефолтные сущности для новой компании:
        - Публичные tools
        - Flows из settings.migration.default_flows
        
        Args:
            company: Компания для миграции
        """
        logger.info(f"Миграция дефолтных сущностей для {company.company_id}...")
        
        await self._set_company_context(company)

        # 1. Мигрируем публичные tools
        packages_to_scan = ["app.tools", "app.custom_flows"]
        all_tool_functions = []
        
        for package_name in packages_to_scan:
            tool_functions = await self.scanner.find_tool_functions(package_name)
            all_tool_functions.extend(tool_functions)

        tools_count = 0
        for tool_obj, module_name in all_tool_functions:
            is_public = getattr(tool_obj, '_platform_is_public', False)
            if is_public:
                await ToolReference.migrate(source=tool_obj, migrator=self)
                tools_count += 1

        logger.info(f"✅ Мигрировано {tools_count} публичных tools")

        # 2. Устанавливаем дефолтные flows из конфига
        from app.core.config import settings
        
        default_flows = settings.migration.default_flows
        if default_flows:
            logger.info(f"Установка {len(default_flows)} дефолтных flows...")
            
            for flow_id in default_flows:
                try:
                    await FlowConfig.migrate(flow_id, migrator=self, with_dependencies=True)
                    logger.info(f"✅ Flow {flow_id} установлен")
                except Exception as e:
                    logger.error(f"❌ Ошибка установки flow {flow_id}: {e}")
            
            logger.info(f"✅ Установлено {len(default_flows)} дефолтных flows")
        
        # 3. Создаем дефолтные MCP серверы
        await self._create_default_mcp_servers(company)
        
        logger.info(f"✅ Миграция дефолтных сущностей завершена для {company.company_id}")

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
