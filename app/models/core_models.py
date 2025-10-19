"""
Pydantic модели для конфигурации агентов и флоу.
Это источник правды для Storage, Migrator и FlowFactory.
"""

from __future__ import annotations

from pydantic import BaseModel, field_validator
from typing import Optional, List, Dict, Any, TYPE_CHECKING, Union
from enum import Enum
from datetime import datetime, timezone
import json
import inspect
import hashlib
import logging
from pathlib import Path
from ..core.config import settings
from ..fields import Field
from ..core.slug_utils import generate_slug
from ..core.context import get_context

from .rag_models import AgentRAGConfig
from .types import HistorySource, PythonCode

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class NodeType(str, Enum):
    """Типы нод в графе"""

    AGENT_NODE = "agent_node"          # Вызов субагента
    TOOL_NODE = "tool_node"            # Вызов инструмента (обычный или MCP, различается по code_mode)
    FUNCTION_NODE = "function_node"    # Вызов функции (обычная функция)
    ROUTER_NODE = "router_node"        # Функция-роутер для условных переходов
    FLOW_NODE = "flow_node"            # Вызов другого flow
    MESSAGE_NODE = "message_node"      # Отправка фиксированного сообщения


class AgentType(str, Enum):
    """Типы агентов"""

    REACT = "react"
    STATEGRAPH = "stategraph"


class CodeMode(str, Enum):
    """Режим хранения кода"""

    CODE_REFERENCE = "code_reference"  # Ссылка на код в файлах
    INLINE_CODE = "inline_code"        # Код хранится в БД
    MCP_TOOL = "mcp_tool"              # Внешний MCP инструмент (HTTP/SSE)


class ConditionType(str, Enum):
    """Типы условий в графе"""

    ROUTER = "router"  # Функция возвращает ID следующей ноды
    EXPRESSION = "expression"  # Простое условное выражение (true/false)


class GraphNode(BaseModel):
    """Нода в графе"""

    id: str = Field(
        title="ID ноды",
        description="Уникальный идентификатор ноды в графе",
        readonly=True,
    )
    type: NodeType = Field(title="Тип ноды", description="Тип ноды в графе")
    params: Dict[str, Any] = Field(
        default_factory=dict,
        title="Параметры",
        description="Параметры ноды",
    )

    # Режим хранения кода ноды
    code_mode: CodeMode = Field(
        default=CodeMode.CODE_REFERENCE,
        title="Режим кода",
        description="Режим хранения кода ноды",
    )

    # Для CODE_REFERENCE режима
    function_class: Optional[str] = Field(
        default=None,
        title="Класс функции",
        description="Путь к классу агента",
        placeholder="app.agents.calculator.CalculatorAgent",
    )
    function_path: Optional[str] = Field(
        default=None,
        title="Путь к функции",
        description="Путь к функции",
        placeholder="app.tools.calc_tools.add_numbers",
    )

    # Для INLINE_CODE режима
    inline_code: Optional[str] = Field(
        default=None,
        title="Инлайн код",
        description="Python код ноды",
        widget_attrs={"rows": 10, "class": "code-editor"},
    )
    prompt: Optional[str] = Field(
        default='.',
        title="Промпт",
        description="Промпт для ReAct нод",
        widget_attrs={"rows": 5},
    )

    # Маппинг данных
    input_mapping: Optional[Dict[str, str]] = Field(
        default=None,
        title="Маппинг входных данных",
        description="Как брать данные из state",
    )
    output_mapping: Optional[Dict[str, str]] = Field(
        default=None,
        title="Маппинг выходных данных",
        description="Как сохранять результат в state",
    )


class GraphEdge(BaseModel):
    """Ребро в графе"""

    source: str = Field(title="Источник", description="ID исходной ноды")
    target: str = Field(title="Цель", description="ID целевой ноды")
    condition: Optional[str] = Field(
        default=None,
        title="Условие",
        description="Условие или выражение для перехода (только для ROUTER и EXPRESSION)",
        widget_attrs={"rows": 3},
    )
    condition_type: Optional[ConditionType] = Field(
        default=None,
        title="Тип условия",
        description="Тип условия для перехода (None = обычное ребро, ROUTER = функция-роутер, EXPRESSION = булево выражение)",
    )


class BuilderEntity(BaseModel):
    """Базовая модель для всех сущностей Builder с автоматическим преобразованием типов"""
    
    model_config = {"str_strip_whitespace": True}
    
    # Метаданные - общие для всех сущностей
    source: str = Field(
        default="manual",
        title="Источник",
        description="Источник создания (manual, migration, canvas_created)",
        readonly=True,
    )
    created_at: Optional[datetime] = Field(
        default=None, title="Создан", description="Дата создания", readonly=True
    )
    updated_at: Optional[datetime] = Field(
        default=None, title="Обновлен", description="Дата обновления", readonly=True
    )
    
    @staticmethod
    def parse_json_string(v: Any) -> Any:
        """Преобразует JSON строку в dict/list"""
        if isinstance(v, str) and v.strip():
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return v
        return v if v else None


class GraphDefinition(BaseModel):
    """Определение графа"""

    nodes: List[GraphNode] = Field(
        title="Ноды",
        description="Список нод в графе",
    )
    edges: List[GraphEdge] = Field(
        title="Ребра",
        description="Список ребер в графе",
    )
    entry_point: str = Field(
        title="Точка входа",
        description="ID ноды, с которой начинается выполнение графа",
    )
    
    @classmethod
    async def migrate(cls, source) -> Optional["GraphDefinition"]:
        """
        Создает GraphDefinition из различных источников.
        
        Поддерживает:
        - Класс BaseAgent → анализирует build_graph() и создает GraphDefinition
        - StateGraph объект → извлекает ноды и ребра
        - None → возвращает None (ReAct агент)
        
        Args:
            source: Класс агента или StateGraph объект
            
        Returns:
            GraphDefinition или None
        """
        
        if source is None:
            return None
        
        if hasattr(source, 'nodes') and hasattr(source, 'edges'):
            return await cls._migrate_from_stategraph(source)
        
        if inspect.isclass(source):
            return await cls._migrate_from_agent_class(source)
        
        return None
    
    @classmethod
    async def _migrate_from_agent_class(cls, agent_class) -> Optional["GraphDefinition"]:
        """Извлекает GraphDefinition из класса агента"""
        logger.info(f"🔍 Анализируем граф агента {agent_class.__name__}")
        
        if hasattr(agent_class, "graph_definition") and agent_class.graph_definition:
            logger.info("🔍 Найден статический graph_definition в классе")
            return agent_class.graph_definition
        
        temp_config = AgentConfig(
            agent_id=f"{agent_class.__module__}.{agent_class.__name__}",
            name="temp",
            description="temp",
        )
        
        try:
            agent_instance = agent_class(temp_config)
            
            if not hasattr(agent_instance, "build_graph"):
                logger.info(f"🔍 Агент {agent_class.__name__} - простой ReAct агент (нет StateGraph)")
                return None
            
            langgraph_graph = agent_instance.build_graph()
            
            if not langgraph_graph:
                logger.info(f"🔍 build_graph() вернул None для {agent_class.__name__}")
                return None
            
            logger.info(f"🔍 Найден StateGraph: {type(langgraph_graph)}")
            
            if hasattr(langgraph_graph, "nodes"):
                logger.info(f"🔍 Найдены nodes: {list(langgraph_graph.nodes.keys())}")
            
            if hasattr(langgraph_graph, "edges"):
                logger.info(f"🔍 Найдены edges: {langgraph_graph.edges}")
            
            return await cls._migrate_from_stategraph(langgraph_graph)
            
        except Exception as e:
            logger.warning(f"Не удалось проанализировать граф {agent_class.__name__}: {e}")
            return None
    
    @classmethod
    async def _migrate_from_stategraph(cls, stategraph) -> "GraphDefinition":
        """
        Извлекает GraphDefinition из LangGraph StateGraph.
        
        Args:
            stategraph: StateGraph объект из LangGraph
            
        Returns:
            GraphDefinition с нодами и ребрами
        """
        nodes = []
        edges = []
        
        logger.info(f"🔍 Анализируем StateGraph с {len(stategraph.nodes)} нодами")
        
        for node_id, node_spec in stategraph.nodes.items():
            node_func = node_spec
            
            if hasattr(node_spec, 'runnable'):
                runnable = node_spec.runnable
                if hasattr(runnable, 'afunc') and runnable.afunc:
                    node_func = runnable.afunc
                elif hasattr(runnable, 'func') and runnable.func:
                    node_func = runnable.func
                else:
                    node_func = runnable
            elif hasattr(node_spec, '__wrapped__'):
                node_func = node_spec.__wrapped__
            elif hasattr(node_spec, 'func'):
                node_func = node_spec.func
            
            node_type = cls._determine_node_type(node_func)
            
            function_path = None
            function_class = None
            
            if node_type == NodeType.FUNCTION_NODE:
                if hasattr(node_func, '__module__') and hasattr(node_func, '__name__'):
                    function_path = f"{node_func.__module__}.{node_func.__name__}"
            elif node_type == NodeType.AGENT_NODE:
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
        
        for source, target in stategraph.edges:
            if source == "__start__":
                source = "START"
            if target == "__end__":
                target = "END"
            
            edges.append(GraphEdge(source=source, target=target))
        
        if hasattr(stategraph, 'branches') and stategraph.branches:
            for source, branches_dict in stategraph.branches.items():
                source_name = "START" if source == "__start__" else source
                
                for cond_name, branch_spec in branches_dict.items():
                    condition_path = None
                    if hasattr(branch_spec, 'path'):
                        cond_runnable = branch_spec.path
                        cond_func = None
                        if hasattr(cond_runnable, 'afunc') and cond_runnable.afunc:
                            cond_func = cond_runnable.afunc
                        elif hasattr(cond_runnable, 'func') and cond_runnable.func:
                            cond_func = cond_runnable.func
                        
                        if cond_func and hasattr(cond_func, '__module__') and hasattr(cond_func, '__name__'):
                            condition_path = f"{cond_func.__module__}.{cond_func.__name__}"
                    
                    if hasattr(branch_spec, 'ends') and branch_spec.ends:
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
        
        return cls(nodes=nodes, edges=edges, entry_point="START")
    
    @staticmethod
    def _determine_node_type(node_func) -> NodeType:
        """Определяет тип ноды по функции"""
        if hasattr(node_func, '__name__'):
            # Проверяем является ли это методом класса агента
            if hasattr(node_func, '__self__'):
                # Это bound method агента
                return NodeType.AGENT_NODE
            
            # Если это свободная функция с "_function" в имени - это FUNCTION_NODE
            if "_function" in node_func.__name__ or node_func.__name__.endswith("_function"):
                return NodeType.FUNCTION_NODE
            
            # Если это свободная функция с "_node" в имени - тоже FUNCTION_NODE
            if "_node" in node_func.__name__ or node_func.__name__.endswith("_node"):
                return NodeType.FUNCTION_NODE
            
            # По умолчанию свободная функция = FUNCTION_NODE
            # AGENT_NODE только если это метод агента (с __self__)
            return NodeType.FUNCTION_NODE
        
        return NodeType.FUNCTION_NODE


class ToolReference(BuilderEntity):
    """Ссылка на инструмент"""

    class Config:
        storage_prefix = "tool"

    tool_id: str = Field(
        frozen=True,
        title="ID инструмента",
        description="ID инструмента (путь к функции, ID агента, MCP tool)",
        pattern=r"^[a-zA-Z0-9_.:/-]+$",
    )
    title: Optional[str] = Field(
        default=None,
        title="Название",
        description="Название для отображения в UI",
        placeholder="Красивое название функции"
    )
    group: Optional[str] = Field(
        default=None,
        title="Группа",
        description="Группа тулов для UI группировки",
        placeholder="Коммуникации, Анализ данных, Погода..."
    )
    params: Dict[str, Any] = Field(
        default_factory=dict,
        title="Параметры",
        description="Параметры инструмента",
    )

    # Новые поля для поддержки inline кода
    code_mode: CodeMode = Field(
        default=CodeMode.CODE_REFERENCE,
        title="Режим кода",
        description="Режим хранения кода инструмента",
    )
    function_path: Optional[str] = Field(
        default=None,
        title="Путь к функции",
        description="Путь к функции для CODE_REFERENCE",
        placeholder="app.tools.calc_tools.add_numbers",
    )
    inline_code: Optional[PythonCode] = Field(
        default=None,
        title="Инлайн код",
        description="Python код для INLINE_CODE режима",
    )
    description: Optional[str] = Field(
        default=None,
        title="Описание",
        description="Описание инструмента",
        widget_attrs={"rows": 3},
    )
    
    # Поля для биллинга и доступа
    cost: float = Field(
        default=0.0,
        title="Стоимость",
        description="Стоимость вызова инструмента в RUB",
        ge=0.0,
        widget_attrs={"step": "0.001", "placeholder": "0.001"}
    )
    billing_name: Optional[str] = Field(
        default=None,
        title="Название для биллинга",
        description="Название для учета использования (по умолчанию tool_id)",
        placeholder="weather_api"
    )
    free_for_plans: List[str] = Field(
        default_factory=list,
        title="Бесплатно для планов",
        description="Тарифные планы для которых инструмент бесплатен",
        widget_attrs={"multiple": True}
    )
    tariff_limits: Dict[str, int] = Field(
        default_factory=dict,
        title="Лимиты по тарифам",
        description="Лимиты использования по тарифным планам (-1 = без лимитов, 0 = запрещено)",
        widget_attrs={"rows": 4, "placeholder": '{"free": 10, "basic": 100, "premium": -1}'}
    )
    is_public: bool = Field(
        default=False,
        title="Публичный",
        description="Доступен ли инструмент в публичном редакторе ботов"
    )
    
    @classmethod
    async def migrate(cls, source, migrator=None) -> "ToolReference":
        """
        Мигрирует tool из кода в БД.
        
        Поддерживает:
        - Строка (tool_id) → загружает из кода и мигрирует
        - Функция/StructuredTool → создает ToolReference
        
        Args:
            source: tool_id (строка) или функция/StructuredTool
            migrator: Экземпляр Migrator (нужен только для сохранения в БД)
            
        Returns:
            ToolReference
        """
        if isinstance(source, str):
            if "." not in source:
                raise ValueError(f"tool_id должен быть полным путем к функции: {source}")
            
            module_path, func_name = source.rsplit(".", 1)
            module = __import__(module_path, fromlist=[func_name])
            tool_obj = getattr(module, func_name)
            module_name_for_ref = module_path
        else:
            tool_obj = source
            target_func = None
            if hasattr(source, 'func') and source.func is not None:
                target_func = source.func
            elif hasattr(source, 'coroutine') and source.coroutine is not None:
                target_func = source.coroutine
            else:
                target_func = source
            
            module_name_for_ref = target_func.__module__ if hasattr(target_func, '__module__') else None
        
        tool_ref = cls._from_function(func=tool_obj, module_name=module_name_for_ref)
        
        if migrator:
            await migrator.storage.set(f"tool:{tool_ref.tool_id}", tool_ref.model_dump_json())
        
        return tool_ref
    
    @classmethod
    def _from_function(
        cls, 
        func: callable, 
        module_name: Optional[str] = None,
        tool_id: Optional[str] = None, 
        description: Optional[str] = None
    ) -> "ToolReference":
        """
        Создает ToolReference из StructuredTool или обычной функции.
        
        Универсальный метод для преобразования функций в ToolReference.
        Используется в validators FlowConfig и в Migrator.
        
        Args:
            func: StructuredTool объект или обычная функция
            module_name: Имя модуля (для StructuredTool)
            tool_id: ID инструмента (опционально, для обычных функций)
            description: Описание (опционально, для обычных функций)
            
        Returns:
            ToolReference с кодом функции
        """
        is_structured_tool = hasattr(func, "func") or hasattr(func, "coroutine")
        
        if is_structured_tool:
            target_func = None
            if hasattr(func, "func") and func.func is not None:
                target_func = func.func
            elif hasattr(func, "coroutine") and func.coroutine is not None:
                target_func = func.coroutine

            if target_func is None:
                raise ValueError(f"Не удалось найти исходную функцию для тула {func.name}")

            source_code = inspect.getsource(target_func)
            function_path = f"{module_name}.{func.name}"

            params = {}
            if hasattr(func, "args_schema") and func.args_schema:
                if hasattr(func.args_schema, "model_fields"):
                    for field_name, field_info in func.args_schema.model_fields.items():
                        params[field_name] = {
                            "type": str(field_info.annotation) if field_info.annotation else "str",
                            "description": field_info.description or "",
                            "required": field_info.is_required() if hasattr(field_info, "is_required") else True,
                        }

            platform_title = getattr(func, '_platform_title', None)
            platform_group = getattr(func, '_platform_group', None)
            platform_cost = getattr(func, '_platform_cost', 0.0)
            platform_billing_name = getattr(func, '_platform_billing_name', None)
            platform_free_for_plans = getattr(func, '_platform_free_for_plans', [])
            platform_is_public = getattr(func, '_platform_is_public', False)

            return cls(
                tool_id=function_path,
                title=platform_title,
                group=platform_group,
                code_mode=CodeMode.CODE_REFERENCE,
                function_path=function_path,
                inline_code=source_code,
                description=func.description or f"Инструмент {func.name}",
                params=params,
                cost=platform_cost,
                billing_name=platform_billing_name,
                free_for_plans=platform_free_for_plans,
                tariff_limits={},
                is_public=platform_is_public,
            )
        else:
            if not callable(func):
                raise ValueError(f"Объект {func} не является функцией или StructuredTool")
            
            source_code = inspect.getsource(func)
            
            return cls(
                tool_id=tool_id or f"{func.__module__}.{func.__name__}",
                code_mode=CodeMode.INLINE_CODE,
                inline_code=source_code,
                description=description or f"Функция {func.__name__}"
            )


class LLMConfig(BaseModel):
    """Конфигурация LLM для агента"""

    model: str = Field(
        default="anthropic/claude-sonnet-4.5",
        title="Модель",
        description="ID модели в формате provider/model (через OpenRouter)",
        placeholder="anthropic/claude-sonnet-4.5, google/gemini-2.5-flash, openai/gpt-4o",
    )
    temperature: float = Field(
        default=0.2,
        title="Температура",
        description="Температура для генерации (0.0-1.0)",
        ge=0.0,
        le=1.0,
    )
    max_tokens: Optional[int] = Field(
        default=None,
        title="Максимум токенов в ответе",
        description="Максимальное количество токенов в ответе модели",
        ge=1,
    )
    
    context_window: Optional[int] = Field(
        default=None,
        title="Размер контекстного окна",
        description="Максимальное количество токенов на входе (если None - из глобальной конфигурации модели)",
        ge=1000,
    )
    summarization_threshold: float = Field(
        default=0.8,
        title="Порог суммаризации (%)",
        description="При каком проценте заполненности контекста начинать суммаризацию (0.5-1.0)",
        ge=0.5,
        le=1.0,
    )
    summarization_target: float = Field(
        default=0.2,
        title="Целевой размер после суммаризации (%)",
        description="До какого процента от context_window сжимать диалог (0.1-0.5)",
        ge=0.1,
        le=0.5,
    )
    enable_auto_summarization: bool = Field(
        default=True,
        title="Автосуммаризация",
        description="Автоматически суммаризировать диалог при достижении порога",
    )


class AgentConfig(BuilderEntity):
    """Конфигурация агента"""

    class Config:
        storage_prefix = "agent"

    agent_id: str = Field(
        ...,
        frozen=True,
        title="ID агента",
        description="Уникальный идентификатор агента",
        readonly=True,
    )
    name: str = Field(
        title="Название", description="Название агента", placeholder="Мой агент"
    )
    title: Optional[str] = Field(
        default=None,
        title="Название для UI",
        description="Название для отображения в списке способностей (по умолчанию name)",
        placeholder="Красивое название агента"
    )
    description: Optional[str] = Field(
        default=None,
        title="Описание",
        description="Описание агента",
        widget_attrs={"rows": 4},
    )
    type: AgentType = Field(
        default=AgentType.REACT,
        title="Тип агента",
        description="Тип агента (ReAct или StateGraph). Автоматически определяется по graph_definition",
        readonly=True,
    )
    
    @field_validator('type', mode='before')
    @classmethod
    def auto_determine_type(cls, v, info):
        """Автоматически определяет тип агента на основе graph_definition"""
        data = info.data
        
        # Если graph_definition есть → StateGraph
        if data.get('graph_definition'):
            return AgentType.STATEGRAPH
        
        # Если передан тип явно, используем его
        if v:
            return v
            
        # По умолчанию ReAct
        return AgentType.REACT
    
    def __init__(self, **data):
        """Инициализация с автоопределением типа"""
        # Если type не передан, но есть graph_definition → STATEGRAPH
        if 'type' not in data and data.get('graph_definition'):
            data['type'] = AgentType.STATEGRAPH
        super().__init__(**data)

    # Режим хранения кода
    code_mode: CodeMode = Field(
        default=CodeMode.CODE_REFERENCE,
        title="Режим кода",
        description="Режим хранения кода агента",
    )

    # Для CODE_REFERENCE режима
    function_class: Optional[str] = Field(
        default=None,
        title="Класс агента",
        description="Путь к классу-наследнику BaseAgent",
        placeholder="app.agents.calculator.CalculatorAgent",
    )

    # Для INLINE_CODE режима
    inline_code: Optional[str] = Field(
        default=None,
        title="Инлайн код",
        description="Python код агента",
        widget_attrs={"rows": 15, "class": "code-editor"},
    )

    # Поля для ReAct агентов
    prompt: Optional[str] = Field(
        default=None,
        title="Промпт",
        description="Системный промпт для ReAct агента (используйте {variable} для подстановки)",
        widget_attrs={"rows": 8},
    )

    # Поля для StateGraph агентов
    graph_definition: Optional[GraphDefinition] = Field(
        default=None,
        title="Определение графа",
        description="Определение графа для StateGraph агента",
    )

    # Общие поля
    tools: List[ToolReference] = Field(
        default_factory=list,
        title="Инструменты",
        description="Список инструментов агента",
    )
    llm_config: Optional[LLMConfig] = Field(
        default=None,
        title="Конфигурация LLM",
        description="Конфигурация языковой модели",
    )

    # История диалогов
    history_from: Optional[HistorySource] = Field(
        default=None,
        title="История от",
        description="Источник истории диалогов (global, список агентов или None)",
        placeholder="global или agent1,agent2",
    )
    
    # Локальные переменные агента
    local_variables: Dict[str, Any] = Field(
        default_factory=dict,
        title="Локальные переменные",
        description="Переменные доступные только в этом агенте (перекрывают переменные flow)",
        widget_attrs={"rows": 4, "placeholder": '{"max_attempts": 3, "greeting": "Привет!"}'}
    )
    
    # Начальные данные store для агента
    store: Dict[str, Any] = Field(
        default_factory=dict,
        title="Session Store",
        description="Начальные значения для state.store (доступны через {store.key} или session_get)",
        widget_attrs={"rows": 4, "placeholder": '{"max_attempts": 3, "welcome_shown": false}'}
    )
    
    # Публичность агента
    is_public: bool = Field(
        default=False,
        title="Публичный",
        description="Доступен ли агент как инструмент в публичном редакторе ботов"
    )
    
    @field_validator('local_variables', 'store', mode='before')
    @classmethod
    def parse_json_fields(cls, v):
        """Автоматически парсит JSON строки в dict"""
        if isinstance(v, str) and v.strip():
            import json
            return json.loads(v)
        return v if v else {}
    
    @field_validator('tools', mode='before')
    @classmethod
    def convert_tools_to_references(cls, v):
        """
        Преобразует список tools в ToolReference.
        
        Поддерживает:
        - dict → создает ToolReference из dict (при загрузке из JSON)
        - ToolReference → как есть
        - Функции → ToolReference с tool_id=путь
        - Классы → ToolReference с tool_id=путь
        - Строки (mcp:, agent:) → ToolReference как есть
        - StructuredTool → ToolReference с извлечением кода
        - BaseAgent экземпляры → ToolReference с tool_id=путь к классу
        """
        if not v:
            return []
        
        references = []
        
        for tool in v:
            # Если это dict (загрузка из JSON), создаем ToolReference
            if isinstance(tool, dict):
                references.append(ToolReference(**tool))
            
            elif isinstance(tool, ToolReference):
                references.append(tool)
            
            elif inspect.isfunction(tool) or inspect.ismethod(tool):
                full_path = f"{tool.__module__}.{tool.__name__}"
                references.append(ToolReference(tool_id=full_path))
            
            elif inspect.isclass(tool):
                full_path = f"{tool.__module__}.{tool.__name__}"
                references.append(ToolReference(tool_id=full_path))
            
            elif isinstance(tool, str) and (tool.startswith("mcp:") or tool.startswith("agent:")):
                references.append(ToolReference(tool_id=tool))
            
            elif hasattr(tool, "__class__"):
                from app.agents.base import BaseAgent
                if issubclass(tool.__class__, BaseAgent):
                    agent_class = tool.__class__
                    full_path = f"{agent_class.__module__}.{agent_class.__name__}"
                    references.append(ToolReference(tool_id=full_path))
                elif hasattr(tool, "name") and (hasattr(tool, "func") or hasattr(tool, "coroutine")):
                    if tool.func and hasattr(tool.func, "__module__"):
                        full_path = f"{tool.func.__module__}.{tool.func.__name__}"
                        references.append(ToolReference(tool_id=full_path))
                    elif hasattr(tool, "coroutine") and tool.coroutine:
                        full_path = f"{tool.coroutine.__module__}.{tool.coroutine.__name__}"
                        references.append(ToolReference(tool_id=full_path))
                    else:
                        raise ValueError(f"Неизвестный тип инструмента: {type(tool)}")
            else:
                raise ValueError(f"Неизвестный тип инструмента: {type(tool)}")
        
        return references
    
    @classmethod
    async def migrate(cls, agent_id: str, migrator, with_tools: bool = True) -> "AgentConfig":
        """
        Мигрирует агента из кода в БД с зависимостями.
        
        1. Загружает класс агента из кода по agent_id
        2. Создает AgentConfig через from_class
        3. Сохраняет в БД
        4. Если with_tools=True, рекурсивно мигрирует все tools
        5. Возвращает AgentConfig
        
        Args:
            agent_id: Путь к классу (например, "app.agents.calculator.agent.CalculatorAgent")
            migrator: Экземпляр Migrator для доступа к вспомогательным методам
            with_tools: Мигрировать ли tools агента рекурсивно
            
        Returns:
            Мигрированный AgentConfig
        """
        if not agent_id or "." not in agent_id:
            raise ValueError(f"agent_id должен быть полным путем к классу: {agent_id}")
        
        module_path, class_name = agent_id.rsplit(".", 1)
        module = __import__(module_path, fromlist=[class_name])
        agent_class = getattr(module, class_name)
        
        # Проверяем что это класс, а не готовый AgentConfig
        if isinstance(agent_class, cls):
            # Это уже готовый AgentConfig (например, test_stategraph_agent_config)
            agent_config = agent_class
            logger.info(f"✅ Найден готовый AgentConfig: {agent_id}")
        else:
            # Это класс агента, нужно создать конфиг
            agent_config = await cls.from_class(agent_class=agent_class)
        
        await migrator.persister.save_agent(agent_config)
        
        from ..services.variables_service import get_variables_service
        variables_service = get_variables_service()
        
        if agent_config.local_variables:
            await variables_service.resolve(agent_config.local_variables, auto_create=True)
        
        if agent_config.store:
            await variables_service.resolve(agent_config.store, auto_create=True)
        
        if with_tools:
            for tool_ref in agent_config.tools:
                tool_id = tool_ref.tool_id
                
                if tool_id.startswith("agent:"):
                    await cls.migrate(tool_id.replace("agent:", ""), migrator, with_tools=True)
                elif "." in tool_id and not tool_id.startswith("mcp:"):
                    if ".agent." in tool_id or ".Agent" in tool_id:
                        await cls.migrate(tool_id, migrator, with_tools=True)
                    else:
                        await ToolReference.migrate(tool_id, migrator)
        
        # Мигрируем субагенты из graph_definition (для StateGraph агентов)
        if with_tools and agent_config.graph_definition:
            for node in agent_config.graph_definition.nodes:
                if node.type == NodeType.AGENT_NODE:
                    sub_agent_id = node.params.get("agent_id")
                    if sub_agent_id and "." in sub_agent_id:
                        logger.info(f"🔄 Рекурсивная миграция субагента из ноды: {sub_agent_id}")
                        await cls.migrate(sub_agent_id, migrator, with_tools=True)
        
        return agent_config
    
    @classmethod
    async def from_class(cls, agent_class):
        """
        Создает AgentConfig из класса BaseAgent.
        
        Извлекает все атрибуты класса и создает AgentConfig.
        Рекурсивно вызывает GraphDefinition.migrate для анализа графа.
        
        Args:
            agent_class: Класс наследник BaseAgent
            
        Returns:
            AgentConfig созданный из класса
        """
        name = getattr(agent_class, "name", agent_class.__name__)
        title = getattr(agent_class, "title", None)
        agent_id = f"{agent_class.__module__}.{agent_class.__name__}"
        description = getattr(agent_class, "description", None)
        prompt = getattr(agent_class, "prompt", None)
        raw_tools = getattr(agent_class, "tools", [])
        raw_llm_config = getattr(agent_class, "llm_config", None)
        history_from = getattr(agent_class, "history_from", None)
        is_public = getattr(agent_class, "is_public", False)
        local_variables = getattr(agent_class, "local_variables", {})
        store = getattr(agent_class, "store", {})
        
        graph_definition = await GraphDefinition.migrate(agent_class)
        
        llm_config = None
        if raw_llm_config:
            if isinstance(raw_llm_config, dict):
                llm_config = LLMConfig(**raw_llm_config)
            elif isinstance(raw_llm_config, LLMConfig):
                llm_config = raw_llm_config
        
        return cls(
            agent_id=agent_id,
            name=name,
            title=title,
            description=description,
            function_class=f"{agent_class.__module__}.{agent_class.__name__}",
            prompt=prompt,
            graph_definition=graph_definition,
            tools=raw_tools,
            llm_config=llm_config,
            history_from=history_from,
            is_public=is_public,
            local_variables=local_variables,
            store=store,
            source="migration",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )


class FlowAuthor(BaseModel):
    """Информация об авторе flow"""

    name: str = Field(
        default="Agent Lab",
        title="Имя",
        description="Имя автора или организации"
    )
    email: Optional[str] = Field(
        default=None,
        title="Email",
        description="Email для связи"
    )
    website: Optional[str] = Field(
        default=None,
        title="Сайт",
        description="Веб-сайт автора"
    )
    github: Optional[str] = Field(
        default=None,
        title="GitHub",
        description="GitHub профиль или репозиторий"
    )
    linkedin: Optional[str] = Field(
        default=None,
        title="LinkedIn",
        description="LinkedIn профиль"
    )
    twitter: Optional[str] = Field(
        default=None,
        title="Twitter",
        description="Twitter профиль"
    )


class VariableDefinition(BaseModel):
    """Определение переменной с описанием для установки flow"""

    key: str = Field(
        title="Ключ переменной",
        description="Имя переменной в формате @var:key"
    )
    description: str = Field(
        title="Описание",
        description="Описание переменной для пользователя"
    )
    default_value: Optional[str] = Field(
        default=None,
        title="Значение по умолчанию",
        description="Предлагаемое значение по умолчанию"
    )
    is_secret: bool = Field(
        default=False,
        title="Секретная переменная",
        description="Переменная содержит чувствительные данные"
    )
    required: bool = Field(
        default=True,
        title="Обязательная",
        description="Требуется ли заполнить переменную при установке"
    )


# Type alias для гибкого определения переменных
VariableDefinitionInput = Union[VariableDefinition, Dict[str, Any]]


class FlowConfig(BuilderEntity):
    """Конфигурация флоу - простая административная сущность"""

    class Config:
        storage_prefix = "flow"
        arbitrary_types_allowed = True

    flow_id: Optional[str] = Field(
        default=None,
        frozen=True,
        title="ID флоу",
        description="Уникальный идентификатор флоу",
        readonly=True,
    )
    name: str = Field(
        title="Название", description="Название флоу", placeholder="Мой флоу"
    )
    description: Optional[str] = Field(
        default=None,
        title="Описание",
        description="Описание флоу",
        widget_attrs={"rows": 4},
    )

    # Точка входа - агент который обрабатывает запросы
    entry_point_agent: Any = Field(
        title="Агент точки входа",
        description="ID агента или класс агента который обрабатывает запросы",
        placeholder="app.agents.calculator.agent.CalculatorAgent",
    )

    # Платформы на которых работает flow с настройками
    platforms: Dict[str, Dict[str, Any]] = Field(
        default_factory=lambda: {"api": {}},
        title="Платформы",
        description="Платформы на которых работает флоу с настройками",
    )

    # Настройки выполнения
    timeout: Optional[int] = Field(
        default=None, title="Таймаут", description="Таймаут выполнения в секундах", ge=1
    )
    max_retries: int = Field(
        default=0,
        title="Максимум повторов",
        description="Максимальное количество повторов при ошибке",
        ge=0,
    )
    
    # Переменные флоу
    variables: Dict[str, Any] = Field(
        default_factory=dict,
        title="Переменные",
        description="Переменные доступные во всех агентах флоу (используйте {variable} в промптах)",
        widget_attrs={"rows": 6, "placeholder": '{"bot_name": "Помощник", "timeout_minutes": 30}'}
    )

    # Определения переменных для установки flow из store
    variables_definitions: List[VariableDefinitionInput] = Field(
        default_factory=list,
        title="Определения переменных",
        description="Переменные которые нужно заполнить при установке flow из store (словари или VariableDefinition объекты)"
    )

    @field_validator('variables_definitions', mode='before')
    @classmethod
    def validate_variables_definitions(cls, value):
        """Валидирует и конвертирует определения переменных"""
        if not isinstance(value, list):
            return []

        validated = []
        for item in value:
            if isinstance(item, dict):
                # Конвертируем dict в VariableDefinition (Pydantic сам кинет ValidationError если невалидно)
                var_def = VariableDefinition(**item)
                validated.append(var_def)
            elif isinstance(item, VariableDefinition):
                validated.append(item)
            else:
                raise ValueError(f"Unsupported variable definition type: {type(item)}")

        return validated

    @field_validator('variables_definitions', mode='after')
    @classmethod
    def validate_variables_usage(cls, value, info):
        """Проверяет что переменные из definitions используются в flow"""
        if not value or not hasattr(info.data, 'get'):
            return value

        flow_data = info.data

        # Собираем все @var: ссылки из flow
        var_usage = set()

        def collect_vars(obj):
            if isinstance(obj, str) and obj.startswith('@var:'):
                var_usage.add(obj[5:])  # Убираем @var: префикс
            elif isinstance(obj, dict):
                for v in obj.values():
                    collect_vars(v)
            elif isinstance(obj, list):
                for v in obj:
                    collect_vars(v)

        # Ищем @var: ссылки в variables, store, platforms
        if 'variables' in flow_data:
            collect_vars(flow_data['variables'])
        if 'store' in flow_data:
            collect_vars(flow_data['store'])
        if 'platforms' in flow_data:
            collect_vars(flow_data['platforms'])

        # Проверяем что все переменные из definitions используются
        defined_vars = {vd.key for vd in value}
        unused_vars = defined_vars - var_usage

        if unused_vars:
            logger.warning(f"Flow {flow_data.get('name', 'unknown')} has unused variables in definitions: {unused_vars}")

        return value

    # Начальные данные store
    store: Dict[str, Any] = Field(
        default_factory=dict,
        title="Начальные данные store",
        description="Начальные значения для state.store (доступны во всех агентах через {store.key} или session_get)",
        widget_attrs={"rows": 6, "placeholder": '{"max_attempts": 3, "welcome_shown": false}'}
    )
    
    # Reasoning от LLM
    enable_reasoning: bool = Field(
        default=False,
        title="Включить Reasoning",
        description="Отправлять промежуточные размышления LLM (reasoning) пользователю в реальном времени",
    )
    
    # RAG конфигурация для flow
    rag_config: Optional[AgentRAGConfig] = Field(
        default_factory=lambda: AgentRAGConfig(
            enabled=True,
            namespace_scope="flow",
            search_scopes=["flow"],
            auto_index_messages=False
        ),
        title="RAG конфигурация",
        description="Настройки базы знаний для агентов в этом flow"
    )
    
    # Публичность
    is_public: bool = Field(
        default=False,
        title="Публичный",
        description="Доступен ли flow для копирования в новые компании"
    )
    
    # Store поля
    author: Optional[FlowAuthor] = Field(
        default_factory=lambda: FlowAuthor(),
        title="Автор",
        description="Информация об авторе flow"
    )
    
    image_path: Optional[str] = Field(
        default=None,
        title="Путь к картинке",
        description="Путь к картинке flow в проекте (для миграции)"
    )
    
    image_file_id: Optional[str] = Field(
        default=None,
        title="ID файла картинки",
        description="ID файла в S3 после загрузки",
        exclude_from_form=True
    )
    
    install_hook: Optional[ToolReference] = Field(
        default=None,
        title="Хук установки",
        description="ToolReference для установки flow"
    )
    
    after_install_hook: Optional[ToolReference] = Field(
        default=None,
        title="Хук после установки",
        description="ToolReference который выполняется после установки. Может вернуть URL для открытия в новом окне"
    )
    
    uninstall_hook: Optional[ToolReference] = Field(
        default=None,
        title="Хук удаления",
        description="ToolReference для удаления flow"
    )

    # Данные канваса Builder
    canvas_data: Optional[Dict[str, Any]] = Field(
        default=None,
        title="Данные канваса",
        description="Позиции элементов и связи на канвасе Builder",
        exclude_from_form=True,
    )
    
    @field_validator('platforms', 'canvas_data', 'variables', 'store', mode='before')
    @classmethod
    def parse_json_fields(cls, v):
        """Автоматически парсит JSON строки в dict"""
        if isinstance(v, str) and v.strip():
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return v
        return v if v else ({"api": {}} if v is None else v)
    
    @field_validator('timeout', mode='before')
    @classmethod
    def parse_timeout(cls, v):
        """Преобразует пустую строку в None для timeout"""
        if isinstance(v, str) and v.strip() == "":
            return None
        return v
    
    @field_validator('max_retries', mode='before')
    @classmethod
    def parse_max_retries(cls, v):
        """Преобразует пустую строку в 0 для max_retries"""
        if isinstance(v, str) and v.strip() == "":
            return 0
        return v
    
    @field_validator('rag_config', mode='before')
    @classmethod
    def ensure_rag_config(cls, v):
        """Создаёт дефолтный RAG конфиг если он None (для старых flow)"""
        if v is None:
            return AgentRAGConfig(
                enabled=True,
                namespace_scope="flow",
                search_scopes=["flow"],
                auto_index_messages=False
            )
        return v
    
    @field_validator('entry_point_agent', mode='before')
    @classmethod
    def convert_entry_point_agent(cls, v):
        """
        Преобразует класс агента в строку с путем.
        
        Поддерживает:
        - Класс агента → строка с путем "module.ClassName"
        - Строка → как есть
        """
        if v is None:
            raise ValueError("entry_point_agent обязателен")
        
        if isinstance(v, str):
            return v
        
        if inspect.isclass(v):
            return f"{v.__module__}.{v.__name__}"
        
        if hasattr(v, "__class__"):
            return f"{v.__class__.__module__}.{v.__class__.__name__}"
        
        return v
    
    @field_validator('install_hook', 'after_install_hook', 'uninstall_hook', mode='before')
    @classmethod
    def convert_hook_to_tool_reference(cls, v, info):
        """
        Преобразует функцию в ToolReference используя ToolReference.migrate.
        
        Если передана функция - создает ToolReference.
        Если передан ToolReference - возвращает как есть.
        """
        if v is None:
            return None
        
        if isinstance(v, ToolReference):
            return v
        
        if callable(v):
            hook_type = info.field_name.replace('_hook', '')
            return ToolReference._from_function(
                func=v,
                tool_id=f"hook.{hook_type}.{v.__name__}",
                description=f"Хук {hook_type} flow"
            )
        
        return v
    
    @classmethod
    async def migrate(cls, flow_id: str, migrator, with_dependencies: bool = True) -> "FlowConfig":
        """
        Мигрирует flow из кода в БД с зависимостями.
        
        1. Загружает FlowConfig объект из кода по flow_id
        2. Создает FlowConfig через from_flow_config_object
        3. Загружает картинку в S3 если есть
        4. Сохраняет в БД
        5. Если with_dependencies=True, рекурсивно мигрирует entry_point_agent
        6. Возвращает FlowConfig
        
        Args:
            flow_id: Путь к переменной (например, "app.flows.weather_flow.weather_flow_config")
            migrator: Экземпляр Migrator для доступа к вспомогательным методам
            with_dependencies: Мигрировать ли entry_point_agent и его зависимости
            
        Returns:
            Мигрированный FlowConfig
        """
        if not flow_id or "." not in flow_id:
            raise ValueError(f"flow_id должен быть полным путем к переменной: {flow_id}")
        
        module_path, var_name = flow_id.rsplit(".", 1)
        module = __import__(module_path, fromlist=[var_name])
        flow_config_orig = getattr(module, var_name)
        
        if not isinstance(flow_config_orig, cls):
            raise ValueError(f"Объект {flow_id} не является FlowConfig")
        
        flow_repo = migrator.persister.flow_repository
        existing_flow = await flow_repo.get(flow_id)
        
        flow_config = cls.from_flow_config_object(flow_config_orig, flow_id)
        
        if flow_config.image_path:
            flow_config = await cls._upload_image_to_s3(flow_config)
        
        flow_config.source = "migration"
        now = datetime.now(timezone.utc)
        flow_config.updated_at = now
        if existing_flow and existing_flow.created_at:
            flow_config.created_at = existing_flow.created_at
        elif not flow_config.created_at:
            flow_config.created_at = now
        
        await migrator.persister.save_flow(flow_config)
        
        from ..services.variables_service import get_variables_service
        variables_service = get_variables_service()
        
        if flow_config.variables:
            await variables_service.resolve(flow_config.variables, auto_create=True)
        
        if flow_config.platforms:
            await variables_service.resolve(flow_config.platforms, auto_create=True)
        
        if flow_config.store:
            await variables_service.resolve(flow_config.store, auto_create=True)
        
        flow_tag = flow_config.name
        data_sources = [
            flow_config.variables,
            flow_config.platforms,
            flow_config.store
        ]
        tagged_count = await variables_service.tag_variables_for_entity(flow_tag, data_sources)
        if tagged_count > 0:
            logger.info(f"✅ Добавлено тегов для flow '{flow_tag}': {tagged_count}")
        
        if with_dependencies and flow_config.entry_point_agent:
            await AgentConfig.migrate(
                flow_config.entry_point_agent,
                migrator,
                with_tools=True
            )
        
        return flow_config
    
    @classmethod
    async def _upload_image_to_s3(cls, flow_config: "FlowConfig") -> "FlowConfig":
        """
        Загружает картинку flow в S3.
        
        Args:
            flow_config: FlowConfig с установленным image_path
            
        Returns:
            FlowConfig с установленным image_file_id
        """
        if not flow_config.image_path:
            return flow_config
        
        image_path = Path(flow_config.image_path)
        
        if not image_path.exists():
            logger.warning(f"Картинка не найдена: {flow_config.image_path}")
            return flow_config
        
        if not settings.s3.enabled:
            logger.warning("S3 не настроен, пропускаем загрузку картинки")
            return flow_config
        
        if not flow_config.flow_id:
            logger.warning("flow_id не установлен, пропускаем загрузку картинки")
            return flow_config
        
        from ..core.core_clients.s3_client import S3ClientFactory
        s3_client = S3ClientFactory.create_client_for_bucket(settings.s3.default_bucket)
        
        flow_hash = hashlib.md5(flow_config.flow_id.encode()).hexdigest()[:8]
        extension = image_path.suffix
        s3_key = f"flows/{flow_hash}/image{extension}"
        
        content_types = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".webp": "image/webp"
        }
        content_type = content_types.get(extension.lower(), "application/octet-stream")
        
        success = await s3_client.upload_file(
            file_path=str(image_path),
            key=s3_key,
            content_type=content_type,
            metadata={
                "flow_id": flow_config.flow_id,
                "type": "flow_image"
            }
        )
        
        if success:
            flow_config.image_file_id = s3_key
            logger.info(f"Картинка загружена в S3: {s3_key}")
        else:
            logger.warning(f"Не удалось загрузить картинку для {flow_config.flow_id}")
        
        await s3_client.close()
        
        return flow_config
    
    @property
    def slug(self) -> str:
        """
        Возвращает slug для использования в namespace.
        Формируется как: {company_subdomain}-{flow_id_slug}
        
        Использует get_context() для получения текущей компании.
        """
        if not self.flow_id:
            raise ValueError("flow_id не установлен")
        
        context = get_context()
        if not context or not context.active_company:
            raise ValueError("Контекст или активная компания не установлены")
        
        company_slug = context.active_company.subdomain
        flow_slug = generate_slug(self.flow_id, add_hash=True)
        
        return f"{company_slug}-{flow_slug}"
    
    @classmethod
    def from_flow_config_object(cls, obj: "FlowConfig", flow_id: str) -> "FlowConfig":
        """
        Создает новый FlowConfig из существующего объекта с установкой flow_id.
        
        Используется в Migrator для преобразования FlowConfig из кода
        с установкой правильного flow_id (полный путь к переменной).
        
        Args:
            obj: Исходный FlowConfig объект из кода
            flow_id: Полный путь к переменной (например, "app.flows.weather_flow.weather_flow_config")
            
        Returns:
            Новый FlowConfig с установленным flow_id
        """
        return cls(
            flow_id=flow_id,
            name=obj.name,
            description=obj.description,
            entry_point_agent=obj.entry_point_agent,
            platforms=obj.platforms,
            timeout=obj.timeout,
            max_retries=obj.max_retries,
            variables=obj.variables,
            store=getattr(obj, "store", {}),
            enable_reasoning=getattr(obj, "enable_reasoning", False),
            is_public=getattr(obj, "is_public", False),
            author=getattr(obj, "author", None),
            image_path=getattr(obj, "image_path", None),
            install_hook=getattr(obj, "install_hook", None),
            after_install_hook=getattr(obj, "after_install_hook", None),
            uninstall_hook=getattr(obj, "uninstall_hook", None),
            variables_definitions=getattr(obj, "variables_definitions", []),
            rag_config=getattr(obj, "rag_config", None),
            canvas_data=getattr(obj, "canvas_data", None),
            source=obj.source,
            created_at=obj.created_at,
            updated_at=obj.updated_at
        )
