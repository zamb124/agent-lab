"""
Построитель графов для StateGraph агентов.
Динамически создает графы на основе JSON-описания.
"""

import logging
import inspect
import importlib
from typing import Optional
from langgraph.graph import StateGraph, END
from langchain_core.runnables import Runnable
from langchain_core.messages import AIMessage

from app.models import (
    GraphDefinition,
    NodeType,
    LLMConfig,
    ToolReference,
    ConditionType,
    CodeMode,
)
from app.core.tool_factory import ToolFactory
from app.core.checkpointer import get_checkpointer
from app.core.agent_factory import AgentFactory
from app.core.state import State

logger = logging.getLogger(__name__)


class GraphBuilder:
    """Построитель графов на основе определений"""

    def __init__(self):
        self.tool_factory = ToolFactory()

    async def build_from_definition(
        self, graph_def: GraphDefinition, llm_config: Optional[LLMConfig] = None
    ) -> Runnable:
        """
        Строит исполняемый граф на основе определения.

        Args:
            graph_def: Определение графа
            llm_config: Конфигурация LLM

        Returns:
            Скомпилированный граф
        """
        logger.info(
            f"Строим граф с {len(graph_def.nodes)} нодами и {len(graph_def.edges)} ребрами"
        )

        # Создаем StateGraph с единым State
        graph = StateGraph(State)

        # Добавляем ноды
        for node in graph_def.nodes:
            node_func = await self._create_node_function(node, llm_config)
            graph.add_node(node.id, node_func)

        # Добавляем ребра
        start_target = None  # Запоминаем куда ведет START
        conditional_groups = {}  # Группируем conditional edges по источнику

        for edge in graph_def.edges:
            if edge.source == "START":
                # Ребро от START - запоминаем для set_entry_point
                start_target = edge.target
                continue

            if edge.condition_type == ConditionType.ROUTER:
                # Группируем conditional edges по источнику
                if edge.source not in conditional_groups:
                    conditional_groups[edge.source] = {}
                conditional_groups[edge.source][edge.target] = edge.target
            else:
                # Обычное ребро
                if edge.target == "END":
                    graph.add_edge(edge.source, END)
                else:
                    graph.add_edge(edge.source, edge.target)

        # Добавляем conditional edges группами
        for source, mapping in conditional_groups.items():
            # Находим функцию условия
            condition_func = None

            # Сначала ищем в inline коде source ноды
            source_node = next((n for n in graph_def.nodes if n.id == source), None)
            if (
                source_node
                and hasattr(source_node, "code_mode")
                and source_node.code_mode == CodeMode.INLINE_CODE
                and source_node.inline_code
            ):
                # Извлекаем функцию условия из inline кода
                try:
                    local_namespace = {}
                    exec(source_node.inline_code, globals(), local_namespace)

                    # Ищем функцию условия
                    condition_names = [f"{source}_condition", "router_condition"]
                    for cond_name in condition_names:
                        if cond_name in local_namespace:
                            condition_func = local_namespace[cond_name]
                            logger.info(
                                f"✅ INLINE функция условия найдена: {cond_name}"
                            )
                            break

                except Exception as e:
                    logger.error(
                        f"❌ Ошибка извлечения функции условия из inline кода: {e}",
                        exc_info=True
                    )

            # Если не нашли в inline коде, ищем по пути
            if not condition_func:
                for edge in graph_def.edges:
                    if (
                        edge.source == source
                        and edge.condition_type == ConditionType.ROUTER
                        and edge.condition
                    ):
                        try:
                            # Импортируем функцию по пути
                            module_path, func_name = edge.condition.rsplit(".", 1)
                            module = importlib.import_module(module_path)
                            condition_func = getattr(module, func_name)
                            break
                        except Exception as e:
                            logger.warning(
                                f"Не удалось импортировать функцию условия {edge.condition}: {e}"
                            )

            if condition_func:
                graph.add_conditional_edges(source, condition_func, mapping)
            else:
                logger.warning(f"Не найдена функция условия для {source}")

        # Устанавливаем точку входа
        if start_target:
            # Используем ноду куда ведет START
            graph.set_entry_point(start_target)
        elif graph_def.entry_point == "START":
            # Если entry_point это START, находим первую ноду без входящих ребер
            first_node = self._find_first_node(graph_def)
            graph.set_entry_point(first_node)
        else:
            graph.set_entry_point(graph_def.entry_point)

        # Компилируем граф с checkpointer для сохранения состояния
        checkpointer = await get_checkpointer()
        compiled_graph = graph.compile(checkpointer=checkpointer)

        logger.info("Граф успешно скомпилирован")
        return compiled_graph

    async def _create_node_function(self, node, llm_config: Optional[LLMConfig] = None):
        """Создает функцию для ноды на основе ее типа"""

        if node.type == NodeType.AGENT_NODE:
            return await self._create_agent_node(node, llm_config)
        elif node.type == NodeType.TOOL_NODE:
            return await self._create_tool_node(node)
        elif node.type == NodeType.FUNCTION_NODE:
            return await self._create_function_node(node)
        elif node.type == NodeType.MESSAGE_NODE:
            return self._create_message_node(node)
        else:
            raise ValueError(f"Неизвестный тип ноды: {node.type}")

    async def _create_agent_node(self, node, llm_config: Optional[LLMConfig] = None):
        """Создает ноду-агента"""

        # Поддерживаем несколько вариантов указания агента:
        # 1. node.params['agent_id'] - строка с ID агента (для UI/API)
        # 2. node.function_class - путь к классу агента (для миграции из кода)
        # 3. node.id как agent_id (если нода названа по имени агента)
        agent_id = node.params.get("agent_id") or node.function_class
        
        if not agent_id:
            # Попытка использовать id ноды как agent_id
            logger.warning(
                f"Нода агента {node.id} не содержит agent_id или function_class, "
                f"пытаемся использовать id ноды как agent_id"
            )
            agent_id = node.id
        
        if not agent_id:
            raise ValueError(
                f"Нода агента {node.id} должна содержать agent_id в params или function_class. "
                f"Доступные поля: params={node.params}, function_class={node.function_class}"
            )

        agent_factory = AgentFactory()
        
        try:
            agent = await agent_factory.get_agent(agent_id)
        except Exception as e:
            raise ValueError(
                f"Не удалось загрузить агента {agent_id} для ноды {node.id}: {e}"
            ) from e

        async def agent_node(state: State) -> State:
            """Функция ноды агента"""
            try:
                result = await agent.ainvoke(state)
                # Обновляем состояние результатом агента
                if isinstance(result, dict):
                    state.update(result)
                return state
            except Exception as e:
                logger.error(f"Ошибка в ноде агента {node.id}: {e}", exc_info=True)
                if "store" not in state:
                    state["store"] = {}
                state["store"]["error"] = str(e)
                return state

        return agent_node

    async def _create_tool_node(self, node):
        """Создает ноду-инструмент"""
        tool_id = node.params.get("tool_id")
        if not tool_id:
            raise ValueError(f"Нода инструмента {node.id} должна содержать tool_id")

        tool_ref = ToolReference(
            tool_id=tool_id, params=node.params.get("tool_params", {})
        )
        tools = await self.tool_factory.create_tools([tool_ref])

        if not tools:
            raise ValueError(f"Не удалось создать инструмент {tool_id}")

        tool = tools[0]

        async def tool_node(state: State) -> State:
            """Функция ноды инструмента"""
            try:
                # Извлекаем входные данные из состояния
                tool_input = node.params.get("input_key", "input")
                input_data = state.get(tool_input, "")

                # Вызываем инструмент
                result = (
                    await tool.ainvoke(input_data)
                    if hasattr(tool, "ainvoke")
                    else tool.invoke(input_data)
                )

                # Сохраняем результат в состояние
                output_key = node.params.get("output_key", "output")
                state[output_key] = result

                return state
            except Exception as e:
                logger.error(f"Ошибка в ноде инструмента {node.id}: {e}", exc_info=True)
                if "store" not in state:
                    state["store"] = {}
                state["store"]["error"] = str(e)
                return state

        return tool_node

    async def _create_function_node(self, node):
        """Создает ноду-функцию"""

        # Проверяем режим хранения кода
        if hasattr(node, "code_mode") and node.code_mode == CodeMode.INLINE_CODE:
            # INLINE_CODE режим - выполняем код из БД
            if not node.inline_code:
                raise ValueError(f"INLINE нода {node.id} должна содержать inline_code")

            # Выполняем inline код и извлекаем функцию
            func = await self._execute_inline_code(node)

        else:
            # CODE_REFERENCE режим - импортируем функцию
            function_path = node.params.get("function") or node.function_path
            if not function_path:
                raise ValueError(
                    f"Нода функции {node.id} должна содержать function или function_path"
                )

            # Импортируем функцию
            module_path, func_name = function_path.rsplit(".", 1)
            module = importlib.import_module(module_path)
            func = getattr(module, func_name)

        async def function_node(state: State) -> State:
            """Функция ноды функции"""
            try:
                # Передаем состояние в функцию
                if inspect.iscoroutinefunction(func):
                    result = await func(state)
                else:
                    result = func(state)

                # Обновляем состояние
                if isinstance(result, dict):
                    state.update(result)
                else:
                    output_key = node.params.get("output_key", "output")
                    state[output_key] = result

                return state
            except Exception as e:
                logger.error(f"Ошибка в ноде функции {node.id}: {e}", exc_info=True)
                if "store" not in state:
                    state["store"] = {}
                state["store"]["error"] = str(e)
                return state

        return function_node

    async def _execute_inline_code(self, node):
        """Выполняет inline код и возвращает функцию"""
        try:
            # Создаем локальное пространство имен
            local_namespace = {}

            # Выполняем код
            exec(node.inline_code, globals(), local_namespace)

            # Ищем функцию с именем как ID ноды или с суффиксом _function
            possible_names = [
                node.id,
                f"{node.id}_function",
                "router_function",  # Для router ноды
                "router_condition",  # Для условий
            ]

            for func_name in possible_names:
                if func_name in local_namespace:
                    func = local_namespace[func_name]
                    logger.info(
                        f"✅ INLINE функция найдена: {func_name} для ноды {node.id}"
                    )
                    return func

            # Если не нашли по именам, берем первую функцию
            for name, obj in local_namespace.items():
                if callable(obj) and not name.startswith("_"):
                    logger.info(
                        f"✅ INLINE функция найдена (первая): {name} для ноды {node.id}"
                    )
                    return obj

            raise ValueError(f"Не найдена функция в inline коде ноды {node.id}")

        except Exception as e:
            logger.error(f"❌ Ошибка выполнения inline кода ноды {node.id}: {e}", exc_info=True)
            raise

    def _create_message_node(self, node):
        """Создает ноду сообщения"""
        message = node.params.get("message", "")

        async def message_node(state: State) -> State:
            """Функция ноды сообщения"""
            # Добавляем сообщение в историю
            if "messages" not in state:
                state["messages"] = []

            state["messages"].append(AIMessage(content=message))
            return state

        return message_node

    def _create_condition_function(self, condition: str):
        """Создает функцию условия для условных ребер"""

        def condition_func(state: State) -> str:
            """Функция условия"""
            try:
                # Простая оценка условия (в продакшене нужна более безопасная реализация)
                if eval(condition, {"state": state}):
                    return "continue"
                else:
                    return "end"
            except Exception as e:
                logger.error(f"Ошибка в условии {condition}: {e}", exc_info=True)
                return "end"

        return condition_func

    def _find_first_node(self, graph_def: GraphDefinition) -> str:
        """Находит первую ноду (без входящих ребер)"""
        all_targets = {edge.target for edge in graph_def.edges}
        for node in graph_def.nodes:
            if node.id not in all_targets:
                return node.id

        # Если не нашли, берем первую ноду
        return graph_def.nodes[0].id if graph_def.nodes else "start"
