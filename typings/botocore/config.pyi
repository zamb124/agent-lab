from collections.abc import Mapping

class Config:
    def __init__(
        self,
        *,
        signature_version: str | None = ...,
        proxies: Mapping[str, str] | None = ...,
    ) -> None: ...
