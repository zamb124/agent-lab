"""DI процесса sync: чат, звонки и Git-ссылки."""

from typing import Annotated

from apps.sync.services.call_link_service import SyncCallLinkService
from apps.sync.services.call_service import SyncCallService
from apps.sync.services.channel_service import SyncChannelService
from apps.sync.services.git_service import SyncGitService
from apps.sync.services.message_service import SyncMessageService
from apps.sync.services.recording_service import SyncCallRecordingService
from apps.sync.services.sync_channel_access_service import SyncChannelAccessService
from apps.sync.services.thread_service import SyncThreadService
from core.di import http_di, task_di
from core.di.platform import PlatformDi


class SyncDi(PlatformDi):
    channel_access_service: SyncChannelAccessService
    call_recording_service: SyncCallRecordingService
    call_link_service: SyncCallLinkService
    call_service: SyncCallService
    channel_service: SyncChannelService
    git_service: SyncGitService
    message_service: SyncMessageService
    thread_service: SyncThreadService


Di = Annotated[SyncDi, http_di(SyncDi), task_di(SyncDi)]
