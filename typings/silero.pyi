from typing import Protocol

import torch

class SileroTTSModel(Protocol):
    def apply_tts(self, *, text: str, speaker: str, sample_rate: int) -> torch.Tensor: ...


def silero_tts(
    language: str = ...,
    speaker: str = ...,
    *,
    device: str | None = ...,
) -> tuple[SileroTTSModel, str]: ...
