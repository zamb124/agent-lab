"""DI процесса secrets: версионируемые переменные и секреты компании."""

from typing import Annotated

from core.di import http_di, task_di
from core.di.platform import PlatformDi
from core.secrets.service import SecretsService


class SecretsDi(PlatformDi):
    secrets_service: SecretsService


Di = Annotated[SecretsDi, http_di(SecretsDi), task_di(SecretsDi)]
