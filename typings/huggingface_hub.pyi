from pathlib import Path

class DeleteCacheStrategy:
    def execute(self) -> None: ...


class HFCacheInfo:
    def delete_revisions(self, *revisions: str) -> DeleteCacheStrategy: ...


def scan_cache_dir(cache_dir: str | Path | None = ...) -> HFCacheInfo: ...


def snapshot_download(
    repo_id: str,
    *,
    token: bool | str | None = ...,
    local_files_only: bool = ...,
) -> str: ...
