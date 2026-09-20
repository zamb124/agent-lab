"""FastAPI dependencies для realtime bus."""

from typing import Annotated

from fastapi import Depends

from apps.realtime.container import RealtimeContainer, get_realtime_container


def get_container() -> RealtimeContainer:
    return get_realtime_container()


ContainerDep = Annotated[RealtimeContainer, Depends(get_container)]
