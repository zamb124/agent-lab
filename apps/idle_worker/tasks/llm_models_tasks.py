"""TaskIQ задачи синхронизации LLM моделей."""

from core.clients.service_client import ServiceClient
from apps.idle_worker.broker import broker as idle_broker
from core.logging import get_logger

logger = get_logger(__name__)


@idle_broker.task(task_name="sync_llm_models_task", queue_name="idle")
async def sync_llm_models_task(
    scheduler_task_id: str | None = None,
    company_id: str | None = None,
    system_task: str | None = None,
) -> dict[str, int]:
    """Синхронизирует модели от всех настроенных LLM провайдеров."""
    service_client = ServiceClient()
    result = await service_client.post("flows", "/registry/models/sync")
    logger.info("LLM models sync completed: %s", result)
    return result
