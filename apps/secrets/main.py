"""
Secrets Service — защищённое версионируемое хранилище переменных компании.

Порт: 8022
БД: platform_secrets (service) + shared_db
"""

from fastapi import FastAPI

from apps.secrets.api import get_api_router
from apps.secrets.config import SecretsSettings
from apps.secrets.container import SecretsContainer, get_secrets_container
from core.app import create_service_app
from core.config import get_settings
from core.logging import get_logger

logger = get_logger(__name__)


async def on_startup(
    app: FastAPI, container: SecretsContainer, settings: SecretsSettings
) -> None:
    _ = app, container, settings
    logger.info("Secrets Service: запущен")


app = create_service_app(
    service_name="secrets",
    settings_class=SecretsSettings,
    get_container=get_secrets_container,
    routers=[
        get_api_router(),
    ],
    on_startup=on_startup,
    title="Secrets Service",
    description="Версионируемые переменные и секреты компании (scoped overrides, шифрование)",
    api_version="v1",
    include_crud_routers=False,
)


if __name__ == "__main__":
    from core.app.server import serve

    serve("secrets", "apps.secrets.main:app", get_settings())
