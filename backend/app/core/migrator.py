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
from typing import List, Any, Dict, Type
from datetime import datetime, timezone

import app.agents
import app.flows

from app.core.storage import Storage
from app.core.models import (
    AgentConfig, FlowConfig, ToolReference, AgentType, LLMConfig, CodeMode,
    GraphDefinition, GraphNode, GraphEdge, NodeType, ConditionType
)
from app.agents.base import BaseAgent

logger = logging.getLogger(__name__)


class Migrator:
    """Мигратор для переноса агентов и флоу из кода в БД"""
    
    def __init__(self):
        self.storage = Storage()
    
    async def run_full_migration(self):
        """Запускает полную миграцию агентов, флоу и инструментов"""
        logger.info("Запуск полной миграции...")
        
        try:
            await self._migrate_tools()
            await self._migrate_agents()
            await self._migrate_flows()
            logger.info("Полная миграция завершена успешно")
        except Exception as e:
            logger.error(f"Ошибка при миграции: {e}")
            raise
    
    async def _migrate_tools(self):
        """Мигрирует @tool функции из кода в БД"""
        logger.info("Миграция инструментов...")
        
        # Сканируем папку tools
        tools_package = "app.tools"
        tool_functions = await self._find_tool_functions(tools_package)
        
        logger.info(f"Найдено {len(tool_functions)} tool функций для миграции")
        
        migrated_count = 0
        for tool_obj, module_name in tool_functions:
            logger.info(f"Мигрируем tool: {tool_obj.name} из {module_name}")
            tool_ref = await self._create_tool_reference_from_function(tool_obj, module_name)
            await self.storage.set(f"tool:{tool_ref.tool_id}", tool_ref.model_dump_json())
            logger.info(f"Инструмент {tool_ref.tool_id} успешно мигрирован")
            migrated_count += 1
        
        logger.info(f"Мигрировано {migrated_count} инструментов")
    
    async def _migrate_agents(self):
        """Мигрирует агентов из кода в БД"""
        logger.info("Миграция агентов...")
        
        # Находим все классы-наследники BaseAgent
        agent_classes = await self._find_agent_classes()
        
        migrated_count = 0
        for agent_class in agent_classes:
            try:
                config = await self._create_agent_config_from_class(agent_class)
                await self.storage.set_agent_config(config)
                logger.info(f"Агент {config.agent_id} успешно мигрирован")
                migrated_count += 1
            except Exception as e:
                logger.error(f"Ошибка миграции агента {agent_class.__name__}: {e}")
                continue
        
        logger.info(f"Мигрировано агентов: {migrated_count}")
    
    async def _migrate_flows(self):
        """Мигрирует флоу из кода в БД"""
        logger.info("Миграция флоу...")
        
        # Находим все FlowConfig объекты в коде
        flow_configs = await self._find_flow_configs()
        
        migrated_count = 0
        for config in flow_configs:
            try:
                # Обновляем метаданные
                config.source = "migration"
                config.updated_at = datetime.now(timezone.utc).isoformat()
                if not config.created_at:
                    config.created_at = config.updated_at
                
                await self.storage.set_flow_config(config)
                logger.info(f"Флоу {config.flow_id} успешно мигрирован")
                migrated_count += 1
            except Exception as e:
                logger.error(f"Ошибка миграции флоу {config.flow_id}: {e}")
                continue
        
        logger.info(f"Мигрировано флоу: {migrated_count}")
    
    async def _find_agent_classes(self) -> List[Type[BaseAgent]]:
        """Находит все классы-наследники BaseAgent в проекте"""
        agent_classes = []
        
        # Сканируем папки где могут быть агенты
        modules_to_scan = []
        
        # 1. Сканируем app.agents
        try:
            modules_to_scan.append(app.agents)
        except ImportError:
            logger.warning("Модуль app.agents не найден")
        
        # 2. Сканируем app.flows (для StateGraph агентов)
        try:
            modules_to_scan.append(app.flows)
        except ImportError:
            logger.warning("Модуль app.flows не найден")
        
        # Обходим все найденные модули
        for base_module in modules_to_scan:
            try:
                # Рекурсивно обходим все подмодули
                for importer, modname, ispkg in pkgutil.walk_packages(
                    base_module.__path__, 
                    base_module.__name__ + "."
                ):
                    try:
                        module = importlib.import_module(modname)
                        
                        # Ищем классы-наследники BaseAgent
                        for name, obj in inspect.getmembers(module, inspect.isclass):
                            if (issubclass(obj, BaseAgent) and 
                                obj != BaseAgent and 
                                obj.__module__ == modname):
                                agent_classes.append(obj)
                                logger.info(f"✅ Найден класс агента: {modname}.{name}")
                            elif issubclass(obj, BaseAgent):
                                logger.debug(f"🔍 Пропущен класс BaseAgent: {modname}.{name}")
                            elif obj.__module__ != modname:
                                logger.debug(f"🔍 Пропущен класс из другого модуля: {modname}.{name} (модуль: {obj.__module__})")
                                
                    except Exception as e:
                        logger.warning(f"Не удалось импортировать модуль {modname}: {e}")
                        continue
                        
            except Exception as e:
                logger.warning(f"Ошибка сканирования модуля {base_module.__name__}: {e}")
                continue
        
        return agent_classes
    
    async def _find_flow_configs(self) -> List[FlowConfig]:
        """Находит все FlowConfig объекты в коде"""
        flow_configs = []
        
        try:
            # Импортируем модуль flows
            
            # Рекурсивно обходим все подмодули
            for importer, modname, ispkg in pkgutil.walk_packages(
                app.flows.__path__, 
                app.flows.__name__ + "."
            ):
                try:
                    module = importlib.import_module(modname)
                    
                    # Ищем объекты типа FlowConfig
                    for name, obj in inspect.getmembers(module):
                        if isinstance(obj, FlowConfig):
                            flow_configs.append(obj)
                            logger.debug(f"Найден FlowConfig: {modname}.{name}")
                            
                except Exception as e:
                    logger.warning(f"Не удалось импортировать модуль {modname}: {e}")
                    continue
        
        except ImportError:
            logger.warning("Модуль app.flows не найден")
        
        return flow_configs
    
    async def _create_agent_config_from_class(self, agent_class: Type[BaseAgent]) -> AgentConfig:
        """Создает AgentConfig из класса агента"""
        
        # Генерируем agent_id из полного пути к классу
        agent_id = f"{agent_class.__module__}.{agent_class.__name__}"
        
        # Извлекаем статические атрибуты
        name = getattr(agent_class, 'name', agent_class.__name__)
        description = getattr(agent_class, 'description', None)
        prompt = getattr(agent_class, 'prompt', None)
        raw_tools = getattr(agent_class, 'tools', [])
        raw_llm_config = getattr(agent_class, 'llm_config', None)
        history_from = getattr(agent_class, 'history_from', None)
        
        # Проверяем статический graph_definition
        graph_definition = getattr(agent_class, 'graph_definition', None)
        
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
            function_class=agent_id,  # Путь к классу для импорта
            prompt=prompt,
            graph_definition=graph_definition,
            tools=tool_references,
            llm_config=llm_config,
            history_from=history_from,
            source="migration",
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat()
        )
        
        return config
    
    async def _analyze_agent_graph(self, agent_class: Type[BaseAgent]):
        """Анализирует LangGraph агента и создает GraphDefinition"""
        try:
            logger.info(f"🔍 Анализируем граф агента {agent_class.__name__}")
            
            # Создаем экземпляр агента для анализа
            temp_config = AgentConfig(
                agent_id=f"{agent_class.__module__}.{agent_class.__name__}",
                name="temp",
                description="temp",
                type=AgentType.REACT  # Временно
            )
            
            # Создаем экземпляр
            agent_instance = agent_class(temp_config)
            logger.info(f"🔍 Экземпляр создан: {type(agent_instance)}")
            
            # Проверяем атрибуты экземпляра
            logger.info(f"🔍 Атрибуты экземпляра: {[attr for attr in dir(agent_instance) if not attr.startswith('_')]}")
            
            # Проверяем есть ли у него LangGraph граф
            if hasattr(agent_instance, 'graph') and hasattr(agent_instance.graph, 'nodes'):
                logger.info(f"🔍 Найден StateGraph: {type(agent_instance.graph)}")
                logger.info(f"🔍 Найдены nodes: {list(agent_instance.graph.nodes.keys())}")
                logger.info(f"🔍 Найдены edges: {dict(agent_instance.graph.edges)}")
                return await self._extract_stategraph_definition(agent_instance.graph)
            else:
                logger.warning(f"🔍 У экземпляра нет StateGraph с nodes")
            
        except Exception as e:
            logger.error(f"❌ Ошибка анализа графа агента {agent_class.__name__}: {e}")
            traceback.print_exc()
        
        return None
    
    async def _extract_stategraph_definition(self, stategraph):
        """Извлекает GraphDefinition из StateGraph (до компиляции)"""
        
        nodes = []
        edges = []
        
        logger.info(f"🔍 Анализируем StateGraph с {len(stategraph.nodes)} нодами")
        
        # Извлекаем ноды
        for node_id in stategraph.nodes.keys():
            # Определяем тип ноды по названию
            if 'function' in node_id or node_id.endswith('_function'):
                node_type = NodeType.FUNCTION_NODE
            else:
                node_type = NodeType.AGENT_NODE
            
            nodes.append(GraphNode(
                id=node_id,
                type=node_type,
                params={}
            ))
        
        # Извлекаем обычные ребра
        for source, target in stategraph.edges:
            # Преобразуем служебные названия
            if source == '__start__':
                source = 'START'
            if target == '__end__':
                target = 'END'
                
            edges.append(GraphEdge(
                source=source,
                target=target
            ))
        
        # Анализируем conditional edges через compiled graph
        if hasattr(stategraph, 'compile'):
            try:
                compiled = stategraph.compile()
                # Ищем conditional edges по каналам
                conditional_sources = set()
                conditional_targets = {}
                
                for channel_name in compiled.channels.keys():
                    if channel_name.startswith('branch:to:'):
                        target = channel_name.replace('branch:to:', '')
                        if target in stategraph.nodes:
                            conditional_sources.add("router")  # Определяем источник
                            if "router" not in conditional_targets:
                                conditional_targets["router"] = []
                            conditional_targets["router"].append(target)
                
                # Добавляем conditional edges
                for source, targets in conditional_targets.items():
                    for target in targets:
                        # Определяем функцию условия по источнику
                        condition_function = f"{source}_condition"  # router → router_condition
                        
                        edges.append(GraphEdge(
                            source=source,
                            target=target,
                            condition=f"app.flows.smart_flow.{condition_function}",  # Путь к функции
                            condition_type=ConditionType.ROUTER
                        ))
                        
            except Exception as e:
                logger.warning(f"Не удалось проанализировать conditional edges: {e}")
        
        return GraphDefinition(
            nodes=nodes,
            edges=edges,
            entry_point="START"
        )
    
    async def _extract_compiled_graph_definition(self, compiled_graph):
        """Извлекает GraphDefinition из CompiledStateGraph"""
        
        nodes = []
        edges = []
        
        logger.info(f"🔍 Анализируем CompiledStateGraph с {len(compiled_graph.nodes)} нодами")
        
        # Извлекаем ноды из compiled_graph
        for node_id, node_obj in compiled_graph.nodes.items():
            if node_id == '__start__':  # Пропускаем служебную ноду
                continue
                
            # Определяем тип ноды по названию
            if 'function' in node_id or node_id.endswith('_function'):
                node_type = NodeType.FUNCTION_NODE
            else:
                node_type = NodeType.AGENT_NODE
            
            nodes.append(GraphNode(
                id=node_id,
                type=node_type,
                params={"compiled_node": str(node_obj)}
            ))
        
        # Извлекаем ребра из channels (упрощенно)
        # В CompiledStateGraph ребра представлены через каналы
        for channel_name in compiled_graph.channels.keys():
            if channel_name.startswith('branch:to:'):
                target = channel_name.replace('branch:to:', '')
                if target in compiled_graph.nodes and target != '__start__':
                    # Это conditional edge, источник определяем по логике
                    source = 'router'  # В нашем случае router делает conditional routing
                    edges.append(GraphEdge(
                        source=source,
                        target=target,
                        condition_type=ConditionType.ROUTER
                    ))
        
        # Добавляем основные ребра (упрощенно на основе нашей архитектуры)
        edges.extend([
            GraphEdge(source="START", target="router"),
            GraphEdge(source="calculator", target="explainer"),
            GraphEdge(source="weather", target="explainer")
        ])
        
        return GraphDefinition(
            nodes=nodes,
            edges=edges,
            entry_point="START"
        )
    
    async def _extract_graph_definition(self, langgraph_graph):
        """Извлекает GraphDefinition из LangGraph StateGraph"""
        
        nodes = []
        edges = []
        
        # Извлекаем ноды
        for node_id, node_func in langgraph_graph._nodes.items():
            # Определяем тип ноды
            if hasattr(node_func, '__name__'):
                if 'function' in node_func.__name__ or node_func.__name__.endswith('_function'):
                    node_type = NodeType.FUNCTION_NODE
                else:
                    node_type = NodeType.AGENT_NODE
            else:
                node_type = NodeType.AGENT_NODE
            
            nodes.append(GraphNode(
                id=node_id,
                type=node_type,
                params={"function": f"{node_func.__module__}.{node_func.__name__}" if hasattr(node_func, '__name__') else "unknown"}
            ))
        
        # Извлекаем обычные ребра
        for source, targets in langgraph_graph._edges.items():
            if isinstance(targets, list):
                for target in targets:
                    edges.append(GraphEdge(
                        source=source,
                        target=target
                    ))
            else:
                edges.append(GraphEdge(
                    source=source,
                    target=targets
                ))
        
        # Извлекаем conditional edges
        for source, condition_info in langgraph_graph._conditional_edges.items():
            for target in condition_info.get('mapping', {}).values():
                edges.append(GraphEdge(
                    source=source,
                    target=target,
                    condition_type=ConditionType.ROUTER
                ))
        
        # Определяем entry point
        entry_point = "START"
        if hasattr(langgraph_graph, '_entry_point') and langgraph_graph._entry_point:
            entry_point = langgraph_graph._entry_point
        
        return GraphDefinition(
            nodes=nodes,
            edges=edges,
            entry_point=entry_point
        )
    
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
                    
                elif isinstance(tool, str) and tool.startswith('mcp:'):
                    # Это MCP-инструмент
                    references.append(ToolReference(tool_id=tool))
                    
                elif isinstance(tool, str) and tool.startswith('agent:'):
                    # Это ссылка на агента
                    references.append(ToolReference(tool_id=tool))
                    
                elif hasattr(tool, '__class__') and issubclass(tool.__class__, BaseAgent):
                    # Это экземпляр другого агента
                    agent_class = tool.__class__
                    full_path = f"{agent_class.__module__}.{agent_class.__name__}"
                    references.append(ToolReference(tool_id=full_path))
                    
                elif hasattr(tool, 'name') and hasattr(tool, 'func'):
                    # Это уже готовый инструмент LangChain (StructuredTool и т.д.)
                    # Пытаемся извлечь путь к функции
                    if tool.func and hasattr(tool.func, '__module__') and hasattr(tool.func, '__name__'):
                        full_path = f"{tool.func.__module__}.{tool.func.__name__}"
                        references.append(ToolReference(tool_id=full_path))
                    elif hasattr(tool, 'coroutine') and tool.coroutine:
                        # Для async @tool функций func=None, но есть coroutine
                        full_path = f"{tool.coroutine.__module__}.{tool.coroutine.__name__}"
                        references.append(ToolReference(tool_id=full_path))
                    else:
                        logger.warning(f"Не удалось извлечь путь к функции инструмента {tool.name}")
                        
                else:
                    logger.warning(f"Неизвестный тип инструмента при миграции: {type(tool)}. Пропускаем.")
                    
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
            module_path, class_name = agent_class_path.rsplit('.', 1)
            module = importlib.import_module(module_path)
            agent_class = getattr(module, class_name)
            
            if not issubclass(agent_class, BaseAgent):
                raise ValueError(f"Класс {agent_class_path} не является наследником BaseAgent")
            
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
            flow_config.updated_at = datetime.now(timezone.utc).isoformat()
            if not flow_config.created_at:
                flow_config.created_at = flow_config.updated_at
            
            await self.storage.set_flow_config(flow_config)
            logger.info(f"Флоу {flow_config.flow_id} успешно мигрирован")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка миграции флоу {flow_config.flow_id}: {e}")
            return False
    
    async def _find_tool_functions(self, package_name: str):
        """Находит все @tool функции в пакете"""
        tool_functions = []
        
        logger.info(f"🔧 Сканируем пакет: {package_name}")
        
        package = importlib.import_module(package_name)
        package_path = Path(package.__file__).parent
        
        logger.info(f"🔧 Путь к пакету: {package_path}")
        
        # Сканируем все .py файлы в пакете
        py_files = list(package_path.glob("*.py"))
        logger.info(f"🔧 Найдено {len(py_files)} .py файлов")
        
        for py_file in py_files:
            logger.info(f"🔧 Проверяем файл: {py_file.name}")
            
            if py_file.name.startswith("__"):
                logger.info(f"🔧 Пропускаем {py_file.name} (служебный)")
                continue
            
            module_name = f"{package_name}.{py_file.stem}"
            logger.info(f"🔧 Загружаем модуль: {module_name}")
            
            module = importlib.import_module(module_name)
            
            # Ищем StructuredTool объекты (результат @tool декоратора)
            all_members = inspect.getmembers(module)
            logger.info(f"🔧 Найдено {len(all_members)} объектов в {module_name}")
            
            for name, obj in all_members:
                # Пропускаем служебные объекты
                if name.startswith('_') or name in ['tool', 'operator', 're']:
                    continue
                
                logger.info(f"🔧 Проверяем объект: {name} ({type(obj).__name__})")
                
                # Ищем StructuredTool объекты
                if hasattr(obj, 'name') and hasattr(obj, 'description') and (hasattr(obj, 'func') or hasattr(obj, 'coroutine')):
                    # Это LangChain StructuredTool (результат @tool)
                    tool_type = "async" if (hasattr(obj, 'func') and obj.func is None and hasattr(obj, 'coroutine')) else "sync"
                    logger.info(f"🔧 ✅ Найден @tool ({tool_type}): {name} (tool.name={obj.name})")
                    tool_functions.append((obj, module_name))
                else:
                    logger.info(f"🔧 ❌ НЕ @tool: {name}")
                    
        logger.info(f"🔧 Итого найдено {len(tool_functions)} @tool функций")
        return tool_functions
    
    async def _create_tool_reference_from_function(self, tool_obj, module_name: str) -> ToolReference:
        """Создает ToolReference из StructuredTool объекта"""
        
        # Получаем исходный код оригинальной функции
        # Для sync тулов используем func, для async - coroutine
        target_func = None
        if hasattr(tool_obj, 'func') and tool_obj.func is not None:
            target_func = tool_obj.func
        elif hasattr(tool_obj, 'coroutine') and tool_obj.coroutine is not None:
            target_func = tool_obj.coroutine
        
        if target_func is None:
            raise ValueError(f"Не удалось найти исходную функцию для тула {tool_obj.name}")
        
        source_code = inspect.getsource(target_func)
        
        # Создаем function_path - используем имя переменной в модуле
        function_path = f"{module_name}.{tool_obj.name}"
        
        # Извлекаем параметры из args_schema
        params = {}
        if hasattr(tool_obj, 'args_schema') and tool_obj.args_schema:
            try:
                # Получаем поля из Pydantic модели
                if hasattr(tool_obj.args_schema, 'model_fields'):
                    for field_name, field_info in tool_obj.args_schema.model_fields.items():
                        params[field_name] = {
                            'type': str(field_info.annotation) if field_info.annotation else 'str',
                            'description': field_info.description or '',
                            'required': field_info.is_required() if hasattr(field_info, 'is_required') else True
                        }
            except Exception as e:
                logger.warning(f"Не удалось извлечь параметры для {tool_obj.name}: {e}")
        
        return ToolReference(
            tool_id=function_path,
            code_mode=CodeMode.CODE_REFERENCE,
            function_path=function_path,
            inline_code=source_code,  # Сохраняем код для возможности INLINE режима
            description=tool_obj.description or f"Инструмент {tool_obj.name}",
            params=params
        )
