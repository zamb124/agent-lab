"""FastAPI dependencies для Wiki сервиса."""

from typing import Annotated

from fastapi import Depends

from apps.wiki.container import WikiContainer, get_wiki_container


def get_container() -> WikiContainer:
    return get_wiki_container()


ContainerDep = Annotated[WikiContainer, Depends(get_container)]
