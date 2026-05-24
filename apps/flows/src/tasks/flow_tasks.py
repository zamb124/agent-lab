"""Задачи для асинхронной обработки flows."""

from apps.flows.src.channels.types import PreparedTaskParams
from apps.flows.src.container import get_container
from apps.flows.src.tasks.task_names import TASK_PROCESS_FLOW
from apps.flows_worker.broker import broker
from core.context import Context, set_context
from core.files.file_ref import FileRef
from core.logging import get_logger
from core.tracing.context import set_current_trace_context
from core.types import JsonObject, require_json_object

logger = get_logger(__name__)


@broker.task(task_name=TASK_PROCESS_FLOW, queue_name="flows_worker")
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
    is_resume: bool = False,
    files: list[JsonObject] | None = None,
    context_data: JsonObject | None = None,
    trace_context: JsonObject | None = None,
) -> JsonObject:
    """
    Обрабатывает запрос через агента.

    Делегирует выполнение в соответствующий канал (BaseChannel.process_task).

    Args:
        flow_id: ID агента
        session_id: ID сессии
        user_id: ID пользователя
        content: Содержимое сообщения
        branch_id: ID skill для агента
        channel: Канал ("a2a", "telegram", "whatsapp")
        task_id: ID задачи A2A
        context_id: ID контекста A2A
        metadata: Дополнительные данные
        is_resume: True если это продолжение после interrupt
        files: Информация о прикрепленных файлах
        context_data: Сериализованный Context из middleware (всегда должен быть)
        trace_context: Сериализованный TraceContext для трейсинга

    Returns:
        Результат выполнения
    """
    if context_data is None:
        raise ValueError("Context is required. Context must be created in middleware.")

    if trace_context:
        set_current_trace_context(trace_context)

    context = Context.from_dict(context_data)
    context.session_id = session_id
    set_context(context)

    channel_instance = get_container().get_channel(channel, flow_id)
    file_refs = [FileRef.model_validate(item) for item in files] if files is not None else []

    params = PreparedTaskParams(
        task_id=task_id or "",
        context_id=context_id or session_id,
        session_id=session_id,
        content=content,
        branch_id=branch_id,
        is_resume=is_resume,
        files_data=file_refs,
        message=None,
        metadata=metadata,
        user_id=user_id,
    )

    result = await channel_instance.process_task(params)
    return require_json_object(
        result.model_dump(mode="json", exclude_none=False),
        "process_flow_task.result",
    )
