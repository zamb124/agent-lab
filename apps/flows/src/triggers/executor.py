"""
TriggerExecutor - запуск агента при срабатывании триггера.

Получает данные из триггера, применяет input_mapping,
и запускает агента через process_flow_task.

OutputActionExecutor - выполнение output_actions после завершения агента.
"""

import uuid
from typing import Any, Dict, List, Optional

from apps.flows.src.models import TriggerConfig
from apps.flows.src.models.channel_config import OutputAction
from apps.flows.src.triggers.input_mapper import InputMapper
from apps.flows.src.triggers.output_condition import evaluate_output_action_condition
from core.context import Context, User, get_context
from core.logging import get_logger

logger = get_logger(__name__)


class TriggerExecutor:
    """
    Выполняет агента при срабатывании триггера.

    Workflow:
    1. Загружает конфиг триггера
    2. Применяет input_mapping к payload
    3. Формирует context и initial state
    4. Запускает process_flow_task
    """

    def __init__(self):
        self._input_mapper = InputMapper()

    async def execute(
        self,
        flow_id: str,
        trigger: TriggerConfig,
        payload: Dict[str, Any],
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Запускает агента с данными из триггера.

        Args:
            flow_id: ID агента
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
            f"Executing flow from trigger: flow_id={flow_id}, "
            f"trigger={trigger_id}, type={trigger_type}"
        )

        mapping = {**dict(trigger.input_mapping), **dict(trigger.output_mapping)}
        mapped_data = self._input_mapper.map(trigger_id, payload, mapping)

        content = mapped_data.get("content", "")
        triggers_data = mapped_data.get("triggers", {})

        # Формируем IDs
        task_id = str(uuid.uuid4())
        context_id = str(uuid.uuid4())
        session_id = f"{flow_id}:{context_id}"

        # User ID из payload или дефолтный
        effective_user_id = user_id or self._extract_user_id(trigger_type, payload)

        # Получаем существующий context или создаем минимальный
        existing_context = get_context()
        existing_user = existing_context.user if existing_context and existing_context.user else None
        existing_company = existing_context.active_company if existing_context else None
        existing_metadata = existing_context.metadata if existing_context else {}

        # Используем данные из существующего context
        context = Context(
            user=existing_user or User(
                user_id=effective_user_id,
                name=f"Trigger:{trigger_type}"
            ),
            active_company=existing_company,
            session_id=session_id,
            flow_id=flow_id,
            channel=f"trigger:{trigger_type}",
            metadata={
                **(existing_metadata or {}),
                "trigger_id": trigger_id,
                "trigger_type": trigger_type,
                **(metadata or {}),
            },
        )


        # Запускаем через TaskIQ
        from apps.flows.src.tasks.flow_tasks import process_flow_task

        final_metadata = {
            "trigger_id": trigger_id,
            "trigger_type": trigger_type,
            "triggers": triggers_data,
            **(metadata or {}),
        }

        await process_flow_task.kiq(
            flow_id=flow_id,
            session_id=session_id,
            user_id=effective_user_id,
            content=content,
            branch_id=trigger.branch_id,
            channel=("telegram" if trigger_type == "telegram" else "a2a"),
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
            cq = payload.get("callback_query")
            if isinstance(cq, dict) and cq:
                from_user_raw = cq.get("from")
                from_user = from_user_raw if isinstance(from_user_raw, dict) else {}
                uid = from_user.get("id")
                if uid is not None:
                    return f"tg:{uid}"
            message_raw = payload.get("message")
            message = message_raw if isinstance(message_raw, dict) else {}
            from_user_raw = message.get("from")
            from_user = from_user_raw if isinstance(from_user_raw, dict) else {}
            user_id = from_user.get("id")
            if user_id is not None:
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

    Вызывается из BaseChannel.process_task после успешного run flow без interrupt
    и без breakpoint, когда в metadata задачи передан trigger_id, триггер включён
    в конфиге flow и для него разрешён пост-выход (см. effective_output_actions_for_trigger).
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
        from apps.flows.src.container import get_container

        if not output_actions:
            return []

        container = get_container()
        results = []

        variables = state.get("variables", {})

        for action in output_actions:
            if action.condition:
                if not evaluate_output_action_condition(action.condition, state):
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

                ch_label = (
                    action.channel.value
                    if hasattr(action.channel, "value")
                    else str(action.channel)
                )
                logger.info(
                    f"Output action {ch_label}:{action.action} executed"
                )
                results.append({"action": action.action, "result": result})

            except Exception as e:
                logger.error(
                    f"Output action {action.action} failed: {e}"
                )
                results.append({"action": action.action, "error": str(e)})

        return results

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
        from apps.flows.src.mapping import MappingResolver

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
