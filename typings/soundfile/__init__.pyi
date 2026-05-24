from collections.abc import Iterator
from typing import BinaryIO, Literal, Protocol

class FloatAudioArray(Protocol):
    ndim: int

    def mean(self, axis: Literal[1]) -> "FloatAudioArray": ...
    def __iter__(self) -> Iterator[float]: ...

def read(
    file: BinaryIO | bytes | bytearray | memoryview | str,
    frames: int = ...,
    start: int = ...,
    stop: int | None = ...,
    dtype: Literal["float32"] = ...,
    always_2d: bool = ...,
    fill_value: float | None = ...,
    out: None = ...,
    samplerate: int | None = ...,
    channels: int | None = ...,
    format: str | None = ...,
    subtype: str | None = ...,
    endian: str | None = ...,
    closefd: bool = ...,
) -> tuple[FloatAudioArray, int]: ...
