from typing import Protocol, TypedDict

import torch

class SileroVADModel(Protocol):
    def reset_states(self) -> None: ...


class SpeechTimestamp(TypedDict):
    start: int
    end: int


def load_silero_vad() -> SileroVADModel: ...


def get_speech_timestamps(
    audio: torch.Tensor,
    model: SileroVADModel,
    *,
    threshold: float = ...,
    sampling_rate: int = ...,
) -> list[SpeechTimestamp]: ...
