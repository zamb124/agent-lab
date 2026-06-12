from __future__ import annotations

import asyncio
import logging
import re

from tests.profiling.collector import _LOOP_WARN_MS, get_collector

_installed = False
_SLOW_RE = re.compile(r"took (?P<sec>[0-9]+(?:\.[0-9]+)?) seconds")


class _AsyncioSlowCallbackHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        if record.levelno < logging.WARNING:
            return
        message = record.getMessage()
        duration_ms: float | None = None
        match = _SLOW_RE.search(message)
        if match is None:
            return
        duration_ms = float(match.group("sec")) * 1000.0
        get_collector().record_slow_loop(message, duration_ms)


def install_loop_watchdog(loop: asyncio.AbstractEventLoop) -> None:
    global _installed
    if _installed:
        return
    loop.set_debug(True)
    loop.slow_callback_duration = _LOOP_WARN_MS / 1000.0

    asyncio_logger = logging.getLogger("asyncio")
    handler = _AsyncioSlowCallbackHandler()
    handler.setLevel(logging.WARNING)
    asyncio_logger.addHandler(handler)

    _installed = True


def try_install_on_running_loop() -> None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    install_loop_watchdog(loop)
