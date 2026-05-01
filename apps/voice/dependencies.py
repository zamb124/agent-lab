"""FastAPI dependencies для voice сервиса."""

from typing import Annotated

from fastapi import Depends

from apps.voice.container import VoiceContainer, get_voice_container


def get_voice_container_dep() -> VoiceContainer:
    return get_voice_container()


ContainerDep = Annotated[VoiceContainer, Depends(get_voice_container_dep)]
