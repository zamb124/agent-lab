"""
NetWorkle Service - FastAPI приложение для управления NetWorkle.

Порт: 8003
БД: crm_db (service) + shared_db
"""

import importlib
from pathlib import Path

from fastapi import FastAPI

from apps.crm.api.router import router as api_router
from apps.crm.config import CRMSettings
from apps.crm.di import CrmDi
from apps.crm.integrations.registry import IntegrationRegistry
from apps.crm.realtime.command_router import CRM_OPERATIONS
from apps.crm.services.company_init_service import CompanyInitService
from apps.crm.services.task_service import TaskService
from core.app import create_service_app
from core.app.spa import mount_service_spa
from core.config import get_settings
from core.config.testing import in_xdist_worker, is_testing
from core.context import reset_context, set_context
from core.di import recipe
from core.integrations.models import IntegrationCredential
from core.integrations.oauth_service import set_oauth_credential_saved_hook
from core.logging import get_logger
from core.models.context_models import Context
from core.models.identity_models import Company, User

# side-effect: register platform event catalog types
_ = importlib.import_module("apps.crm.events")

logger = get_logger(__name__)


async def crm_http_startup(
    company_init_service: CompanyInitService,
    integration_registry: IntegrationRegistry,
    task_service: TaskService,
) -> None:
    startup_context = set_context(
        Context(
            user=User(user_id="system", name="System"),
            active_company=Company(company_id="system", name="System"),
            channel="lifespan",
        )
    )
    # В тест-контуре reseed+reconcile делает test-up один раз
    # (scripts.testing.service_seed до спауна стека): каждый granian-воркер
    # и in-process lifespan идут insert-only fast-path по CompanyMapping без
    # очереди на pg_advisory_lock (~50s сериализовано на процесс → hang_guard)
    # и без перетирания active-задач соседних процессов.
    test_mode = is_testing() or in_xdist_worker()
    try:
        init_result = await company_init_service.initialize_company(
            "system",
            reseed=not test_mode,
        )
        logger.info("crm.entities.system", result=init_result)
    finally:
        reset_context(startup_context)

    async def _on_oauth_credential_saved(credential: IntegrationCredential) -> None:
        oauth_context = set_context(
            Context(
                user=User(user_id=credential.user_id, name="OAuth"),
                active_company=Company(
                    company_id=credential.company_id,
                    name="OAuth",
                ),
                channel="integration_oauth",
            )
        )
        try:
            await integration_registry.dispatch_credential_saved(credential)
        finally:
            reset_context(oauth_context)

    set_oauth_credential_saved_hook(_on_oauth_credential_saved)

    if not test_mode:
        reconciled = await task_service.reconcile_stale_worker_tasks()
        if reconciled:
            logger.warning(
                "crm.reconcile_stale_crm_tasks_on_api_startup",
                service="crm",
                reconciled=reconciled,
            )


async def crm_test_stack_seed(company_init_service: CompanyInitService) -> None:
    """Reseed системной компании в ``test-up``: один процесс до спауна стека
    вместо полного reseed под ``pg_advisory_lock`` в каждом granian-воркере."""
    seed_context = set_context(
        Context(
            user=User(user_id="system", name="System"),
            active_company=Company(company_id="system", name="System"),
            channel="lifespan",
        )
    )
    try:
        init_result = await company_init_service.initialize_company("system", reseed=True)
        logger.info("crm.entities.system", result=init_result)
    finally:
        reset_context(seed_context)


async def crm_test_stack_reconcile(task_service: TaskService) -> None:
    """Reconcile stale-задач после readiness стека: broadcast идёт в realtime."""
    reconciled = await task_service.reconcile_stale_worker_tasks()
    if reconciled:
        logger.warning(
            "crm.reconcile_stale_crm_tasks_on_api_startup",
            service="crm",
            reconciled=reconciled,
        )


def create_app() -> FastAPI:
    return create_service_app(
        "crm",
        CRMSettings,
        CrmDi,
        database="crm_url",
        operations=CRM_OPERATIONS,
        lifecycle=(recipe(crm_http_startup),),
        routers=[api_router],
        services_spa_index=Path(__file__).parent / "ui" / "index.html",
        title="NetWorkle Service",
        description="API для управления NetWorkle: сущности, заметки, задачи, связи",
    )


app = create_app()

mount_service_spa(
    app,
    public_segment="crm",
    ui_dir=Path(__file__).parent / "ui",
    excluded_prefixes=("api/", "ui/static/"),
)


if __name__ == "__main__":
    from core.app.server import serve

    serve("crm", "apps.crm.main:app", get_settings())
