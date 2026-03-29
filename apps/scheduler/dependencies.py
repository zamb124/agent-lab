"""FastAPI dependencies для scheduler сервиса."""

from typing import Annotated

from fastapi import Depends

from apps.scheduler.container import SchedulerContainer, get_scheduler_container


def get_container() -> SchedulerContainer:
    return get_scheduler_container()


ContainerDep = Annotated[SchedulerContainer, Depends(get_container)]
