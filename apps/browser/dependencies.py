"""
FastAPI Depends для сервиса browser.
"""

from typing import Annotated

from fastapi import Depends

from apps.browser.container import BrowserContainer, get_browser_container


def get_container() -> BrowserContainer:
    return get_browser_container()


ContainerDep = Annotated[BrowserContainer, Depends(get_container)]
