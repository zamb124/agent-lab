"""Задачи для асинхронной обработки flows."""

from a2a.types import Message

from apps.flows.di import Di
from apps.flows.src.channels.factory import get_channel
from apps.flows.src.channels.types import PreparedTaskParams
from apps.flows.src.tasks.task_names import TASK_PROCESS_FLOW
from core.a2a import message_from_json_dict
from core.context import set_context
from core.files.file_ref import FileRef
from core.flow_ui.action import ui_action_from_message
from core.logging import get_logger
from core.models.context_models import Context
from core.tasks import platform_task
from core.tracing.context import set_current_trace_context
from core.types import JsonObject, require_json_object

logger = get_logger(__name__)


@platform_task(TASK_PROCESS_FLOW)
async def process_flow_task(
    flow_id: str,
    session_id: str,
    user_id: str,
    content: str,
    branch_id: str = "default",
    channel: str = "a2a",
    task_id: str | None = None,
    context_id: str | None = None,
    metadata: JsonObject | None = None,
    message: JsonObject | None = None,
    is_resume: bool = False,
    files: list[JsonObject] | None = None,
    context_data: JsonObject | None = None,
    trace_context: JsonObject | None = None,
    initiator_user_id: str | None = None,
    *,
    di: Di,
) -> JsonObject:
    """
    Обрабатывает запрос через агента.

    Делегирует выполнение в соответствующий канал (BaseChannel.process_task).

    Аргументы:
        flow_id: ID агента
        session_id: ID сессии
        user_id: ID пользователя
        content: Содержимое сообщения
        branch_id: ID skill для агента
        channel: Канал ("a2a", "telegram", "webhook")
        task_id: ID задачи A2A
        context_id: ID контекста A2A
        metadata: Дополнительные данные
        is_resume: True если это продолжение после interrupt
        files: Информация о прикрепленных файлах
        context_data: Сериализованный Context из middleware (всегда должен быть)
        trace_context: Сериализованный TraceContext для трейсинга

    Возвращает:
        Результат выполнения
    """
    if context_data is None:
        raise ValueError("Context is required. Context must be created in middleware.")

    if trace_context:
        set_current_trace_context(trace_context)

    context = Context.from_dict(context_data)
    context.session_id = session_id
    _ = set_context(context)

    channel_instance = get_channel(
        channel,
        flow_id,
        variables_service=di.variables_service,
        authz_service=di.authz_service,
        workflow_runtime=di.workflow_runtime,
        redis_client=di.redis_client,
        handoff_orchestrator_service=di.handoff_orchestrator_service,
        flow_factory=di.flow_factory,
        tool_registry=di.tool_registry,
        projection_service=di.a2a_task_projection_service,
        shared_storage=di.shared_storage,
        channel_registry=di.channel_registry,
        mail_service=di.mail_service,
        flow_ui_share_service=di.flow_ui_share_service,
        hitl_conversation_service=di.hitl_conversation_service,
        files_service=di.files_service,
    )
    file_refs = [FileRef.model_validate(item) for item in files] if files is not None else []
    parsed_message: Message | None = (
        message_from_json_dict(message) if message is not None else None
    )
    # TaskIQ везёт только JSON сообщения, поэтому ui-action Part разбирается заново в worker.
    ui_action = ui_action_from_message(parsed_message) if parsed_message is not None else None

    params = PreparedTaskParams(
        task_id=task_id or "",
        context_id=context_id or session_id,
        session_id=session_id,
        content=content,
        branch_id=branch_id,
        is_resume=is_resume,
        files_data=file_refs,
        message=parsed_message,
        metadata=metadata,
        user_id=user_id,
        initiator_user_id=initiator_user_id,
        ui_action=ui_action,
    )

    result = await channel_instance.process_task(params)
    return require_json_object(
        result.model_dump(mode="json", exclude_none=False),
        "process_flow_task.result",
    )
