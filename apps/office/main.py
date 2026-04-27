"""
Документы OnlyOffice — BFF и Lit UI (процесс office, публичный путь /documents).
"""

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from apps.office.api.bff import router as bff_router
from apps.office.config import OfficeSettings
from apps.office.container import get_office_container
from apps.office.dependencies import ContainerDep
from core.app import create_service_app
from core.app.health_payload import build_health_payload
from apps.office.config import get_office_settings

logger = logging.getLogger(__name__)


def _api_routers():
    return [bff_router]


app = create_service_app(
    service_name="office",
    settings_class=OfficeSettings,
    get_container=get_office_container,
    services_spa_index=Path(__file__).parent / "ui" / "index.html",
    routers=_api_routers(),
    title="Documents",
    description="Документы Office через OnlyOffice Document Server",
    api_version="v1",
    include_crud_routers=False,
    documentation_gateway_prefix="documents",
)

core_frontend_path = Path(__file__).parent.parent.parent / "core" / "frontend" / "static"
if core_frontend_path.exists():
    app.mount("/static/core", StaticFiles(directory=str(core_frontend_path)), name="core_frontend")
    logger.info("Core frontend: %s", core_frontend_path)

office_ui_path = Path(__file__).parent / "ui"
if office_ui_path.exists():
    app.mount(
        "/documents/ui/static",
        StaticFiles(directory=str(office_ui_path), html=True),
        name="office_ui",
    )
    logger.info("Documents UI: %s", office_ui_path)


@app.get("/documents/health")
async def documents_health(container: ContainerDep):
    """Тот же JSON, что /health и /office/health; публичный префикс UI — /documents."""
    _ = container
    return build_health_payload(get_office_settings())


@app.get("/documents")
@app.get("/documents/")
@app.get("/documents/{path:path}")
async def serve_documents_ui(container: ContainerDep, path: str = "") -> FileResponse:
    _ = container
    if (
        path.startswith("api/")
        or path.startswith("ui/static/")
        or path.startswith("ws")
        or path.startswith("assets/")
    ):
        raise HTTPException(status_code=404, detail="Not found")
    index_file = Path(__file__).parent / "ui" / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=404, detail="Documents UI not found")
    return FileResponse(index_file)


if __name__ == "__main__":
    import uvicorn

    settings = get_office_settings()
    uvicorn.run(
        "apps.office.main:app",
        host=settings.server.host,
        port=settings.server.port,
        reload=settings.server.debug,
    )
