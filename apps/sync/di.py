"""DI процесса sync: чат, звонки и Git-ссылки."""

from typing import Annotated

from apps.sync.services.sync_channel_access_service import SyncChannelAccessService
from core.di import http_di, task_di
from core.di.platform import PlatformDi
from core.short_links.service import ShortLinkService


class SyncDi(PlatformDi):
    channel_access_service: SyncChannelAccessService
    short_link_service: ShortLinkService


Di = Annotated[SyncDi, http_di(SyncDi), task_di(SyncDi)]
