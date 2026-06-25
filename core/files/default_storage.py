"""Default process-wide FileStorage for core modules without container."""

from __future__ import annotations

from core.files.file_repository import FileRepository
from core.files.storage import FileStorage

_default_file_repository: FileRepository | None = None
_default_storage: FileStorage | None = None


def initialize_default_storage(file_repository: FileRepository) -> None:
    global _default_file_repository, _default_storage
    _default_file_repository = file_repository
    _default_storage = FileStorage(file_repository=file_repository)


def get_default_storage() -> FileStorage:
    if _default_storage is None:
        if _default_file_repository is None:
            raise RuntimeError(
                "File storage is not initialized. "
                + "Call initialize_default_storage(file_repository) at app startup."
            )
        raise RuntimeError("File storage is not initialized.")
    return _default_storage


async def close_default_storage() -> None:
    global _default_storage
    if _default_storage is not None:
        await _default_storage.close()
        _default_storage = None
