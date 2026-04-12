"""FastAPI dependencies для Flows сервиса."""

from typing import Annotated

from fastapi import Depends

from apps.flows.src.container import FlowContainer
from apps.flows.src.container import get_container as get_flows_container


def get_container() -> FlowContainer:
    return get_flows_container()


ContainerDep = Annotated[FlowContainer, Depends(get_container)]
