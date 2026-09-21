"""Declaration-модуль задач AI model catalog (очередь ``idle``).

Лёгкий: только объявления. Импортируется producer'ами (``LLMModelsService`` для
расписаний scheduler) и impl-модулями idle worker (``@platform_task``).
"""

from core.tasks import declare_task

TASK_SYNC_LLM_MODELS = declare_task("sync_llm_models_task", queue="idle", scheduled=True)

TASK_REFRESH_PLATFORM_FREE_MODELS = declare_task(
    "refresh_platform_free_models_task", queue="idle", scheduled=True
)

__all__ = ["TASK_REFRESH_PLATFORM_FREE_MODELS", "TASK_SYNC_LLM_MODELS"]
