"""
Документы OnlyOffice — BFF и Lit UI (процесс office, публичный путь /documents).
"""

import importlib
from pathlib import Path

from fastapi import FastAPI

from apps.office.api.bff import router as bff_router
from apps.office.config import OfficeSettings, get_office_settings
from apps.office.container import OfficeContainer, get_office_container
from apps.office.dependencies import ContainerDep
from apps.office.realtime.command_router import register_office_ws_commands
from core.app import create_service_app
from core.app.health_payload import build_health_payload
from core.app.spa import mount_service_spa
from core.logging import get_logger

# side-effect: register platform event catalog types
_ = importlib.import_module("apps.office.events")

logger = get_logger(__name__)


async def on_startup(app: FastAPI, container: OfficeContainer, settings: OfficeSettings) -> None:
    _ = app, container, settings
    register_office_ws_commands()
    logger.info("office.documents.command.router.op_")


def _api_routers():
    return [bff_router]


app = create_service_app(
    service_name="office",
    settings_class=OfficeSettings,
    get_container=get_office_container,
    services_spa_index=Path(__file__).parent / "ui" / "index.html",
    routers=_api_routers(),
    on_startup=on_startup,
    title="Documents",
    description="Документы Office через OnlyOffice Document Server",
    api_version="v1",
    include_crud_routers=False,
    documentation_gateway_prefix="documents",
)


@app.get("/documents/health")
async def documents_health(container: ContainerDep):
    """Тот же JSON, что /health и /office/health; публичный префикс UI — /documents."""
    _ = container
    return build_health_payload(get_office_settings())


mount_service_spa(app, public_segment="documents", ui_dir=Path(__file__).parent / "ui")

if __name__ == "__main__":
    from core.app.server import serve

    serve("office", "apps.office.main:app", get_office_settings())
