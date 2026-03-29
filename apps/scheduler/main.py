"""FastAPI entrypoint для scheduler control-plane."""

from fastapi import FastAPI

from apps.scheduler.api.v1 import api_v1_router
from apps.scheduler.config import SchedulerSettings, get_scheduler_settings
from apps.scheduler.container import get_scheduler_container
from core.app import create_service_app


async def on_startup(app: FastAPI, container, settings: SchedulerSettings) -> None:
    return None


async def on_shutdown(app: FastAPI, container) -> None:
    return None


app = create_service_app(
    service_name="scheduler",
    settings_class=SchedulerSettings,
    get_container=get_scheduler_container,
    routers=[api_v1_router],
    repository_names=[],
    on_startup=on_startup,
    on_shutdown=on_shutdown,
    cors_origins=["*"],
    title="Platform Scheduler",
    description="Единый cron/control-plane для всех сервисов",
    version="1.0.0",
    api_version="v1",
    include_crud_routers=False,
    mkdocs_gateway_prefix="scheduler",
)


if __name__ == "__main__":
    import uvicorn

    settings = get_scheduler_settings()
    uvicorn.run(
        "apps.scheduler.main:app",
        host=settings.server.host,
        port=settings.server.port,
        reload=settings.server.debug,
    )
