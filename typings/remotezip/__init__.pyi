"""Typed surface used by GAR HTTP Range archive reading."""

from __future__ import annotations

from zipfile import ZipFile

from requests import Session

class RemoteFetcher:
    def __init__(self, session: Session | None = None) -> None: ...

class RemoteZip(ZipFile):
    def __init__(
        self,
        url: str,
        initial_buffer_size: int = 65536,
        session: Session | None = None,
        fetcher: type[RemoteFetcher] | None = None,
        support_suffix_range: bool = True,
        timeout: float | None = None,
    ) -> None: ...
