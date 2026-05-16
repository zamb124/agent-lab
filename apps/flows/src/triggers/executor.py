"""
TriggerExecutor - запуск агента при срабатывании триггера.

Получает данные из триггера, применяет input_mapping,
и запускает агента через process_flow_task.

"""

import uuid
import importlib
from typing import Any

from apps.flows.src.models import TriggerConfig
from apps.flows.src.triggers.input_mapper import InputMapper
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

    def __init__(self) -> None:
        self._input_mapper = InputMapper()

    async def execute(
        self,
        flow_id: str,
        trigger: TriggerConfig,
        payload: dict[str, Any],
        user_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
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
        flow_tasks_module = importlib.import_module("apps.flows.src.tasks.flow_tasks")
        process_flow_task = getattr(flow_tasks_module, "process_flow_task")

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


    def _extract_user_id(self, trigger_type: str, payload: dict[str, Any]) -> str:
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


__all__ = ["TriggerExecutor"]
