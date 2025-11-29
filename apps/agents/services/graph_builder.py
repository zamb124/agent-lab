"""
Построитель графов для StateGraph агентов.
Динамически создает графы на основе JSON-описания.
"""

import logging
import inspect
import importlib
import uuid
from typing import Optional
from langchain_core.messages import AIMessage

from apps.agents.models import (
    NodeType,
    LLMConfig,
    ToolReference,
    CodeMode,
)
from apps.agents.container import get_agents_container
from apps.agents.services.state import State

logger = logging.getLogger(__name__)


class GraphBuilder:
    """Построитель графов на основе определений"""

    def __init__(self):
        self.tool_factory = get_agents_container().tool_factory

    async def _create_node_function(self, node, llm_config: Optional[LLMConfig] = None):
        """Создает функцию для ноды на основе ее типа"""

        if node.type == NodeType.AGENT_NODE:
            return await self._create_agent_node(node, llm_config)
        elif node.type == NodeType.TOOL_NODE:
            return await self._create_tool_node(node)
        elif node.type == NodeType.FUNCTION_NODE:
            return await self._create_function_node(node)
        elif node.type == NodeType.ROUTER_NODE:
            return await self._create_router_node(node)
        elif node.type == NodeType.MESSAGE_NODE:
            return self._create_message_node(node)
        elif node.type == NodeType.FLOW_NODE:
            return await self._create_flow_node(node)
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

        agent_factory = get_agents_container().agent_factory
        
        try:
            agent = await agent_factory.get_agent(agent_id)
        except Exception as e:
            raise ValueError(
                f"Не удалось загрузить агента {agent_id} для ноды {node.id}: {e}"
            ) from e

        async def agent_node(state: State) -> State:
            """Функция ноды агента"""
            try:
                original_store = state.get("store")
                result = await agent.ainvoke(state)

                if isinstance(result, dict):
                    original_messages = state.get("messages", [])
                    result_messages = result.get("messages", [])
                    result_store = result.get("store")
                    
                    state.clear()
                    state.update(result)
                    
                    if original_messages and result_messages:
                        state["messages"] = original_messages + result_messages
                    elif original_messages:
                        state["messages"] = original_messages
                    elif result_messages:
                        state["messages"] = result_messages
                    
                    if result_store and isinstance(result_store, dict) and len(result_store) > 0:
                        state["store"] = result_store
                    elif original_store:
                        state["store"] = original_store

                return state
            except Exception as e:
                logger.error(f"Ошибка в ноде агента {node.id}: {e}", exc_info=True)
                raise RuntimeError(f"Ошибка выполнения агента в ноде {node.id}: {str(e)}") from e

        return agent_node

    async def _create_tool_node(self, node):
        """Создает ноду-инструмент"""
        tool_id = node.params.get("tool_id")
        if not tool_id:
            raise ValueError(f"Нода инструмента {node.id} должна содержать tool_id")

        # Определяем code_mode по tool_id
        if tool_id.startswith("mcp:"):
            code_mode = CodeMode.MCP_TOOL
        elif "." in tool_id:
            code_mode = CodeMode.CODE_REFERENCE
        else:
            code_mode = CodeMode.INLINE_CODE
        
        # Для MCP тулов загружаем ToolReference из БД
        if code_mode == CodeMode.MCP_TOOL:
            tool_repo = get_agents_container().tool_repository
            tool_ref = await tool_repo.get(tool_id)
            
            if not tool_ref:
                raise ValueError(f"MCP тул {tool_id} не найден в БД. Синхронизируйте MCP сервер.")
        else:
            # Создаем ToolReference для обычного тула
            tool_ref = ToolReference(
                tool_id=tool_id, 
                code_mode=code_mode,
                params=node.params.get("tool_params", {})
            )
        
        tools = await self.tool_factory.create_tools([tool_ref])

        if not tools:
            raise ValueError(f"Не удалось создать инструмент {tool_id}")

        tool = tools[0]

        async def tool_node(state: State) -> State:
            """Функция ноды инструмента"""
            logger.info(f"🔧 [TOOL_NODE] {node.id}: tool={tool.name if hasattr(tool, 'name') else 'unknown'}")
            
            # Если в params есть args - используем их напрямую
            if "args" in node.params:
                tool_args = node.params["args"].copy() if isinstance(node.params["args"], dict) else {}
                logger.info(f"   Используем args из params: {tool_args}")
            else:
                # Извлекаем входные данные из состояния
                # Поддержка вложенных ключей вида "store.key"
                tool_input_key = node.params.get("input_key", "input")
                
                if "." in tool_input_key:
                    # Вложенный ключ вида "store.calc_input"
                    parts = tool_input_key.split(".", 1)
                    input_data = state.get(parts[0], {}).get(parts[1], "")
                else:
                    input_data = state.get(tool_input_key, "")
                
                logger.info(f"   Input key: {tool_input_key}")
                logger.info(f"   Input data type: {type(input_data)}")
                logger.info(f"   State keys: {list(state.keys())}")

                # Подготавливаем аргументы для тула
                # Для StructuredTool (включая MCP) нужен dict с параметрами
                if hasattr(tool, 'args_schema') and tool.args_schema:
                    # Если input_data уже dict - используем как есть
                    if isinstance(input_data, dict):
                        tool_args = input_data.copy()
                    else:
                        # Преобразуем в dict с первым параметром
                        schema_fields = tool.args_schema.model_fields
                        # Фильтруем служебные поля state и tool_call_id
                        param_names = [
                            name for name in schema_fields.keys() 
                            if name not in ['state', 'tool_call_id']
                        ]
                        
                        if not param_names:
                            tool_args = {}
                        else:
                            first_param = param_names[0]
                            tool_args = {first_param: input_data}
                else:
                    tool_args = input_data
            
            # Устанавливаем state в контекст для state_aware тулов
            from core.variables import set_state_in_context
            if hasattr(tool, '_is_platform_tool') and tool._is_platform_tool:
                set_state_in_context(state)
                logger.debug("   State установлен в контекст для тула (state_aware)")
            
            # Добавляем tool_call_id только если он есть в схеме
            if hasattr(tool, 'args_schema') and tool.args_schema:
                schema_fields = tool.args_schema.model_fields if hasattr(tool.args_schema, 'model_fields') else {}
                if 'tool_call_id' in schema_fields and 'tool_call_id' not in tool_args:
                    tool_args['tool_call_id'] = str(uuid.uuid4())
                    logger.debug("   Добавляем tool_call_id в аргументы тула")

            # Вызываем тул через ainvoke для корректной работы @tool декоратора
            if hasattr(tool, "ainvoke"):
                result = await tool.ainvoke(tool_args)
            else:
                result = tool.invoke(tool_args)

            # Сохраняем результат в состояние
            # Поддержка вложенных ключей вида "store.key"
            output_key = node.params.get("output_key", "output")
            
            if "." in output_key:
                # Вложенный ключ вида "store.calc_result"
                parts = output_key.split(".", 1)
                if parts[0] not in state:
                    raise ValueError(f"В state должен быть '{parts[0]}', но его нет. State keys: {list(state.keys())}")
                state[parts[0]][parts[1]] = result
            else:
                state[output_key] = result
            
            logger.info(f"✅ [TOOL_NODE] {node.id}: результат сохранен в {output_key}")

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
            from apps.agents.exceptions import AgentInterrupt
            
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
            except AgentInterrupt as interrupt:
                # Пробрасываем AgentInterrupt дальше для обработки в agent_runner
                raise interrupt
            except Exception as e:
                logger.error(f"Ошибка в ноде функции {node.id}: {e}", exc_info=True)
                raise RuntimeError(f"Ошибка выполнения функции в ноде {node.id}: {str(e)}") from e

        return function_node

    async def _create_router_node(self, node):
        """
        Создает ноду-роутер для условных переходов.
        
        ROUTER_NODE - это специальная FUNCTION_NODE, которая определяет
        следующую ноду на основе состояния (state).
        
        Функция-роутер должна возвращать строку - ID следующей ноды.
        """
        
        # Проверяем режим хранения кода
        if hasattr(node, "code_mode") and node.code_mode == CodeMode.INLINE_CODE:
            # INLINE_CODE режим
            if not node.inline_code:
                raise ValueError(f"ROUTER_NODE {node.id} должна содержать inline_code")

            # Выполняем inline код и извлекаем функцию
            router_func = await self._execute_inline_code(node)

        else:
            # CODE_REFERENCE режим
            function_path = node.params.get("function") or node.function_path
            if not function_path:
                raise ValueError(
                    f"ROUTER_NODE {node.id} должна содержать function или function_path"
                )

            # Импортируем функцию
            module_path, func_name = function_path.rsplit(".", 1)
            module = importlib.import_module(module_path)
            router_func = getattr(module, func_name)

        async def router_node(state: State) -> State:
            """
            Функция роутера.
            
            Важно: сама нода ничего не возвращает, она просто выполняется.
            Логика роутинга берется из функции для conditional_edges.
            """
            try:
                logger.info(f"ROUTER_NODE {node.id}: выполняется логика роутинга")
                
                # Роутер может модифицировать state перед принятием решения
                if inspect.iscoroutinefunction(router_func):
                    result = await router_func(state)
                else:
                    result = router_func(state)
                
                # Если функция возвращает dict, обновляем state
                if isinstance(result, dict):
                    state.update(result)
                
                # Если возвращает строку, сохраняем решение роутера в state
                elif isinstance(result, str):
                    if "store" not in state:
                        state["store"] = {}
                    state["store"]["router_decision"] = result
                    logger.info(f"ROUTER_NODE {node.id}: принято решение -> {result}")

                return state
            except Exception as e:
                logger.error(f"Ошибка в ROUTER_NODE {node.id}: {e}", exc_info=True)
                raise RuntimeError(f"Ошибка выполнения роутера в ноде {node.id}: {str(e)}") from e

        return router_node

    async def _execute_inline_code(self, node):
        """Выполняет inline код и возвращает функцию"""
        try:
            # Получаем namespace с доступными функциями (ask_user, session_set и т.д.)
            from apps.agents.services.tool_factory import ToolFactory
            tool_factory = ToolFactory()
            namespace = await tool_factory.get_tool_namespace()
            
            # Создаем локальное пространство имен
            local_namespace = {}

            # Выполняем код с доступом к namespace
            exec(node.inline_code, namespace, local_namespace)

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
        """Создает ноду сообщения для отправки фиксированного текста"""
        message = node.params.get("message", "")
        
        if not message:
            logger.warning(f"MESSAGE_NODE {node.id} не содержит сообщение")

        async def message_node(state: State) -> State:
            """Функция ноды сообщения"""
            try:
                # Добавляем сообщение в историю
                if "messages" not in state:
                    state["messages"] = []

                state["messages"].append(AIMessage(content=message))
                logger.info(f"MESSAGE_NODE {node.id}: добавлено сообщение '{message[:50]}...'")
                return state
            except Exception as e:
                logger.error(f"Ошибка в MESSAGE_NODE {node.id}: {e}", exc_info=True)
                raise RuntimeError(f"Ошибка выполнения сообщения в ноде {node.id}: {str(e)}") from e

        return message_node

    async def _create_flow_node(self, node):
        """Создает ноду для вызова другого flow"""
        flow_id = node.params.get("flow_id")
        if not flow_id:
            raise ValueError(
                f"FLOW_NODE {node.id} должна содержать flow_id в params. "
                f"Доступные поля: {node.params}"
            )

        flow_factory = get_agents_container().flow_factory
        
        try:
            flow = await flow_factory.get_flow(flow_id)
        except Exception as e:
            raise ValueError(
                f"Не удалось загрузить flow {flow_id} для ноды {node.id}: {e}"
            ) from e

        async def flow_node(state: State) -> State:
            """Функция ноды flow"""
            try:
                logger.info(f"FLOW_NODE {node.id}: вызов flow {flow_id}")
                
                result = await flow.ainvoke(state)
                
                if isinstance(result, dict):
                    state.update(result)
                
                logger.info(f"FLOW_NODE {node.id}: flow {flow_id} завершен успешно")
                return state
            except Exception as e:
                logger.error(f"Ошибка в FLOW_NODE {node.id} (flow {flow_id}): {e}", exc_info=True)
                raise RuntimeError(f"Ошибка выполнения flow {flow_id} в ноде {node.id}: {str(e)}") from e

        return flow_node

    def _create_condition_function(self, condition: str):
        """Создает функцию условия для условных ребер"""

        def condition_func(state: State) -> str:
            """Функция условия"""
            try:
                from simpleeval import simple_eval
                result = simple_eval(condition, names={"state": state})
                if bool(result):
                    return "continue"
                else:
                    return "end"
            except Exception as e:
                logger.error(f"Ошибка в условии {condition}: {e}", exc_info=True)
                raise ValueError(f"Ошибка выполнения условия '{condition}': {str(e)}") from e

        return condition_func
