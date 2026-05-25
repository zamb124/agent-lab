from types import TracebackType
from typing import Literal, Required, TypedDict

class FFmpegExtractAudioPostProcessor(TypedDict):
    key: Literal["FFmpegExtractAudio"]
    preferredcodec: Literal["mp3"]
    preferredquality: str


class YoutubeDLOptions(TypedDict, total=False):
    format: str
    outtmpl: str
    postprocessors: list[FFmpegExtractAudioPostProcessor]
    quiet: bool
    no_warnings: bool
    noplaylist: bool
    socket_timeout: int | float


class YoutubeDLInfo(TypedDict):
    title: Required[str]


class YoutubeDL:
    def __init__(self, params: YoutubeDLOptions | None = None) -> None: ...
    def __enter__(self) -> "YoutubeDL": ...
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...
    def extract_info(self, url: str, download: bool = False) -> YoutubeDLInfo: ...
