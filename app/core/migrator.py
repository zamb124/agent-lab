"""
Migrator - система миграции агентов и флоу из кода в БД.
Сканирует папки /flows и /agents, читает Python-объекты и сохраняет в БД.
"""

import logging
import importlib
import inspect
import pkgutil
import traceback
from pathlib import Path
from typing import List, Any, Type
from datetime import datetime, timezone

import app.agents
import app.flows
import app.custom_flows

from app.core.storage import Storage
from app.models import (
    AgentConfig,
    FlowConfig,
    ToolReference,
    AgentType,
    LLMConfig,
    CodeMode,
    GraphDefinition,
    GraphNode,
    GraphEdge,
    NodeType,
    ConditionType,
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
        """Запускает полную миграцию агентов, флоу и инструментов"""
        logger.info("Запуск полной миграции...")

        try:
            # Сначала создаем системную компанию
            await self._ensure_system_company()
            
            await self._migrate_tools()
            await self._migrate_agents()
            await self._migrate_flows()
            logger.info("Полная миграция завершена успешно")
        except Exception as e:
            logger.error(f"Ошибка при миграции: {e}")
            raise

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

    async def _migrate_tools(self):
        """Мигрирует @tool функции из кода в БД"""
        logger.info("Миграция инструментов...")

        # Устанавливаем контекст системной компании для миграции
        await self._set_system_context()

        # Список пакетов для сканирования
        packages_to_scan = ["app.tools"]
        
        # Добавляем custom_flows для поиска кастомных инструментов
        packages_to_scan.append("app.custom_flows")

        all_tool_functions = []
        
        # Сканируем все пакеты
        for package_name in packages_to_scan:
            tool_functions = await self._find_tool_functions(package_name)
            all_tool_functions.extend(tool_functions)
            logger.info(f"Найдено {len(tool_functions)} tool функций в {package_name}")

        logger.info(f"Всего найдено {len(all_tool_functions)} tool функций для миграции")

        migrated_count = 0
        for tool_obj, module_name in all_tool_functions:
            logger.info(f"Мигрируем tool: {tool_obj.name} из {module_name}")
            tool_ref = await self._create_tool_reference_from_function(
                tool_obj, module_name
            )
            await self.storage.set(
                f"tool:{tool_ref.tool_id}", tool_ref.model_dump_json()
            )
            logger.info(f"Инструмент {tool_ref.tool_id} успешно мигрирован в системную компанию")
            migrated_count += 1

        logger.info(f"Мигрировано {migrated_count} инструментов")

    async def _migrate_agents(self):
        """Мигрирует агентов из кода в БД"""
        logger.info("Миграция агентов...")

        # Устанавливаем контекст системной компании для миграции
        await self._set_system_context()

        # Находим все классы-наследники BaseAgent
        agent_classes = await self._find_agent_classes()

        migrated_count = 0
        for agent_class in agent_classes:
            config = await self._create_agent_config_from_class(agent_class)
            await self.storage.set_agent_config(config)
            logger.info(f"Агент {config.agent_id} успешно мигрирован в системную компанию")
            migrated_count += 1

        logger.info(f"Мигрировано агентов: {migrated_count}")

    async def _migrate_flows(self):
        """Мигрирует флоу из кода в БД"""
        logger.info("Миграция флоу...")

        # Устанавливаем контекст системной компании для миграции
        await self._set_system_context()

        # Находим все FlowConfig объекты в коде
        flow_configs = await self._find_flow_configs()

        migrated_count = 0
        for config in flow_configs:
            # Обновляем метаданные
            config.source = "migration"
            now = datetime.now(timezone.utc)
            config.updated_at = now
            if not config.created_at:
                config.created_at = now

            await self.storage.set_flow_config(config)
            logger.info(f"Флоу {config.flow_id} успешно мигрирован в системную компанию")
            migrated_count += 1

        logger.info(f"Мигрировано флоу: {migrated_count}")

    async def _set_system_context(self):
        """Устанавливает контекст системной компании для миграции"""
        # Получаем системную компанию
        company_data = await self.storage.get("company:system", force_global=True)
        system_company = Company.model_validate_json(company_data)
        
        # Создаем системного пользователя для миграции
        system_user = User(
            user_id="system_migrator",
            provider=AuthProvider.YANDEX,
            provider_user_id="system_migrator", 
            email="system@agents-lab.ru",
            name="System Migrator",
            status=UserStatus.ACTIVE,
            groups=["system"],
            companies={"system": ["admin"]},
            active_company_id="system"
        )
        
        # Устанавливаем контекст
        context = Context(
            user=system_user,
            platform="migration",
            active_company=system_company,
            user_companies=[system_company]
        )
        
        set_context(context)
        logger.info("✅ Установлен контекст системной компании для миграции")

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

    async def _find_flow_configs(self) -> List[FlowConfig]:
        """Находит все FlowConfig объекты в коде"""
        flow_configs = []

        # Список модулей для сканирования
        modules_to_scan = []
        
        # 1. Сканируем app.flows
        modules_to_scan.append(app.flows)

        # 2. Сканируем app.custom_flows
        modules_to_scan.append(app.custom_flows)

        # Обходим все модули
        for base_module in modules_to_scan:
            # Рекурсивно обходим все подмодули
            for importer, modname, ispkg in pkgutil.walk_packages(
                base_module.__path__, base_module.__name__ + "."
            ):
                module = importlib.import_module(modname)

                # Ищем объекты типа FlowConfig
                for name, obj in inspect.getmembers(module):
                    if isinstance(obj, FlowConfig):
                        # Создаем новый FlowConfig с правильным flow_id (путь к переменной)
                        new_flow_id = f"{modname}.{name}"
                        
                        # Создаем новый объект с обновленным flow_id
                        new_config = FlowConfig(
                            flow_id=new_flow_id,
                            name=obj.name,
                            description=obj.description,
                            entry_point_agent=obj.entry_point_agent,
                            platforms=obj.platforms,
                            timeout=obj.timeout,
                            max_retries=obj.max_retries,
                            source=obj.source,
                            created_at=obj.created_at,
                            updated_at=obj.updated_at
                        )
                        
                        flow_configs.append(new_config)
                        logger.info(f"✅ Найден FlowConfig: {modname}.{name} -> {new_flow_id}")

        return flow_configs

    async def _create_agent_config_from_class(
        self, agent_class: Type[BaseAgent]
    ) -> AgentConfig:
        """Создает AgentConfig из класса агента"""

        # Извлекаем статические атрибуты
        name = getattr(agent_class, "name", agent_class.__name__)

        # Используем полный путь к классу как agent_id для возможности импорта
        agent_id = f"{agent_class.__module__}.{agent_class.__name__}"
        description = getattr(agent_class, "description", None)
        prompt = getattr(agent_class, "prompt", None)
        raw_tools = getattr(agent_class, "tools", [])
        raw_llm_config = getattr(agent_class, "llm_config", None)
        history_from = getattr(agent_class, "history_from", None)

        # Проверяем статический graph_definition
        graph_definition = getattr(agent_class, "graph_definition", None)

        # Если нет статического graph_definition, пробуем анализировать экземпляр
        if not graph_definition:
            graph_definition = await self._analyze_agent_graph(agent_class)

        # Определяем тип агента
        agent_type = AgentType.STATEGRAPH if graph_definition else AgentType.REACT

        # Конвертируем инструменты в ToolReference
        tool_references = self._convert_tools_to_references(raw_tools)

        # Конвертируем LLM конфигурацию
        llm_config = None
        if raw_llm_config:
            if isinstance(raw_llm_config, dict):
                llm_config = LLMConfig(**raw_llm_config)
            elif isinstance(raw_llm_config, LLMConfig):
                llm_config = raw_llm_config
        

        # Создаем конфигурацию
        config = AgentConfig(
            agent_id=agent_id,
            name=name,
            description=description,
            type=agent_type,
            function_class=f"{agent_class.__module__}.{agent_class.__name__}",  # Полный путь к классу для импорта
            prompt=prompt,
            graph_definition=graph_definition,
            tools=tool_references,
            llm_config=llm_config,
            history_from=history_from,
            source="migration",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        return config

    async def _analyze_agent_graph(self, agent_class: Type[BaseAgent]):
        """Анализирует LangGraph агента и создает GraphDefinition"""
        try:
            logger.info(f"🔍 Анализируем граф агента {agent_class.__name__}")

            # Проверяем статический graph_definition в классе
            if (
                hasattr(agent_class, "graph_definition")
                and agent_class.graph_definition
            ):
                logger.info("🔍 Найден статический graph_definition в классе")
                return agent_class.graph_definition

            # Создаем экземпляр агента для анализа
            temp_config = AgentConfig(
                agent_id=f"{agent_class.__module__}.{agent_class.__name__}",
                name="temp",
                description="temp",
                type=AgentType.REACT,  # Временно
            )

            # Создаем экземпляр
            agent_instance = agent_class(temp_config)
            logger.info(f"🔍 Экземпляр создан: {type(agent_instance)}")

            # Проверяем есть ли у него LangGraph граф
            if hasattr(agent_instance, "graph") and hasattr(
                agent_instance.graph, "nodes"
            ):
                logger.info(f"🔍 Найден StateGraph: {type(agent_instance.graph)}")
                logger.info(
                    f"🔍 Найдены nodes: {list(agent_instance.graph.nodes.keys())}"
                )
                logger.info(f"🔍 Найдены edges: {dict(agent_instance.graph.edges)}")
                return await self._extract_stategraph_definition(agent_instance.graph)
            else:
                logger.info(
                    f"🔍 Агент {agent_class.__name__} - простой ReAct агент (нет StateGraph)"
                )

        except Exception as e:
            logger.error(f"❌ Ошибка анализа графа агента {agent_class.__name__}: {e}")
            traceback.print_exc()

        return None

    def _determine_node_type(self, node_func) -> NodeType:
        """
        Определяет тип ноды по её содержимому.
        
        Args:
            node_func: Функция или объект, прикрепленный к ноде
            
        Returns:
            NodeType: Тип ноды
        """
        # Проверяем является ли это обычной функцией
        if inspect.isfunction(node_func) or inspect.iscoroutinefunction(node_func):
            return NodeType.FUNCTION_NODE
        
        # Проверяем является ли это методом (bound method)
        if inspect.ismethod(node_func):
            # Если это метод агента (класс наследует BaseAgent)
            if hasattr(node_func, '__self__'):
                obj = node_func.__self__
                if isinstance(obj, BaseAgent):
                    return NodeType.AGENT_NODE
            # Иначе это обычный метод-функция
            return NodeType.FUNCTION_NODE
        
        # Проверяем является ли это StructuredTool или инструментом
        if hasattr(node_func, 'name') and hasattr(node_func, 'func'):
            return NodeType.TOOL_NODE
        
        # Проверяем является ли это callable объектом (может быть агент)
        if callable(node_func):
            # Если у объекта есть характерные атрибуты агента
            if hasattr(node_func, 'config') or isinstance(node_func, BaseAgent):
                return NodeType.AGENT_NODE
            # Иначе это какой-то callable - считаем функцией
            return NodeType.FUNCTION_NODE
        
        # По умолчанию считаем функцией
        logger.warning(f"⚠️ Не удалось точно определить тип ноды {type(node_func)}, используем FUNCTION_NODE")
        return NodeType.FUNCTION_NODE

    async def _extract_stategraph_definition(self, stategraph):
        """Извлекает GraphDefinition из StateGraph (до компиляции)"""

        nodes = []
        edges = []

        logger.info(f"🔍 Анализируем StateGraph с {len(stategraph.nodes)} нодами")

        # Извлекаем ноды
        for node_id, node_spec in stategraph.nodes.items():
            # Извлекаем функцию из StateNodeSpec
            # В LangGraph 0.2.x ноды обернуты в StateNodeSpec с RunnableCallable внутри
            node_func = node_spec
            
            # Извлекаем runnable из StateNodeSpec
            if hasattr(node_spec, 'runnable'):
                runnable = node_spec.runnable
                # Извлекаем функцию из RunnableCallable
                if hasattr(runnable, 'afunc') and runnable.afunc:
                    # Для async функций
                    node_func = runnable.afunc
                elif hasattr(runnable, 'func') and runnable.func:
                    # Для sync функций
                    node_func = runnable.func
                else:
                    # Если не нашли func/afunc, используем сам runnable
                    node_func = runnable
            elif hasattr(node_spec, '__wrapped__'):
                # Если есть обертка (старые версии LangGraph)
                node_func = node_spec.__wrapped__
            elif hasattr(node_spec, 'func'):
                # Альтернативный способ (старые версии)
                node_func = node_spec.func
            
            # Определяем тип ноды по её содержимому
            node_type = self._determine_node_type(node_func)
            
            # Извлекаем параметры в зависимости от типа
            function_path = None
            function_class = None
            
            if node_type == NodeType.FUNCTION_NODE:
                # Для функций сохраняем путь к функции
                if hasattr(node_func, '__module__') and hasattr(node_func, '__name__'):
                    function_path = f"{node_func.__module__}.{node_func.__name__}"
            elif node_type == NodeType.AGENT_NODE:
                # Для агентов сохраняем класс агента
                if hasattr(node_func, '__self__'):
                    agent_class = node_func.__self__.__class__
                    function_class = f"{agent_class.__module__}.{agent_class.__name__}"

            nodes.append(
                GraphNode(
                    id=node_id,
                    type=node_type,
                    function_path=function_path,
                    function_class=function_class,
                    params={}
                )
            )

        # Извлекаем обычные ребра
        for source, target in stategraph.edges:
            # Преобразуем служебные названия
            if source == "__start__":
                source = "START"
            if target == "__end__":
                target = "END"

            edges.append(GraphEdge(source=source, target=target))

        # Извлекаем conditional edges из branches
        if hasattr(stategraph, 'branches') and stategraph.branches:
            for source, branches_dict in stategraph.branches.items():
                source_name = "START" if source == "__start__" else source
                
                # branches_dict это dict {condition_func_name: BranchSpec}
                for cond_name, branch_spec in branches_dict.items():
                    # Извлекаем путь к функции условия
                    condition_path = None
                    if hasattr(branch_spec, 'path'):
                        cond_runnable = branch_spec.path
                        # Извлекаем функцию из RunnableCallable
                        cond_func = None
                        if hasattr(cond_runnable, 'afunc') and cond_runnable.afunc:
                            cond_func = cond_runnable.afunc
                        elif hasattr(cond_runnable, 'func') and cond_runnable.func:
                            cond_func = cond_runnable.func
                        
                        if cond_func and hasattr(cond_func, '__module__') and hasattr(cond_func, '__name__'):
                            condition_path = f"{cond_func.__module__}.{cond_func.__name__}"
                    
                    # Извлекаем целевые ноды из ends
                    if hasattr(branch_spec, 'ends') and branch_spec.ends:
                        # ends это dict {значение: target_node}
                        for target in set(branch_spec.ends.values()):
                            target_name = "END" if target == "__end__" else target
                            
                            edges.append(
                                GraphEdge(
                                    source=source_name,
                                    target=target_name,
                                    condition=condition_path,
                                    condition_type=ConditionType.ROUTER,
                                )
                            )

        return GraphDefinition(nodes=nodes, edges=edges, entry_point="START")

    async def _extract_compiled_graph_definition(self, compiled_graph):
        """Извлекает GraphDefinition из CompiledStateGraph"""

        nodes = []
        edges = []

        logger.info(
            f"🔍 Анализируем CompiledStateGraph с {len(compiled_graph.nodes)} нодами"
        )

        # Извлекаем ноды из compiled_graph
        for node_id, node_obj in compiled_graph.nodes.items():
            if node_id == "__start__":  # Пропускаем служебную ноду
                continue

            # Определяем тип ноды по названию
            if "function" in node_id or node_id.endswith("_function"):
                node_type = NodeType.FUNCTION_NODE
            else:
                node_type = NodeType.AGENT_NODE

            nodes.append(
                GraphNode(
                    id=node_id, type=node_type, params={"compiled_node": str(node_obj)}
                )
            )

        # Извлекаем ребра из channels (упрощенно)
        # В CompiledStateGraph ребра представлены через каналы
        for channel_name in compiled_graph.channels.keys():
            if channel_name.startswith("branch:to:"):
                target = channel_name.replace("branch:to:", "")
                if target in compiled_graph.nodes and target != "__start__":
                    # Это conditional edge, источник определяем по логике
                    source = (
                        "router"  # В нашем случае router делает conditional routing
                    )
                    edges.append(
                        GraphEdge(
                            source=source,
                            target=target,
                            condition_type=ConditionType.ROUTER,
                        )
                    )

        # Добавляем основные ребра (упрощенно на основе нашей архитектуры)
        edges.extend(
            [
                GraphEdge(source="START", target="router"),
                GraphEdge(source="calculator", target="explainer"),
                GraphEdge(source="weather", target="explainer"),
            ]
        )

        return GraphDefinition(nodes=nodes, edges=edges, entry_point="START")

    async def _extract_graph_definition(self, langgraph_graph):
        """Извлекает GraphDefinition из LangGraph StateGraph"""

        nodes = []
        edges = []

        # Извлекаем ноды
        for node_id, node_func in langgraph_graph._nodes.items():
            # Определяем тип ноды
            if hasattr(node_func, "__name__"):
                if "function" in node_func.__name__ or node_func.__name__.endswith(
                    "_function"
                ):
                    node_type = NodeType.FUNCTION_NODE
                else:
                    node_type = NodeType.AGENT_NODE
            else:
                node_type = NodeType.AGENT_NODE

            nodes.append(
                GraphNode(
                    id=node_id,
                    type=node_type,
                    params={
                        "function": f"{node_func.__module__}.{node_func.__name__}"
                        if hasattr(node_func, "__name__")
                        else "unknown"
                    },
                )
            )

        # Извлекаем обычные ребра
        for source, targets in langgraph_graph._edges.items():
            if isinstance(targets, list):
                for target in targets:
                    edges.append(GraphEdge(source=source, target=target))
            else:
                edges.append(GraphEdge(source=source, target=targets))

        # Извлекаем conditional edges
        for source, condition_info in langgraph_graph._conditional_edges.items():
            for target in condition_info.get("mapping", {}).values():
                edges.append(
                    GraphEdge(
                        source=source,
                        target=target,
                        condition_type=ConditionType.ROUTER,
                    )
                )

        # Определяем entry point
        entry_point = "START"
        if hasattr(langgraph_graph, "_entry_point") and langgraph_graph._entry_point:
            entry_point = langgraph_graph._entry_point

        return GraphDefinition(nodes=nodes, edges=edges, entry_point=entry_point)

    def _convert_tools_to_references(self, raw_tools: List[Any]) -> List[ToolReference]:
        """
        Преобразует сырой список инструментов в список ToolReference.
        Это сердце умного мигратора.
        """
        references = []

        for tool in raw_tools:
            try:
                if inspect.isfunction(tool) or inspect.ismethod(tool):
                    # Это функция
                    full_path = f"{tool.__module__}.{tool.__name__}"
                    references.append(ToolReference(tool_id=full_path))

                elif inspect.isclass(tool):
                    # Это класс (например, BaseTool)
                    full_path = f"{tool.__module__}.{tool.__name__}"
                    references.append(ToolReference(tool_id=full_path))

                elif isinstance(tool, str) and tool.startswith("mcp:"):
                    # Это MCP-инструмент
                    references.append(ToolReference(tool_id=tool))

                elif isinstance(tool, str) and tool.startswith("agent:"):
                    # Это ссылка на агента
                    references.append(ToolReference(tool_id=tool))

                elif hasattr(tool, "__class__") and issubclass(
                    tool.__class__, BaseAgent
                ):
                    # Это экземпляр другого агента
                    agent_class = tool.__class__
                    full_path = f"{agent_class.__module__}.{agent_class.__name__}"
                    references.append(ToolReference(tool_id=full_path))

                elif hasattr(tool, "name") and hasattr(tool, "func"):
                    # Это уже готовый инструмент LangChain (StructuredTool и т.д.)
                    # Пытаемся извлечь путь к функции
                    if (
                        tool.func
                        and hasattr(tool.func, "__module__")
                        and hasattr(tool.func, "__name__")
                    ):
                        full_path = f"{tool.func.__module__}.{tool.func.__name__}"
                        references.append(ToolReference(tool_id=full_path))
                    elif hasattr(tool, "coroutine") and tool.coroutine:
                        # Для async @tool функций func=None, но есть coroutine
                        full_path = (
                            f"{tool.coroutine.__module__}.{tool.coroutine.__name__}"
                        )
                        references.append(ToolReference(tool_id=full_path))
                    else:
                        logger.warning(
                            f"Не удалось извлечь путь к функции инструмента {tool.name}"
                        )

                else:
                    logger.warning(
                        f"Неизвестный тип инструмента при миграции: {type(tool)}. Пропускаем."
                    )

            except Exception as e:
                logger.error(f"Ошибка конвертации инструмента {tool}: {e}")
                continue

        return references

    async def migrate_single_agent(self, agent_class_path: str) -> bool:
        """
        Мигрирует один агент по пути к классу.

        Args:
            agent_class_path: Путь к классу агента (например, "app.agents.my_agent.MyAgent")

        Returns:
            True, если миграция успешна
        """
        try:
            # Импортируем класс
            module_path, class_name = agent_class_path.rsplit(".", 1)
            module = importlib.import_module(module_path)
            agent_class = getattr(module, class_name)

            if not issubclass(agent_class, BaseAgent):
                raise ValueError(
                    f"Класс {agent_class_path} не является наследником BaseAgent"
                )

            # Создаем конфигурацию и сохраняем
            config = await self._create_agent_config_from_class(agent_class)
            await self.storage.set_agent_config(config)

            logger.info(f"Агент {agent_class_path} успешно мигрирован")
            return True

        except Exception as e:
            logger.error(f"Ошибка миграции агента {agent_class_path}: {e}")
            return False

    async def migrate_single_flow(self, flow_config: FlowConfig) -> bool:
        """
        Мигрирует один флоу.

        Args:
            flow_config: Конфигурация флоу

        Returns:
            True, если миграция успешна
        """
        try:
            # Обновляем метаданные
            flow_config.source = "migration"
            now = datetime.now(timezone.utc)
            flow_config.updated_at = now
            if not flow_config.created_at:
                flow_config.created_at = now

            await self.storage.set_flow_config(flow_config)
            logger.info(f"Флоу {flow_config.flow_id} успешно мигрирован")
            return True

        except Exception as e:
            logger.error(f"Ошибка миграции флоу {flow_config.flow_id}: {e}")
            return False

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

    async def _create_tool_reference_from_function(
        self, tool_obj, module_name: str
    ) -> ToolReference:
        """Создает ToolReference из StructuredTool объекта"""

        # Получаем исходный код оригинальной функции
        # Для sync тулов используем func, для async - coroutine
        target_func = None
        if hasattr(tool_obj, "func") and tool_obj.func is not None:
            target_func = tool_obj.func
        elif hasattr(tool_obj, "coroutine") and tool_obj.coroutine is not None:
            target_func = tool_obj.coroutine

        if target_func is None:
            raise ValueError(
                f"Не удалось найти исходную функцию для тула {tool_obj.name}"
            )

        source_code = inspect.getsource(target_func)

        # Создаем function_path - используем имя переменной в модуле
        function_path = f"{module_name}.{tool_obj.name}"

        # Извлекаем параметры из args_schema
        params = {}
        if hasattr(tool_obj, "args_schema") and tool_obj.args_schema:
            try:
                # Получаем поля из Pydantic модели
                if hasattr(tool_obj.args_schema, "model_fields"):
                    for (
                        field_name,
                        field_info,
                    ) in tool_obj.args_schema.model_fields.items():
                        params[field_name] = {
                            "type": str(field_info.annotation)
                            if field_info.annotation
                            else "str",
                            "description": field_info.description or "",
                            "required": field_info.is_required()
                            if hasattr(field_info, "is_required")
                            else True,
                        }
            except Exception as e:
                logger.warning(f"Не удалось извлечь параметры для {tool_obj.name}: {e}")

        # Извлекаем метаданные платформы из декоратора
        platform_cost = getattr(tool_obj, '_platform_cost', 0.0)
        platform_billing_name = getattr(tool_obj, '_platform_billing_name', None)
        platform_free_for_plans = getattr(tool_obj, '_platform_free_for_plans', [])
        
        return ToolReference(
            tool_id=function_path,
            code_mode=CodeMode.CODE_REFERENCE,
            function_path=function_path,
            inline_code=source_code,  # Сохраняем код для возможности INLINE режима
            description=tool_obj.description or f"Инструмент {tool_obj.name}",
            params=params,
            # Метаданные платформы
            cost=platform_cost,
            billing_name=platform_billing_name,
            free_for_plans=platform_free_for_plans,
            tariff_limits={},  # Будут заполняться через UI или конфиг
        )
