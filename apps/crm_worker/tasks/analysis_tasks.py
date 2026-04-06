"""
TaskIQ: тяжёлый analyze и apply черновика AI — выполнение в очереди crm.

HTTP CRM остаётся синхронным для клиента: kiq + wait_result на том же Redis backend.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import ValidationError

from apps.crm.container import get_crm_container
from apps.crm.models.api import AIAnalyzeRequest
from apps.crm.taskiq_analyze_errors import format_validation_for_taskiq
from apps.crm_worker.broker import broker
from apps.crm_worker.tasks.daily_summary_tasks import _set_crm_context
from core.tracing import attributes as trace_attributes
from core.tracing.operation_span import traced_operation


@broker.task
async def apply_analysis_draft_task(
    note_id: str,
    company_id: str,
    namespace: str,
    auth_token: Optional[str],
    user_id: str,
) -> dict[str, Any]:
    _set_crm_context(company_id, namespace, auth_token, user_id)
    container = get_crm_container()
    async with traced_operation(
        "crm.worker.apply_analysis_draft",
        event_type="crm.worker",
        operation_category="sync_command",
        resource_type="crm_note",
        resource_id=note_id,
        extra_attributes={
            trace_attributes.ATTR_TENANT_COMPANY_ID: company_id,
            trace_attributes.ATTR_USER_ID: user_id,
        },
    ):
        result = await container.entity_service.apply_analysis_draft(note_id)
    return result.model_dump(mode="json")


@broker.task
async def analyze_text_with_ai_task(
    request_payload: dict[str, Any],
    note_id: Optional[str],
    check_duplicates: bool,
    company_id: str,
    namespace: str,
    auth_token: Optional[str],
    user_id: str,
    interface_language: str,
) -> dict[str, Any]:
    _set_crm_context(
        company_id,
        namespace,
        auth_token,
        user_id,
        interface_language=interface_language,
    )
    try:
        request = AIAnalyzeRequest.model_validate(request_payload)
    except ValidationError as exc:
        raise ValueError(format_validation_for_taskiq(exc.errors())) from exc
    container = get_crm_container()
    resource_id = note_id if note_id is not None else "new"
    try:
        async with traced_operation(
            "crm.worker.analyze_text_with_ai",
            event_type="crm.worker",
            operation_category="sync_command",
            resource_type="crm_analyze",
            resource_id=resource_id,
            extra_attributes={
                trace_attributes.ATTR_TENANT_COMPANY_ID: company_id,
                trace_attributes.ATTR_USER_ID: user_id,
            },
        ):
            result = await container.entity_service.analyze_text_with_ai(
                request,
                check_duplicates=check_duplicates,
                note_id=note_id,
            )
    except ValidationError as exc:
        raise ValueError(format_validation_for_taskiq(exc.errors())) from exc
    return result.model_dump(mode="json")
