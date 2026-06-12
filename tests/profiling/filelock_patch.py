from __future__ import annotations

import time
from types import TracebackType
from typing import Self

from filelock import FileLock as _OriginalFileLock

from tests.profiling.collector import get_collector

_patched = False


class ProfiledFileLock:
    def __init__(self, lock_file: str, timeout: float = -1) -> None:
        self._lock_file = lock_file
        self._timeout = timeout
        self._inner = _OriginalFileLock(lock_file, timeout=timeout)

    def acquire(
        self,
        timeout: float | None = None,
        poll_interval: float = 0.05,
    ) -> bool:
        started = time.monotonic()
        acquired = self._inner.acquire(timeout=timeout, poll_interval=poll_interval)
        get_collector().record_lock_wait(
            lock_path=self._lock_file,
            wait_sec=time.monotonic() - started,
            acquired=acquired,
            phase="acquire",
        )
        return acquired

    def release(self) -> None:
        self._inner.release()

    def __enter__(self) -> Self:
        started = time.monotonic()
        try:
            self._inner.__enter__()
        finally:
            get_collector().record_lock_wait(
                lock_path=self._lock_file,
                wait_sec=time.monotonic() - started,
                acquired=True,
                phase="enter",
            )
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self._inner.__exit__(exc_type, exc_val, exc_tb)


def install_filelock_patch() -> None:
    global _patched
    if _patched:
        return
    import filelock

    filelock.FileLock = ProfiledFileLock
    _patched = True

    import tests.fixtures.search_runet as search_runet_mod
    import tests.fixtures.workers as workers_mod

    workers_mod.FileLock = ProfiledFileLock
    search_runet_mod.FileLock = ProfiledFileLock
