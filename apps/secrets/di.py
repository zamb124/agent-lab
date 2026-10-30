"""DI процесса secrets: версионируемые переменные и секреты компании."""

from typing import Annotated

from apps.secrets.secrets_service import SecretsService
from core.di import http_di, task_di
from core.di.platform import PlatformDi


class SecretsDi(PlatformDi):
    secrets_service: SecretsService


Di = Annotated[SecretsDi, http_di(SecretsDi), task_di(SecretsDi)]
