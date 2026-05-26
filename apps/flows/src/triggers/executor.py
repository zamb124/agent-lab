"""
TriggerExecutor - запуск агента при срабатывании триггера.

Получает данные из триггера, применяет input_mapping,
и запускает агента через process_flow_task.

"""

import uuid

from apps.flows.src.models import TriggerConfig
from apps.flows.src.tasks.task_names import TASK_PROCESS_FLOW
from apps.flows.src.triggers.input_mapper import InputMapper
from apps.flows_worker.broker_core import broker as flows_broker
from core.context import Context, User, get_context
from core.logging import get_logger
from core.tasks.kicker import kiq_task_name_with_context
from core.types import JsonObject, require_json_object

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
        self._input_mapper: InputMapper = InputMapper()

    async def execute(
        self,
        flow_id: str,
        trigger: TriggerConfig,
        payload: JsonObject,
        user_id: str | None = None,
        metadata: JsonObject | None = None,
    ) -> JsonObject:
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
        trigger_type = trigger.type.value

        logger.info(
            "Executing flow from trigger: flow_id=%s, trigger=%s, type=%s",
            flow_id,
            trigger_id,
            trigger_type,
        )

        mapping = {**dict(trigger.input_mapping), **dict(trigger.output_mapping)}
        mapped_data = self._input_mapper.map(trigger_id, payload, mapping)

        content_raw = mapped_data["content"]
        if not isinstance(content_raw, str):
            raise TypeError("Trigger mapped content must be a string")
        content = content_raw
        triggers_data = require_json_object(mapped_data["triggers"], "trigger mapped data")

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

        final_metadata: JsonObject = {
            "trigger_id": trigger_id,
            "trigger_type": trigger_type,
            "triggers": triggers_data,
            **(metadata or {}),
        }

        _ = await kiq_task_name_with_context(
            TASK_PROCESS_FLOW,
            flows_broker,
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
            background_kind="trigger",
        )

        logger.info(f"Trigger execution started: task_id={task_id}")

        return {
            "task_id": task_id,
            "session_id": session_id,
            "context_id": context_id,
            "status": "started",
        }


    def _extract_user_id(self, trigger_type: str, payload: JsonObject) -> str:
        """Извлекает user_id из payload в зависимости от типа триггера."""
        if trigger_type == "telegram":
            cq = payload.get("callback_query")
            if cq is not None:
                callback_query = require_json_object(cq, "telegram.callback_query")
                from_user_raw = callback_query.get("from")
                if from_user_raw is None:
                    raise ValueError("telegram.callback_query.from is required")
                from_user = require_json_object(from_user_raw, "telegram.callback_query.from")
                uid = from_user.get("id")
                if uid is not None:
                    return f"tg:{uid}"
            message_raw = payload.get("message")
            if message_raw is None:
                return f"trigger:{trigger_type}"
            message = require_json_object(message_raw, "telegram.message")
            from_user_raw = message.get("from")
            if from_user_raw is None:
                raise ValueError("telegram.message.from is required")
            from_user = require_json_object(from_user_raw, "telegram.message.from")
            user_id = from_user.get("id")
            if user_id is not None:
                return f"tg:{user_id}"

        if trigger_type == "email":
            # Email: from адрес
            from_addr = payload.get("from")
            if isinstance(from_addr, str) and from_addr:
                return f"email:{from_addr}"

        return f"trigger:{trigger_type}"


__all__ = ["TriggerExecutor"]
