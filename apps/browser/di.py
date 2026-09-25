"""DI процесса browser: Playwright и CDP."""

from collections.abc import AsyncIterator
from typing import Annotated

from apps.browser.config import BrowserSettings, settings_to_runtime_view
from apps.browser.services.runtime_facade import BrowserRuntimeFacade
from core.clients.redis_client import RedisClient
from core.di import http_di, recipe, task_di
from core.di.platform import PlatformDi
from core.files.service import FilesService


@recipe
async def browser_runtime(
    settings: BrowserSettings,
    redis_client: RedisClient,
    files_service: FilesService,
) -> AsyncIterator[BrowserRuntimeFacade]:
    facade = BrowserRuntimeFacade(
        settings_to_runtime_view(settings),
        redis_client=redis_client,
        files_service=files_service,
    )
    yield facade
    await facade.stop()


class BrowserDi(PlatformDi, recipes=(browser_runtime,)):
    browser_runtime: BrowserRuntimeFacade


Di = Annotated[BrowserDi, http_di(BrowserDi), task_di(BrowserDi)]
