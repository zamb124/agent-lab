"""FastAPI dependencies для Sync сервиса."""

from typing import Annotated

from fastapi import Depends

from apps.sync.container import SyncContainer, get_sync_container


def get_container() -> SyncContainer:
    return get_sync_container()


ContainerDep = Annotated[SyncContainer, Depends(get_container)]
