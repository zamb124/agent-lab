"""
TaskIQ tasks для LLM вызовов.

Обеспечивает единообразное выполнение LLM через worker.
"""

from typing import Any, Dict, List, Optional

from core.billing import get_billing_service
from core.clients.llm import get_llm
from core.context import get_context
from core.logging import get_logger
from core.models.billing_models import UsageType
from core.tracing import attributes as trace_attributes
from core.tracing.operation_span import traced_operation
from apps.flows_worker.broker import broker

logger = get_logger(__name__)


@broker.task(task_name="invoke_llm", queue_name="flows_worker")
async def invoke_llm(
    messages: List[Dict[str, str]],
    tools: Optional[List[Dict[str, Any]]] = None,
    task_id: Optional[str] = None,
    context_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Вызывает LLM и возвращает результат.
    
    Args:
        messages: Список сообщений в OpenAI формате [{"role": "...", "content": "..."}]
        tools: Опциональный список tools
        task_id: ID задачи для трейсинга
        context_id: ID контекста
        
    Returns:
        {"content": "...", "reasoning": "...", "tool_calls": [...]}
    """
    llm = get_llm()

    trace_extra: dict[str, str] = {}
    actx = get_context()
    if actx is None or actx.active_company is None:
        raise ValueError("Контекст с active_company обязателен для invoke_llm")
    await get_billing_service().require_balance_for_billable_operation(
        actx.active_company.company_id
    )
    if actx.user is not None and str(actx.user.user_id).strip() != "":
        trace_extra[trace_attributes.ATTR_USER_ID] = str(actx.user.user_id).strip()
    trace_extra[trace_attributes.ATTR_TENANT_COMPANY_ID] = actx.active_company.company_id

    async with traced_operation(
        "flows.llm.invoke_task",
        event_type="llm.invoke",
        operation_category="llm",
        billing_usage_type=UsageType.LLM_REQUEST.value,
        billing_resource_name="llm:default",
        billing_quantity=1,
        billing_pending_settlement=True,
        extra_attributes=trace_extra if trace_extra else None,
    ) as span:
        content_parts: list[str] = []
        reasoning_parts: list[str] = []
        tool_calls = None
        input_tokens = 0
        output_tokens = 0

        async for event in llm.stream(
            messages=messages,
            tools=tools or [],
            task_id=task_id,
            context_id=context_id,
        ):
            if hasattr(event, "artifact") and event.artifact:
                artifact_name = event.artifact.name
                if event.artifact.parts:
                    for part in event.artifact.parts:
                        if hasattr(part, "root") and hasattr(part.root, "text"):
                            text = part.root.text
                            if artifact_name == "reasoning":
                                reasoning_parts.append(text)
                            else:
                                content_parts.append(text)

            if hasattr(event, "status") and event.status:
                if event.status.message and event.status.message.metadata:
                    tc = event.status.message.metadata.get("tool_calls")
                    if tc:
                        tool_calls = tc
                    usage = event.status.message.metadata.get("usage")
                    if usage:
                        input_tokens = usage.get("input_tokens", 0)
                        output_tokens = usage.get("output_tokens", 0)

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

