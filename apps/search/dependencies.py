"""FastAPI dependencies for search service."""

from typing import Annotated

from fastapi import Depends

from apps.search.container import SearchContainer, get_search_container


def get_container() -> SearchContainer:
    return get_search_container()


ContainerDep = Annotated[SearchContainer, Depends(get_container)]
