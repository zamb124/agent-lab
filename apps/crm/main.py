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
from apps.crm.container import CRMContainer, get_crm_container
from apps.crm.realtime.command_router import register_crm_ws_commands
from core.app import create_service_app
from core.app.spa import mount_service_spa
from core.config import get_settings
from core.context import clear_context, get_context, set_context
from core.integrations.models import IntegrationCredential
from core.integrations.oauth_service import set_oauth_credential_saved_hook
from core.logging import get_logger
from core.models.context_models import Context
from core.models.identity_models import Company, User

# side-effect: register platform event catalog types
_ = importlib.import_module("apps.crm.events")

logger = get_logger(__name__)


async def on_startup(_app: FastAPI, container: CRMContainer, _settings: CRMSettings) -> None:
    """Кастомная логика при старте"""
    register_crm_ws_commands()
    _ = set_context(
        Context(
            user=User(user_id="system", name="System"),
            active_company=Company(company_id="system", name="System"),
            channel="lifespan",
        )
    )
    try:
        init_result = await container.company_init_service.initialize_company(
            "system",
            reseed=True,
        )
        logger.info("crm.entities.system", result=init_result)
    finally:
        clear_context()

    async def _on_oauth_credential_saved(credential: IntegrationCredential) -> None:
        prev = get_context()
        _ = set_context(
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
            await container.integration_registry.dispatch_credential_saved(credential)
        finally:
            if prev is not None:
                _ = set_context(prev)
            else:
                clear_context()

    set_oauth_credential_saved_hook(_on_oauth_credential_saved)

    reconciled = await container.task_service.reconcile_stale_worker_tasks()
    if reconciled:
        logger.warning(
            "crm.reconcile_stale_crm_tasks_on_api_startup",
            service="crm",
            reconciled=reconciled,
        )


def create_app() -> FastAPI:
    """Создает FastAPI приложение"""
    return create_service_app(
        service_name="crm",
        settings_class=CRMSettings,
        get_container=get_crm_container,
        routers=[api_router],
        on_startup=on_startup,
        services_spa_index=Path(__file__).parent / "ui" / "index.html",
        title="NetWorkle Service",
        description="API для управления NetWorkle: сущности, заметки, задачи, связи",
        include_crud_routers=False,
    )


app = create_app()

_NODE_MODULES = Path(__file__).parent.parent.parent / "node_modules"
mount_service_spa(
    app,
    public_segment="crm",
    ui_dir=Path(__file__).parent / "ui",
    excluded_prefixes=("api/", "ui/static/", "ui/vendor/"),
    extra_static_mounts=(
        (
            "/crm/ui/vendor/3d-force-graph",
            _NODE_MODULES / "3d-force-graph" / "dist",
            "crm_ui_vendor_3d_force_graph",
        ),
        ("/crm/ui/vendor/three", _NODE_MODULES / "three" / "build", "crm_ui_vendor_three"),
    ),
)


if __name__ == "__main__":
    from core.app.server import serve

    serve("crm", "apps.crm.main:app", get_settings())
