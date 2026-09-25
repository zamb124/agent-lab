"""DI процесса voice: акустический шлюз STT/TTS/VAD."""

from typing import Annotated

from apps.voice.services.session_providers import VoiceSessionProviders
from core.di import http_di, task_di
from core.di.platform import PlatformDi


class VoiceDi(PlatformDi):
    session_providers: VoiceSessionProviders


Di = Annotated[VoiceDi, http_di(VoiceDi), task_di(VoiceDi)]
