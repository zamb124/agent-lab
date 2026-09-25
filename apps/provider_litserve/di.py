"""DI процесса provider_litserve: локальные embedding, rerank, STT, TTS и VAD."""

from typing import Annotated

from apps.provider_litserve.litserve_runtime import (
    ProviderLitserveRuntime,
    provider_litserve_runtime,
)
from core.di import http_di, recipe, task_di
from core.di.platform import PlatformDi


@recipe
def litserve_runtime() -> ProviderLitserveRuntime:
    return provider_litserve_runtime


class ProviderLitserveDi(PlatformDi, recipes=(litserve_runtime,)):
    litserve_runtime: ProviderLitserveRuntime


Di = Annotated[ProviderLitserveDi, http_di(ProviderLitserveDi), task_di(ProviderLitserveDi)]
