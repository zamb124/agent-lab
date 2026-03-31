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
) -> dict[str, Any]:
    _set_crm_context(company_id, namespace, auth_token, user_id)
    try:
        request = AIAnalyzeRequest.model_validate(request_payload)
    except ValidationError as exc:
        raise ValueError(format_validation_for_taskiq(exc.errors())) from exc
    container = get_crm_container()
    try:
        result = await container.entity_service.analyze_text_with_ai(
            request,
            check_duplicates=check_duplicates,
            note_id=note_id,
        )
    except ValidationError as exc:
        raise ValueError(format_validation_for_taskiq(exc.errors())) from exc
    return result.model_dump(mode="json")
