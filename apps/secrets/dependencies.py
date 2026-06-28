"""FastAPI dependencies для Secrets сервиса."""

from typing import Annotated

from fastapi import Depends

from apps.secrets.container import SecretsContainer, get_secrets_container


def get_container() -> SecretsContainer:
    return get_secrets_container()


ContainerDep = Annotated[SecretsContainer, Depends(get_container)]
