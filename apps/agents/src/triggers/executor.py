"""
TriggerExecutor - запуск агента при срабатывании триггера.

Получает данные из триггера, применяет input_mapping,
и запускает агента через process_agent_task.

OutputActionExecutor - выполнение output_actions после завершения агента.
"""

import uuid
from typing import Any, Dict, List, Optional

from apps.agents.src.models import TriggerConfig
from apps.agents.src.models.channel_config import OutputAction
from apps.agents.src.triggers.input_mapper import InputMapper
from core.context import Context, User, get_context, set_context
from core.logging import get_logger

logger = get_logger(__name__)


class TriggerExecutor:
    """
    Выполняет агента при срабатывании триггера.
    
    Workflow:
    1. Загружает конфиг триггера
    2. Применяет input_mapping к payload
    3. Формирует context и initial state
    4. Запускает process_agent_task
    """
    
    def __init__(self):
        self._input_mapper = InputMapper()
    
    async def execute(
        self,
        agent_id: str,
        trigger: TriggerConfig,
        payload: Dict[str, Any],
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Запускает агента с данными из триггера.
        
        Args:
            agent_id: ID агента
            trigger: Конфигурация триггера
            payload: Входящие данные триггера
            user_id: ID пользователя (опционально)
            metadata: Дополнительные метаданные
            
        Returns:
            Результат выполнения агента
        """
        trigger_id = trigger.trigger_id
        # Обрабатываем и enum и строку
        trigger_type = trigger.type.value if hasattr(trigger.type, 'value') else str(trigger.type)
        
        logger.info(
            f"Executing agent from trigger: agent={agent_id}, "
            f"trigger={trigger_id}, type={trigger_type}"
        )
        
        # Применяем output_mapping (input_mapping - deprecated alias)
        mapping = trigger.output_mapping or trigger.input_mapping or {}
        mapped_data = self._input_mapper.map(trigger_id, payload, mapping)
        
        # Извлекаем content, variables и triggers
        content = mapped_data.get("content", "")
        variables = mapped_data.get("variables", {})
        triggers_data = mapped_data.get("triggers", {})
        
        # Формируем IDs
        task_id = str(uuid.uuid4())
        context_id = str(uuid.uuid4())
        session_id = f"{agent_id}:{context_id}"
        
        # User ID из payload или дефолтный
        effective_user_id = user_id or self._extract_user_id(trigger_type, payload)
        
        # Получаем существующий context или создаем минимальный
        existing_context = get_context()
        
            # Используем данные из существующего context
        context = Context(
            user=existing_context.user or User(
                user_id=effective_user_id,
                name=f"Trigger:{trigger_type}"
            ),
            active_company=existing_context.active_company,
            session_id=session_id,
            agent_id=agent_id,
            channel=f"trigger:{trigger_type}",
            metadata={
                **(existing_context.metadata or {}),
                "trigger_id": trigger_id,
                "trigger_type": trigger_type,
                **(metadata or {}),
            },
        )
        
        
        # Запускаем через TaskIQ
        from apps.agents.src.tasks.agent_tasks import process_agent_task
        
        final_metadata = {
            "trigger_id": trigger_id,
            "trigger_type": trigger_type,
            "variables": variables,
            "triggers": triggers_data,
            **(metadata or {}),
        }
        
        await process_agent_task.kiq(
            agent_id=agent_id,
            session_id=session_id,
            user_id=effective_user_id,
            content=content,
            skill_id="default",
            channel="a2a",  # Используем A2A канал для триггеров
            task_id=task_id,
            context_id=context_id,
            metadata=final_metadata,
            is_resume=False,
            files=None,
            context_data=context.to_dict(),
            trace_context=None,
        )
        
        logger.info(f"Trigger execution started: task_id={task_id}")
        
        return {
            "task_id": task_id,
            "session_id": session_id,
            "context_id": context_id,
            "status": "started",
        }

    
    def _extract_user_id(self, trigger_type: str, payload: Dict[str, Any]) -> str:
        """Извлекает user_id из payload в зависимости от типа триггера."""
        if trigger_type == "telegram":
            # Telegram: message.from.id
            message = payload.get("message", {})
            from_user = message.get("from", {})
            user_id = from_user.get("id")
            if user_id:
                return f"tg:{user_id}"
        
        if trigger_type == "email":
            # Email: from адрес
            from_addr = payload.get("from", "")
            if from_addr:
                return f"email:{from_addr}"
        
        return f"trigger:{trigger_type}"


class OutputActionExecutor:
    """
    Выполняет output_actions после завершения агента.
    
    Вызывается из process_agent_task после успешного выполнения агента.
    Использует MappingResolver и InputMapper для резолвинга - никакого дублирования.
    """
    
    def __init__(self):
        self._input_mapper = InputMapper()
    
    async def execute(
        self,
        output_actions: List[OutputAction],
        state: Dict[str, Any],
        trigger_config: Dict[str, Any],
        original_payload: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        Выполняет все output_actions.
        
        Args:
            output_actions: Список действий для выполнения
            state: Финальный state агента
            trigger_config: Конфигурация триггера (для channel config)
            original_payload: Исходные данные триггера
            
        Returns:
            Список результатов выполнения
        """
        from apps.agents.src.container import get_container
        from apps.agents.src.mapping import MappingResolver
        
        if not output_actions:
            return []
        
        container = get_container()
        results = []
        
        variables = state.get("variables", {})
        
        for action in output_actions:
            # Проверяем условие используя MappingResolver
            if action.condition:
                if not self._check_condition(action.condition, state):
                    logger.debug(
                        f"Output action {action.action} skipped: condition not met"
                    )
                    continue
            
            # Резолвим параметры используя MappingResolver + InputMapper
            params = self._resolve_mapping(action.mapping, state, original_payload)
            
            # Добавляем статические значения из config
            params.update(action.config)
            
            # Получаем handler
            handler = container.channel_registry.get(action.channel)
            
            # Merge trigger config с action config для channel_config
            channel_config = {**trigger_config, **action.config}
            
            try:
                result = await handler.execute_action(
                    action=action.action,
                    params=params,
                    config=channel_config,
                    variables=variables,
                )
                
                logger.info(
                    f"Output action {action.channel.value}:{action.action} executed"
                )
                results.append({"action": action.action, "result": result})
                
            except Exception as e:
                logger.error(
                    f"Output action {action.action} failed: {e}"
                )
                results.append({"action": action.action, "error": str(e)})
        
        return results
    
    def _check_condition(self, condition: str, state: Dict[str, Any]) -> bool:
        """
        Проверяет условие выполнения используя MappingResolver.
        
        Формат: "@state:field == value" или "@state:field"
        """
        from apps.agents.src.mapping import MappingResolver
        
        if not condition:
            return True
        
        # Простая проверка наличия поля
        if "==" not in condition and "!=" not in condition:
            value = MappingResolver.resolve_value(condition, state)
            return bool(value)
        
        # Парсим сравнение
        for op in ["==", "!="]:
            if op in condition:
                parts = condition.split(op)
                if len(parts) != 2:
                    return True
                
                left = MappingResolver.resolve_value(parts[0].strip(), state)
                right = self._parse_literal(parts[1].strip())
                
                if op == "==":
                    return left == right
                else:
                    return left != right
        
        return True
    
    def _parse_literal(self, value: str) -> Any:
        """Парсит литерал (true, false, число, строку)."""
        value = value.strip()
        
        if value.lower() == "true":
            return True
        if value.lower() == "false":
            return False
        if value.lower() in ("null", "none"):
            return None
        
        # Строка в кавычках
        if (value.startswith('"') and value.endswith('"')) or \
           (value.startswith("'") and value.endswith("'")):
            return value[1:-1]
        
        # Число
        try:
            return int(value)
        except ValueError:
            pass
        
        try:
            return float(value)
        except ValueError:
            pass
        
        return value
    
    def _resolve_mapping(
        self,
        mapping: Dict[str, str],
        state: Dict[str, Any],
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Резолвит маппинг параметров.
        
        Использует:
        - MappingResolver для @state:, @var:
        - InputMapper логику для @trigger:, @const:
        """
        from apps.agents.src.mapping import MappingResolver
        
        result = {}
        
        for param_name, expr in mapping.items():
            if expr.startswith("@state:") or expr.startswith("@var:"):
                # Используем MappingResolver
                result[param_name] = MappingResolver.resolve_value(expr, state)
            elif expr.startswith("@trigger:"):
                # Извлекаем из payload
                path = expr[9:]
                result[param_name] = MappingResolver.get_nested_value(payload, path)
            elif expr.startswith("@const:"):
                # Константа
                result[param_name] = expr[7:]
            else:
                # Прямое значение
                result[param_name] = expr
        
        return result


__all__ = ["TriggerExecutor", "OutputActionExecutor"]
