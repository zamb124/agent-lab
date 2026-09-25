"""
Secrets Service — защищённое версионируемое хранилище переменных компании.

Порт: 8022
БД: platform_secrets (service) + shared_db
"""

from apps.secrets.api import get_api_router
from apps.secrets.config import SecretsSettings
from apps.secrets.di import SecretsDi
from apps.secrets.realtime.command_router import SECRETS_OPERATIONS
from core.app import create_service_app
from core.config import get_settings

app = create_service_app(
    "secrets",
    SecretsSettings,
    SecretsDi,
    database="secrets_url",
    operations=SECRETS_OPERATIONS,
    routers=[get_api_router()],
    title="Secrets Service",
    description="Версионируемые переменные и секреты компании (scoped overrides, шифрование)",
    api_version="v1",
)


if __name__ == "__main__":
    from core.app.server import serve

    serve("secrets", "apps.secrets.main:app", get_settings())
