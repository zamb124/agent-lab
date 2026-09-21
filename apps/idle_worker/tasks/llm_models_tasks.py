"""TaskIQ задачи синхронизации LLM моделей."""

from typing import TypedDict

from apps.idle_worker.container import get_container
from core.ai.task_names import TASK_SYNC_LLM_MODELS
from core.context import clear_context, set_context
from core.identity.system_bootstrap import build_system_admin_job_context
from core.logging import get_logger
from core.tasks import platform_task

logger = get_logger(__name__)


class LLMModelsSyncTaskResult(TypedDict):
    providers: dict[str, int]
    total: int


@platform_task(TASK_SYNC_LLM_MODELS)
async def sync_llm_models_task(
    schedule_task_id: str | None = None,
    company_id: str | None = None,
    system_task: str | None = None,
) -> LLMModelsSyncTaskResult:
    """Синхронизирует модели от всех настроенных LLM провайдеров."""
    _ = company_id
    _ = system_task
    container = get_container()

    # Создаём системный контекст для доступа к сервису
    scheduler_context = await build_system_admin_job_context(
        company_repository=container.company_repository,
        user_repository=container.user_repository,
        trace_id=f"scheduler:sync_llm_models:{schedule_task_id}",
        session_id=f"sync_llm_models:{schedule_task_id}",
    )
    _ = set_context(scheduler_context)

    try:
        result = await container.llm_models_service.sync_all_providers()
        total_synced = sum(result.values())
        logger.info("idle.llm.models.sync.completed.total", result=result, total=total_synced)
        return {"providers": result, "total": total_synced}
    finally:
        clear_context()
