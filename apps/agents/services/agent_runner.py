"""
Раннеры для выполнения агентов.
Заменяют скомпилированные графы LangGraph на прозрачную императивную логику.
"""

import asyncio
import importlib
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, List
from langchain_core.messages import AIMessage
from apps.agents.services.state import State
from apps.agents.services.tool_executor import ToolExecutor
from core.variables import VariableResolver
from apps.agents.services.state_modifier import render_state_variables
from apps.agents.container import get_agents_container
from apps.agents.models import ConditionType, CodeMode

logger = logging.getLogger(__name__)


class BaseAgentRunner(ABC):
    """Базовый класс для всех раннеров агентов"""

    def __init__(self, agent_config: Any, tools: List[Any], llm: Any, prompt: Optional[str] = None):
        """
        Args:
            agent_config: Конфигурация агента
            tools: Список доступных инструментов
            llm: Экземпляр LLM
            prompt: Промпт агента (опционально)
        """
        self.agent_config = agent_config
        self.tools = tools
        self.llm = llm
        self.prompt = prompt
        self.tool_executor = ToolExecutor()

    @abstractmethod
    async def arun(self, state: State) -> State:
        """
        Выполняет агента с заданным состоянием.

        Args:
            state: Начальное состояние агента

        Returns:
            Финальное состояние после выполнения
        """
        pass

    def _create_dynamic_prompt(self, state: State) -> List[Dict[str, str]]:
        """
        Создает динамический промпт с поддержкой переменных.

        Args:
            state: Текущее состояние

        Returns:
            Список сообщений для LLM (system message + история)
        """
        if not self.prompt:
            return []

        local_vars = self.agent_config.local_variables if hasattr(self.agent_config, 'local_variables') else {}
        static_rendered_prompt = VariableResolver.render_template(
            self.prompt,
            local_vars=local_vars,
            include_system=False
        )

        context = {
            "store": state.get("store", {}),
            "user_id": state.get("user_id", ""),
            "session_id": state.get("session_id", ""),
            "task_id": state.get("task_id", ""),
            "remaining_steps": state.get("remaining_steps", 0),
        }

        store = state.get("store", {})
        if isinstance(store, dict):
            for key, value in store.items():
                if key not in context:
                    context[key] = value

        sys_vars = VariableResolver.resolve_all(include_system=True)
        combined_context = dict(sys_vars)
        combined_context.update(context)

        rendered = render_state_variables(
            static_rendered_prompt,
            context=combined_context,
            full_state=state
        )

        return [{"role": "system", "content": rendered}]


class ReactAgentRunner(BaseAgentRunner):
    """Раннер для ReAct агентов"""

    async def arun(self, state: State) -> State:
        """
        Выполняет ReAct цикл: думай -> действуй -> наблюдай -> повторяй.

        Args:
            state: Начальное состояние

        Returns:
            Финальное состояние после выполнения
        """
        remaining_steps_raw = state.get("remaining_steps")
        max_iterations = remaining_steps_raw if remaining_steps_raw is not None else 25
        logger.info(f"🟡 ReAct.arun: remaining_steps из state={remaining_steps_raw}, max_iterations={max_iterations}")
        logger.info(f"🟡 ReAct.arun: state keys={list(state.keys())}")
        
        interrupt_context = state.get("interrupt_context", {})
        
        if interrupt_context.get("type") == "react_iteration":
            iteration = interrupt_context.get("iteration", 0)
            state.pop("interrupt_context", None)
            logger.info(f"🔄 ReAct возобновлен с итерации {iteration}")
        else:
            iteration = 0

        logger.info(f"🟡 ReAct.arun: начинаем цикл, iteration={iteration}, max_iterations={max_iterations}")
        while iteration < max_iterations:
            iteration += 1
            logger.info(f"🟡 ReAct итерация {iteration}/{max_iterations}")

            messages = state.get("messages", [])
            logger.info(f"🟡 ReAct: текущее количество сообщений: {len(messages)}")
            
            system_messages = self._create_dynamic_prompt(state)
            llm_messages = system_messages + messages
            logger.info(f"🟡 ReAct: отправляем в LLM {len(llm_messages)} сообщений (system: {len(system_messages)}, messages: {len(messages)})")

            # Привязываем тулы к LLM если они есть
            llm_with_tools = self.llm
            if self.tools:
                llm_with_tools = self.llm.bind_tools(self.tools)
                logger.info(f"🟡 ReAct: привязано {len(self.tools)} тулов к LLM")

            logger.info("🟡 ReAct: вызываем LLM.ainvoke...")
            response = await llm_with_tools.ainvoke(llm_messages)
            logger.info(f"🟡 ReAct: LLM вернул ответ, type={type(response).__name__}")

            if not isinstance(response, AIMessage):
                logger.warning(f"🟡 ReAct: неожиданный тип ответа от LLM: {type(response)}")
                response = AIMessage(content=str(response))

            state["messages"] = messages + [response]
            logger.info(f"🟡 ReAct: добавлен ответ в state, теперь сообщений: {len(state['messages'])}")

            tool_calls = self._extract_tool_calls(response)
            logger.info(f"🟡 ReAct: извлечено tool_calls: {len(tool_calls)}")
            
            if not tool_calls:
                logger.info(f"🟡 ReAct ЗАВЕРШЕН: LLM вернул финальный ответ без tool_calls (итерация {iteration})")
                break

            logger.info(f"🟡 ReAct: выполняем {len(tool_calls)} инструментов")
            
            from apps.agents.agents.base import AgentInterrupt
            
            try:
                tool_messages = await self.tool_executor.execute(
                    tool_calls=tool_calls,
                    tools=self.tools,
                    state=state
                )

                state["messages"] = state["messages"] + tool_messages
                state["remaining_steps"] = max_iterations - iteration
            except AgentInterrupt as interrupt:
                raise interrupt

        if iteration >= max_iterations:
            logger.warning(f"ReAct достиг максимального количества итераций ({max_iterations})")

        return state

    def _extract_tool_calls(self, message: AIMessage) -> List[Dict[str, Any]]:
        """
        Извлекает tool_calls из ответа LLM.

        Args:
            message: Ответ от LLM

        Returns:
            Список вызовов инструментов
        """
        if not hasattr(message, "tool_calls") or not message.tool_calls:
            return []

        tool_calls = []
        for tool_call in message.tool_calls:
            if isinstance(tool_call, dict):
                tool_calls.append(tool_call)
            else:
                tool_calls.append({
                    "name": getattr(tool_call, "name", ""),
                    "args": getattr(tool_call, "args", {}),
                    "id": getattr(tool_call, "id", ""),
                })

        return tool_calls


class StateGraphRunner(BaseAgentRunner):
    """Раннер для StateGraph агентов"""

    def __init__(self, agent_config: Any, tools: List[Any], llm: Any, graph_definition: Any, prompt: Optional[str] = None):
        """
        Args:
            agent_config: Конфигурация агента
            tools: Список доступных инструментов
            llm: Экземпляр LLM
            graph_definition: Определение графа
            prompt: Промпт агента (опционально)
        """
        super().__init__(agent_config, tools, llm, prompt)
        self.graph_definition = graph_definition
        self._node_functions = {}
        self._edges_map = {}
        self._conditional_edges = {}
        self._entry_point = None
        self._initialized = False

    async def _initialize(self):
        """Инициализирует структуру графа из определения"""
        if self._initialized:
            return

        builder = get_agents_container().graph_builder
        llm_config = self.agent_config.llm_config if hasattr(self.agent_config, 'llm_config') else None

        # Создаем функции для всех нод
        for node in self.graph_definition.nodes:
            node_func = await builder._create_node_function(node, llm_config)
            self._node_functions[node.id] = node_func

        # Строим карту ребер
        for edge in self.graph_definition.edges:
            logger.info(f"🔍 Обрабатываем edge: {edge.source} -> {edge.target} (condition_type={edge.condition_type})")
            if edge.source == "START":
                self._entry_point = edge.target
                logger.info(f"🔍 Установлен entry_point={self._entry_point} из edge START -> {edge.target}")
                continue

            if edge.condition_type == ConditionType.ROUTER:
                if edge.source not in self._conditional_edges:
                    self._conditional_edges[edge.source] = {
                        "type": "ROUTER",
                        "mapping": {},
                        "condition_func": None
                    }
                self._conditional_edges[edge.source]["mapping"][edge.target] = edge.target
                logger.info(f"🔍 Добавлен ROUTER edge: {edge.source} -> {edge.target}")
            elif edge.condition_type == ConditionType.EXPRESSION:
                if edge.source not in self._conditional_edges:
                    self._conditional_edges[edge.source] = {
                        "type": "EXPRESSION",
                        "edges": []
                    }
                self._conditional_edges[edge.source]["edges"].append(edge)
                logger.info(f"🔍 Добавлен EXPRESSION edge: {edge.source} -> {edge.target}")
            else:
                # Обычное ребро (без условия)
                if edge.source not in self._edges_map:
                    self._edges_map[edge.source] = []
                self._edges_map[edge.source].append(edge.target)
                logger.info(f"🔍 Добавлен обычный edge в _edges_map: {edge.source} -> {edge.target} (condition_type={edge.condition_type}), теперь {edge.source} имеет edges: {self._edges_map[edge.source]}")

        # Находим функцию условия для ROUTER нод
        for source, cond_info in self._conditional_edges.items():
            if cond_info["type"] == "ROUTER":
                cond_info["condition_func"] = await self._find_router_condition(source)

        if not self._entry_point:
            self._entry_point = self.graph_definition.entry_point or "START"

        self._initialized = True
        logger.info(f"StateGraph инициализирован: entry_point={self._entry_point}, nodes={len(self._node_functions)}, edges={len(self._edges_map)}")
        logger.info(f"Edges map: {self._edges_map}")
        logger.info(f"Conditional edges: {self._conditional_edges}")
        logger.info(f"Node functions: {list(self._node_functions.keys())}")

    async def _find_router_condition(self, source_node_id: str):
        """Находит функцию условия для ROUTER ноды"""
        source_node = next((n for n in self.graph_definition.nodes if n.id == source_node_id), None)
        if not source_node:
            return None

        # Ищем в inline коде
        if hasattr(source_node, "code_mode") and source_node.code_mode == CodeMode.INLINE_CODE and source_node.inline_code:
            local_namespace = {}
            exec(source_node.inline_code, globals(), local_namespace)

            condition_names = [f"{source_node_id}_condition", "router_condition"]
            for cond_name in condition_names:
                if cond_name in local_namespace:
                    func = local_namespace[cond_name]
                    logger.info(f"Найдена функция условия: {cond_name}")
                    return func

        # Ищем в edges
        for edge in self.graph_definition.edges:
            if edge.source == source_node_id and edge.condition:
                module_path, func_name = edge.condition.rsplit(".", 1)
                module = importlib.import_module(module_path)
                func = getattr(module, func_name)
                logger.info(f"Найдена функция условия по пути: {edge.condition}")
                return func

        return None

    async def _ensure_initialized(self):
        """Обеспечивает инициализацию графа (вызывается при создании раннера и перед выполнением)"""
        if not self._initialized:
            await self._initialize()

    async def arun(self, state: State) -> State:
        """
        Выполняет StateGraph агента по определению графа.

        Args:
            state: Начальное состояние

        Returns:
            Финальное состояние после выполнения
        """
        await self._ensure_initialized()

        interrupt_context = state.get("interrupt_context", {})
        
        if interrupt_context.get("type") == "stategraph_node":
            current_node = interrupt_context.get("current_node", self._entry_point)
            state.pop("interrupt_context", None)
            logger.info(f"🔄 StateGraph возобновлен с ноды {current_node}")
        else:
            current_node = self._entry_point
        
        max_iterations = 100
        iteration = 0
        visited_nodes = {}  # Отслеживаем посещенные ноды для защиты от зацикливания

        while current_node and current_node != "END" and iteration < max_iterations:
            iteration += 1
            
            # Защита от зацикливания: если нода посещена более 5 раз, прерываем
            visited_count = visited_nodes.get(current_node, 0)
            if visited_count >= 5:
                logger.error(f"🟣 StateGraph: ОБНАРУЖЕНО ЗАЦИКЛИВАНИЕ! Нода {current_node} посещена {visited_count} раз. Прерываем выполнение.")
                break
            visited_nodes[current_node] = visited_count + 1
            
            logger.info(f"🟣 StateGraph итерация {iteration}/{max_iterations}: выполняется нода {current_node} (посещена {visited_nodes[current_node]} раз)")

            node_func = self._node_functions.get(current_node)
            if not node_func:
                logger.error(f"🟣 StateGraph: нода {current_node} не найдена в графе")
                break
            
            from apps.agents.agents.base import AgentInterrupt
            from apps.agents.services.state_manager import get_state_manager
            
            logger.info(f"🟣 StateGraph: вызываем функцию ноды {current_node}...")
            try:
                state = await node_func(state)
                
                # Сохраняем store после выполнения ноды, если он был изменен
                from apps.agents.services.state_manager import StoreProxy
                store = state.get("store")
                if isinstance(store, StoreProxy) and store._dirty:
                    await store.ensure_saved()
                
                logger.info(f"🟣 StateGraph: нода {current_node} выполнена, state keys: {list(state.keys())}, store keys: {list(state.get('store', {}).keys())}, messages: {len(state.get('messages', []))}")
            except AgentInterrupt as interrupt:
                state["interrupt_context"] = {
                    "type": "stategraph_node",
                    "current_node": current_node
                }
                session_id = state.get("session_id")
                if session_id:
                    state_manager = await get_state_manager()
                    await state_manager.save_session(state)
                    logger.info(f"⏸️  StateGraph: сохранена позиция ноды {current_node} при interrupt")
                raise interrupt

            # Определяем следующую ноду
            next_node = await self._get_next_node(current_node, state)
            logger.info(f"🔍 _get_next_node вернул: {next_node} (type: {type(next_node)}) для {current_node}")
            
            if next_node is None or next_node == "END":
                logger.info(f"🟣 StateGraph завершен: достигнут END (next_node={next_node})")
                break

            if not next_node:
                logger.warning(f"🟣 StateGraph: next_node is None или пустой для {current_node}, завершаем граф")
                break

            logger.info(f"🔍 Переход к следующей ноде: {current_node} -> {next_node}")
            current_node = next_node

        if iteration >= max_iterations:
            logger.warning(f"StateGraph достиг максимального количества итераций ({max_iterations})")

        return state

    async def _get_next_node(self, current_node: str, state: State) -> Optional[str]:
        """Определяет следующую ноду на основе текущей ноды и состояния"""
        if current_node in self._conditional_edges:
            cond_info = self._conditional_edges[current_node]
            
            if cond_info["type"] == "ROUTER":
                condition_func = cond_info["condition_func"]
                if condition_func:
                    next_target = await condition_func(state) if asyncio.iscoroutinefunction(condition_func) else condition_func(state)
                    
                    if next_target in cond_info["mapping"]:
                        logger.info(f"ROUTER {current_node}: переход к {next_target}")
                        return next_target
                    elif next_target == "END":
                        return "END"
                else:
                    logger.warning(f"ROUTER {current_node}: condition_func не найдена, используем обычные ребра")
            
            elif cond_info["type"] == "EXPRESSION":
                for edge in cond_info["edges"]:
                    result = eval(edge.condition, {"state": state, "State": State})
                    if bool(result):
                        logger.info(f"EXPRESSION {current_node} -> {edge.target}: условие выполнено")
                        return edge.target if edge.target != "END" else "END"

        if current_node in self._edges_map:
            next_nodes = self._edges_map[current_node]
            if next_nodes:
                next_node = next_nodes[0]
                logger.info(f"Переход {current_node} -> {next_node} (edges_map содержит: {next_nodes})")
                if next_node == "END":
                    return "END"
                return next_node

        logger.info(f"Нет edges для {current_node}, возвращаем END")
        return "END"

