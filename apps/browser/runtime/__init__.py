"""
Browser Runtime: пул CDP, контексты, аренда страниц, состояние сессии, interactor.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.browser.runtime.facade import BrowserRuntimeFacade
    from apps.browser.runtime.interactor import PlaywrightBrowserInteractor

__all__ = [
    "BrowserRuntimeFacade",
    "PlaywrightBrowserInteractor",
]


def __getattr__(name: str):
    if name == "BrowserRuntimeFacade":
        from apps.browser.runtime.facade import BrowserRuntimeFacade

        return BrowserRuntimeFacade
    if name == "PlaywrightBrowserInteractor":
        from apps.browser.runtime.interactor import PlaywrightBrowserInteractor

        return PlaywrightBrowserInteractor
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
