"""TaskIQ задачи синхронизации LLM моделей."""

from apps.broker.broker import broker
from apps.flows.src.container import get_container
from core.logging import get_logger

logger = get_logger(__name__)


@broker.task(task_name="sync_llm_models_task", queue_name="default")
async def sync_llm_models_task() -> dict[str, int]:
    """Синхронизирует модели от всех настроенных LLM провайдеров."""
    container = get_container()
    result = await container.llm_models_service.sync_all_providers()
    logger.info("LLM models sync completed: %s", result)
    return result
