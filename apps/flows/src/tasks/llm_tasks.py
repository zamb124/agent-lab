"""
TaskIQ tasks для LLM вызовов.

Обеспечивает единообразное выполнение LLM через worker.
"""

from a2a.types import TaskArtifactUpdateEvent, TaskStatusUpdateEvent, TextPart

import core.tracing.attributes as trace_attributes
from apps.flows.src.tasks.task_names import TASK_INVOKE_LLM
from apps.flows_worker.broker_core import broker
from core.billing import get_billing_service
from core.billing.service import BALANCE_BLOCK_OPERATION_LLM
from core.clients.llm import get_llm
from core.company_ai import COST_ORIGIN_COMPANY, AICapability, resolve_llm_for_capability
from core.context import clear_context, get_context, set_context
from core.llm_context import LLMContextBlock
from core.logging import get_logger
from core.models.billing_models import UsageType
from core.models.context_models import Context
from core.tracing.operation_span import traced_operation
from core.types import JsonObject, JsonValue, require_json_object

logger = get_logger(__name__)


@broker.task(task_name=TASK_INVOKE_LLM, queue_name="flows_worker")
async def invoke_llm(
    messages: list[JsonObject],
    tools: list[JsonObject] | None = None,
    task_id: str | None = None,
    context_id: str | None = None,
    context_data: JsonObject | None = None,
    llm_context: JsonObject | None = None,
    llm_context_blocks: list[JsonObject] | None = None,
) -> JsonObject:
    """
    Вызывает LLM и возвращает результат.

    Args:
        messages: Список сообщений в OpenAI формате [{"role": "...", "content": "..."}]
        tools: Опциональный список tools
        task_id: ID задачи для трейсинга
        context_id: ID контекста
        context_data: Сериализованный Context (как у process_flow_task); в worker обязателен, если нет уже выставленного контекста
        llm_context: Опциональный patch контекстного слоя
        llm_context_blocks: Уже извлеченные memory/RAG/tool blocks для generic context layer

    Returns:
        {"content": "...", "reasoning": "...", "tool_calls": [...]}
    """
    previous_context = None
    if context_data is not None:
        previous_context = get_context()
        set_context(Context.from_dict(context_data))

    try:
        trace_extra: dict[str, str] = {}
        actx = get_context()
        if actx is None or actx.active_company is None:
            raise ValueError("Контекст с active_company обязателен для invoke_llm")
        if not str(actx.user.user_id).strip():
            raise ValueError("Контекст с user обязателен для invoke_llm (биллинг и уведомления)")
        uid = str(actx.user.user_id).strip()
        resolved = resolve_llm_for_capability(
            AICapability.LLM_CHAT,
            include_platform_default=True,
        )
        if resolved is None:
            raise ValueError(
                "invoke_llm: platform default для capability=llm_chat не настроен"
            )
        llm = get_llm(
            model_name=resolved.model,
            provider=resolved.provider,
            api_key=resolved.api_key,
            base_url=resolved.base_url,
            folder_id=resolved.folder_id,
            extra_request_headers=resolved.extra_request_headers,
            extra_request_body=resolved.extra_request_body,
            fallback_models=list(resolved.fallback_models or ()) or None,
        )
        if resolved.cost_origin != COST_ORIGIN_COMPANY:
            await get_billing_service().require_balance_for_billable_operation(
                actx.active_company.company_id,
                uid,
                operation_code=BALANCE_BLOCK_OPERATION_LLM,
                notification_service="flows",
            )
        trace_extra[trace_attributes.ATTR_USER_ID] = uid
        trace_extra[trace_attributes.ATTR_TENANT_COMPANY_ID] = actx.active_company.company_id

        async with traced_operation(
            "flows.llm.invoke_task",
            event_type="llm.invoke",
            operation_category="llm",
            billing_usage_type=UsageType.LLM_REQUEST.value,
            billing_resource_name=resolved.billing_resource_name,
            billing_quantity=1,
            billing_pending_settlement=True,
            extra_attributes=trace_extra if trace_extra else None,
        ) as span:
            content_parts: list[str] = []
            reasoning_parts: list[str] = []
            tool_calls: JsonValue = None
            input_tokens = 0
            output_tokens = 0

            async for event in llm.stream(
                messages=messages,
                tools=tools or [],
                task_id=task_id,
                context_id=context_id,
                llm_context=llm_context,
                llm_context_blocks=[
                    LLMContextBlock.model_validate(block)
                    for block in (llm_context_blocks or [])
                ],
            ):
                if isinstance(event, TaskArtifactUpdateEvent):
                    artifact_name = event.artifact.name
                    if event.artifact.parts:
                        for part in event.artifact.parts:
                            if isinstance(part.root, TextPart):
                                text = part.root.text
                                if artifact_name == "reasoning":
                                    reasoning_parts.append(text)
                                else:
                                    content_parts.append(text)

                if isinstance(event, TaskStatusUpdateEvent):
                    if event.status.message and event.status.message.metadata:
                        event_metadata = require_json_object(
                            event.status.message.metadata,
                            "invoke_llm.event.metadata",
                        )
                        tc = event_metadata.get("tool_calls")
                        if tc is not None:
                            tool_calls = tc
                        usage_raw = event_metadata.get("usage")
                        if usage_raw is not None:
                            usage = require_json_object(usage_raw, "invoke_llm.event.usage")
                            input_tokens_raw = usage.get("input_tokens")
                            if input_tokens_raw is None:
                                input_tokens = 0
                            elif isinstance(input_tokens_raw, int) and not isinstance(
                                input_tokens_raw,
                                bool,
                            ):
                                input_tokens = input_tokens_raw
                            else:
                                raise ValueError("invoke_llm.event.usage.input_tokens must be int")
                            output_tokens_raw = usage.get("output_tokens")
                            if output_tokens_raw is None:
                                output_tokens = 0
                            elif isinstance(output_tokens_raw, int) and not isinstance(
                                output_tokens_raw,
                                bool,
                            ):
                                output_tokens = output_tokens_raw
                            else:
                                raise ValueError("invoke_llm.event.usage.output_tokens must be int")

            total_tokens = input_tokens + output_tokens
            if total_tokens > 0:
                span.set_attribute(trace_attributes.ATTR_BILLING_QUANTITY, total_tokens)
                span.set_attribute(trace_attributes.ATTR_LLM_INPUT_TOKENS, input_tokens)
                span.set_attribute(trace_attributes.ATTR_LLM_OUTPUT_TOKENS, output_tokens)

            return {
                "content": "".join(content_parts),
                "reasoning": "".join(reasoning_parts) if reasoning_parts else None,
                "tool_calls": tool_calls,
            }
    finally:
        if context_data is not None:
            if previous_context is not None:
                set_context(previous_context)
            else:
                clear_context()
