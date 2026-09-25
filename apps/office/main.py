"""
Документы OnlyOffice — BFF и Lit UI (процесс office, публичный путь /documents).
"""

import importlib
from pathlib import Path

from apps.office.api.bff import router as bff_router
from apps.office.config import OfficeSettings, get_office_settings
from apps.office.di import OfficeDi
from apps.office.realtime.command_router import OFFICE_OPERATIONS
from core.app import create_service_app
from core.app.health_payload import build_health_payload
from core.app.spa import mount_service_spa
from core.di import recipe
from core.logging import get_logger

# side-effect: register platform event catalog types
_ = importlib.import_module("apps.office.events")

logger = get_logger(__name__)


async def log_office_startup() -> None:
    logger.info("office.documents.command.router.op_")


app = create_service_app(
    "office",
    OfficeSettings,
    OfficeDi,
    database="office_url",
    operations=OFFICE_OPERATIONS,
    lifecycle=(recipe(log_office_startup),),
    services_spa_index=Path(__file__).parent / "ui" / "index.html",
    routers=[bff_router],
    title="Documents",
    description="Документы Office через OnlyOffice Document Server",
    api_version="v1",
    documentation_gateway_prefix="documents",
)


@app.get("/documents/health")
async def documents_health():
    """Тот же JSON, что /health и /office/health; публичный префикс UI — /documents."""
    return build_health_payload(get_office_settings())


mount_service_spa(app, public_segment="documents", ui_dir=Path(__file__).parent / "ui")

if __name__ == "__main__":
    from core.app.server import serve

    serve("office", "apps.office.main:app", get_office_settings())
