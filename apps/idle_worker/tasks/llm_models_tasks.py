"""TaskIQ задачи синхронизации LLM моделей."""

from typing import TypedDict

from apps.idle_worker.broker import broker as idle_broker
from apps.idle_worker.container import IdleWorkerContainer, get_container
from core.context import Context, clear_context, set_context
from core.identity.system_bootstrap import (
    SYSTEM_ADMIN_EMAIL,
    ensure_system_admin_membership,
)
from core.logging import get_logger
from core.models.i18n_models import Language
from core.models.identity_models import Company, User
from core.utils.tokens import get_token_service

logger = get_logger(__name__)


class LLMModelsSyncTaskResult(TypedDict):
    providers: dict[str, int]
    total: int


async def build_scheduler_auth_context(
    container: IdleWorkerContainer, trace_id: str, session_id: str
) -> Context:
    """Создаёт системный контекст для фоновых задач с авторизацией."""
    company, user = await ensure_system_admin_membership(
        company_repository=container.company_repository,
        subdomain_repository=container.subdomain_repository,
        user_repository=container.user_repository,
    )
    if user is None:
        raise ValueError(
            f"Нет пользователя с email {SYSTEM_ADMIN_EMAIL}: контекст для фоновых задач не собрать"
        )
    roles = user.companies.get(company.company_id, [])
    auth_token = get_token_service().create_token(
        user_id=user.user_id,
        company_id=company.company_id,
        roles=roles,
    )
    return Context(
        user=User(user_id=user.user_id, name=user.name or user.user_id, groups=user.groups),
        host="system",
        session_id=session_id,
        channel="system",
        language=Language.RU,
        active_company=Company(company_id=company.company_id, name=company.name, subdomain=company.subdomain),
        user_companies=[],
        trace_id=trace_id,
        auth_token=auth_token,
    )


@idle_broker.task(task_name="sync_llm_models_task", queue_name="idle")
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
    scheduler_context = await build_scheduler_auth_context(
        container=container,
        trace_id=f"scheduler:sync_llm_models:{schedule_task_id}",
        session_id=f"sync_llm_models:{schedule_task_id}",
    )
    set_context(scheduler_context)

    try:
        result = await container.llm_models_service.sync_all_providers()
        total_synced = sum(result.values())
        logger.info("LLM models sync completed: %s total=%s", result, total_synced)
        return {"providers": result, "total": total_synced}
    finally:
        clear_context()
