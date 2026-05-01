"""
Буферизующий logging handler для отправки JSON-логов в Loki push API.

Используется в dev-режиме, когда сервисы запускаются на хосте (не в Docker),
и Alloy (discovery.docker) их не видит. Handler шлёт записи напрямую
в Loki endpoint (по умолчанию http://localhost:3100/loki/api/v1/push).

Дизайн:
- Собирает записи в in-memory очередь (collections.deque) под threading.Lock.
- Фоновый поток (не daemon) раз в _FLUSH_INTERVAL_SEC сливает batch в Loki
  через http.client (без внешних зависимостей).
- Batch ограничен по количеству записей и размеру; тело сжимается gzip.
- При shutdown ждёт завершения потока через join(timeout).
- Если Loki недоступен — тихо логирует ошибку в stderr и дропает batch
  (dev-only, потеря логов приемлема).
"""

from __future__ import annotations

import atexit
import gzip
import http.client
import json
import logging
import sys
import threading
from collections import deque
from urllib.parse import urlparse

_FLUSH_INTERVAL_SEC = 1.0
_MAX_QUEUE_SIZE = 10_000
_MAX_BATCH_ENTRIES = 1_000
_MAX_BATCH_BYTES = 4 * 1024 * 1024


_LOKI_HANDLERS: list[LokiHandler] = []


def _flush_all_on_exit() -> None:
    for handler in list(_LOKI_HANDLERS):
        try:
            handler.close()
        except Exception:
            pass


atexit.register(_flush_all_on_exit)


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
        self._service_name = service_name
        self._flush_interval = flush_interval

        parsed = urlparse(loki_url)
        self._loki_host = parsed.hostname or "localhost"
        self._loki_port = parsed.port or 3100
        self._loki_path = parsed.path or "/loki/api/v1/push"

        self._queue: deque[tuple[str, str, str]] = deque(maxlen=_MAX_QUEUE_SIZE)
        self._lock = threading.Lock()
        self._shutdown = threading.Event()

        self._thread = threading.Thread(
            target=self._flush_loop,
            name="loki-log-flusher",
        )
        self._thread.start()
        _LOKI_HANDLERS.append(self)

    # ── Handler API ─────────────────────────────────────────────────────

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            ts_ns = str(int(record.created * 1e9))
            level = record.levelname.upper()
            with self._lock:
                self._queue.append((ts_ns, level, msg))
        except Exception:
            self.handleError(record)

    # ── Background flush ────────────────────────────────────────────────

    def _flush_loop(self) -> None:
        while not self._shutdown.is_set():
            self._shutdown.wait(self._flush_interval)
            try:
                self._do_flush()
            except Exception:
                pass

    def _do_flush(self) -> None:
        raw: list[tuple[str, str, str]] = []
        with self._lock:
            while self._queue and len(raw) < _MAX_BATCH_ENTRIES:
                try:
                    raw.append(self._queue.popleft())
                except IndexError:
                    break

        if not raw:
            return

        by_level: dict[str, list[tuple[str, str]]] = {}
        for ts_ns, level, line in raw:
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
        body = json.dumps(payload).encode("utf-8")

        # Если batch превышает лимит размера — не шлём, чтобы не перегружать Loki
        if len(body) > _MAX_BATCH_BYTES:
            # Разбиваем на под-батчи по уровням
            self._flush_by_level(by_level)
            return

        self._send(body)

    def _flush_by_level(self, by_level: dict[str, list[tuple[str, str]]]) -> None:
        for level, values in by_level.items():
            # Отправляем каждый уровень отдельно
            streams = [{
                "stream": {
                    "service": self._service_name,
                    "level": level,
                    "source": "host",
                },
                "values": values,
            }]
            body = json.dumps({"streams": streams}).encode("utf-8")
            if len(body) > _MAX_BATCH_BYTES:
                # Если и один уровень тяжелый — урезаем
                half = len(values) // 2
                self._flush_by_level({level: values[:half]})
                self._flush_by_level({level: values[half:]})
                return
            self._send(body)

    def _send(self, body: bytes) -> None:
        compressed = gzip.compress(body)
        try:
            conn = http.client.HTTPConnection(
                self._loki_host, self._loki_port, timeout=5
            )
            conn.request(
                "POST",
                self._loki_path,
                body=compressed,
                headers={
                    "Content-Type": "application/json",
                    "Content-Encoding": "gzip",
                },
            )
            resp = conn.getresponse()
            resp.read()
            conn.close()
        except (OSError, http.client.HTTPException) as exc:
            print(
                f"[LokiHandler] push failed ({len(body)} bytes): {exc}",
                file=sys.stderr,
            )

    def close(self) -> None:
        self._shutdown.set()
        self._thread.join(timeout=5.0)
        try:
            _LOKI_HANDLERS.remove(self)
        except ValueError:
            pass
        super().close()
