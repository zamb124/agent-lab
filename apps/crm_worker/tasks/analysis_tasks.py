"""
TaskIQ: единая задача обработки заметки (analyze / apply / process).

HTTP CRM остаётся синхронным для клиента: kiq + wait_result на том же Redis backend.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import ValidationError

from apps.crm.container import get_crm_container
from apps.crm.models.api import NoteProcessingConfig
from apps.crm.taskiq_analyze_errors import format_validation_for_taskiq
from apps.crm_worker.broker import broker
from apps.crm_worker.tasks.daily_summary_tasks import _set_crm_context
from core.tracing import attributes as trace_attributes
from core.tracing.operation_span import traced_operation


@broker.task
async def process_note_task(
    note_id: str,
    company_id: str,
    namespace: str,
    auth_token: Optional[str],
    user_id: str,
    interface_language: str,
    config_payload: dict[str, Any],
    mode: str,
) -> dict[str, Any]:
    """mode: "analyze" | "apply" | "process"."""
    _set_crm_context(
        company_id,
        namespace,
        auth_token,
        user_id,
        interface_language=interface_language,
    )
    container = get_crm_container()
    pipeline = container.note_processing_service

    try:
        config = NoteProcessingConfig.model_validate(config_payload)
    except ValidationError as exc:
        raise ValueError(format_validation_for_taskiq(exc.errors())) from exc

    try:
        async with traced_operation(
            f"crm.worker.note_{mode}",
            event_type="crm.worker",
            operation_category="sync_command",
            resource_type="crm_note",
            resource_id=note_id,
            extra_attributes={
                trace_attributes.ATTR_TENANT_COMPANY_ID: company_id,
                trace_attributes.ATTR_USER_ID: user_id,
            },
        ):
            if mode == "analyze":
                result = await pipeline.analyze(note_id, config)
            elif mode == "apply":
                result = await pipeline.apply(note_id)
            elif mode == "process":
                result = await pipeline.process(note_id, config)
            else:
                raise ValueError(f"Unknown mode: {mode}")
    except ValidationError as exc:
        raise ValueError(format_validation_for_taskiq(exc.errors())) from exc

    return result.model_dump(mode="json")
