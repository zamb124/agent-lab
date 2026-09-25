"""Default process-wide FileStorage for core modules outside a process DI."""

from __future__ import annotations

from core.files.storage import FileStorage

_default_storage: FileStorage | None = None


def initialize_default_storage() -> None:
    global _default_storage
    _default_storage = FileStorage()


def get_default_storage() -> FileStorage:
    if _default_storage is None:
        raise RuntimeError(
            "File storage is not initialized. "
            + "Call initialize_default_storage() at app startup."
        )
    return _default_storage


async def close_default_storage() -> None:
    global _default_storage
    if _default_storage is not None:
        await _default_storage.close()
        _default_storage = None
