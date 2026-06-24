"""FastAPI dependencies для Worktracker сервиса."""

from typing import Annotated

from fastapi import Depends

from apps.worktracker.container import WorktrackerContainer, get_worktracker_container


def get_container() -> WorktrackerContainer:
    return get_worktracker_container()


ContainerDep = Annotated[WorktrackerContainer, Depends(get_container)]
