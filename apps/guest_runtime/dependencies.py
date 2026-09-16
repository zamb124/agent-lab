"""FastAPI dependencies для guest_runtime."""

from typing import Annotated

from fastapi import Depends

from apps.guest_runtime.container import (
    GuestRuntimeContainer,
    get_guest_runtime_container,
)


def get_container() -> GuestRuntimeContainer:
    return get_guest_runtime_container()


ContainerDep = Annotated[GuestRuntimeContainer, Depends(get_container)]
