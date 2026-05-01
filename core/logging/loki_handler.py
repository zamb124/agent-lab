"""
Асинхронный logging handler для отправки JSON-логов в Loki push API.

Используется в dev-режиме, когда сервисы запускаются на хосте (не в Docker),
и Alloy (discovery.docker) их не видит. Handler шлёт записи напрямую
в Loki endpoint (по умолчанию http://localhost:3100/loki/api/v1/push).

Дизайн:
- Собирает записи в in-memory очередь (collections.deque).
- Фоновый daemon-тред раз в _FLUSH_INTERVAL_SEC сливает batch в Loki
  через urllib (без внешних зависимостей).
- Если Loki недоступен — тихо логирует ошибку в stderr и дропает batch
  (dev-only, потеря логов приемлема).
"""

from __future__ import annotations

import atexit
import json
import logging
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from typing import Optional

_FLUSH_INTERVAL_SEC = 1.0
_MAX_QUEUE_SIZE = 10_000


class LokiHandler(logging.Handler):
    """
    Буферизующий handler: пишет JSON-логи в Loki push API.

    Args:
        loki_url: Полный URL Loki push endpoint
                  (e.g. ``http://localhost:3100/loki/api/v1/push``).
        service_name: Значение label ``service`` в Loki.
        flush_interval: Секунды между flush'ами.
    """

    def __init__(
        self,
        loki_url: str,
        service_name: str,
        flush_interval: float = _FLUSH_INTERVAL_SEC,
    ) -> None:
        super().__init__()
        self._loki_url = loki_url
        self._service_name = service_name
        self._flush_interval = flush_interval

        self._queue: deque[tuple[str, str]] = deque(maxlen=_MAX_QUEUE_SIZE)
        self._shutdown = threading.Event()

        self._thread = threading.Thread(
            target=self._flush_loop,
            name="loki-log-flusher",
            daemon=True,
        )
        self._thread.start()
        atexit.register(self._atexit_flush)

    # ── Handler API ─────────────────────────────────────────────────────

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            # Nanosecond timestamp для Loki
            ts_ns = str(int(record.created * 1e9))
            self._queue.append((ts_ns, msg))
        except Exception:
            self.handleError(record)

    # ── Background flush ────────────────────────────────────────────────

    def _flush_loop(self) -> None:
        while not self._shutdown.is_set():
            self._shutdown.wait(self._flush_interval)
            self._do_flush()

    def _do_flush(self) -> None:
        if not self._queue:
            return

        # Drain всё что есть
        raw: list[tuple[str, str]] = []
        while self._queue:
            try:
                raw.append(self._queue.popleft())
            except IndexError:
                break

        if not raw:
            return

        # Группируем по level — Loki требует одинаковые labels в пределах stream
        by_level: dict[str, list[tuple[str, str]]] = {}
        for ts_ns, line in raw:
            level = self._extract_level(line)
            by_level.setdefault(level, []).append((ts_ns, line))

        streams = []
        for level, values in by_level.items():
            streams.append({
                "stream": {
                    "service": self._service_name,
                    "level": level,
                    "source": "host",
                },
                "values": values,
            })

        payload = {"streams": streams}
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self._loki_url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                resp.read()
        except (urllib.error.URLError, OSError) as exc:
            # Loki недоступен — stderr, не рекурсия через logging
            print(
                f"[LokiHandler] push failed ({len(raw)} entries): {exc}",
                file=sys.stderr,
            )

    @staticmethod
    def _extract_level(log_line: str) -> str:
        try:
            obj = json.loads(log_line)
            return str(obj.get("level", obj.get("LEVEL", "INFO"))).upper()
        except (json.JSONDecodeError, AttributeError):
            return "INFO"

    def _atexit_flush(self) -> None:
        self._shutdown.set()
        self._do_flush()

    def close(self) -> None:
        self._shutdown.set()
        self._do_flush()
        super().close()
