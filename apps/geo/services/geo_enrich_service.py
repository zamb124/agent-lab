"""Дрейнер очереди фонового обогащения (``geo_enrich_queue``).

``GEO_ENRICH_TICK`` (каждые 5 минут) захватывает пачку pending-задач и
исполняет по ``kind``: handler-функции регистрируются импортёрами
источников через ``register_handler``. Rate-limited источники (НСПД и др.)
складывают сюда догон; задача с ``run_after`` ждёт backoff. Незнакомый
``kind`` — ``failed`` сразу: повторы его не починят.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from apps.geo.config import GeoSettings
from apps.geo.models.geo_enrich_item import GeoEnrichItem

EnrichHandler = Callable[[GeoEnrichItem], Awaitable[None]]


class GeoEnrichDeferred(Exception):
    """Handler просит парковку: задача ждёт своего резолвера, не попытка."""

    def __init__(self, defer_seconds: float) -> None:
        super().__init__(f"deferred for {defer_seconds}s")
        self.defer_seconds: float = defer_seconds


class GeoEnrichService:
    """Исполнение задач обогащения по kind-реестру."""

    def __init__(self, settings: GeoSettings) -> None:
        self._settings: GeoSettings = settings
        self._handlers: dict[str, EnrichHandler] = {}

    def register_handler(self, *, kind: str, handler: EnrichHandler) -> None:
        """Привязка kind к исполнителю; конфликт — ошибка конфигурации."""
        if kind in self._handlers:
            raise ValueError(f"enrich handler {kind!r} already registered")
        self._handlers[kind] = handler

    async def drain(self) -> dict[str, int]:
        """Пачка из очереди: claim → dispatch → done/defer/retry/failed."""
        items = await GeoEnrichItem.claim_pending(
            limit=self._settings.enrich_tick_batch
        )
        done = 0
        failed = 0
        deferred = 0
        for item in items:
            handler = self._handlers.get(item.kind)
            if handler is None:
                await GeoEnrichItem.finish_failed(
                    item,
                    error=f"unknown enrich kind {item.kind!r}",
                    retry_after=None,
                    max_attempts=self._settings.enrich_max_attempts,
                )
                failed += 1
                continue
            try:
                await handler(item)
            except GeoEnrichDeferred as defer_exc:
                await GeoEnrichItem.defer(
                    item,
                    run_after=(
                        datetime.now(UTC)
                        + timedelta(seconds=defer_exc.defer_seconds)
                    ),
                )
                deferred += 1
                continue
            except Exception as exc:
                await GeoEnrichItem.finish_failed(
                    item,
                    error=f"{type(exc).__name__}: {exc}"[:2000],
                    retry_after=(
                        datetime.now(UTC)
                        + timedelta(
                            seconds=self._settings.enrich_retry_pause_seconds
                            * item.attempts
                        )
                    ),
                    max_attempts=self._settings.enrich_max_attempts,
                )
                failed += 1
                continue
            await GeoEnrichItem.finish_done(item)
            done += 1
        return {
            "claimed": len(items),
            "done": done,
            "deferred": deferred,
            "failed": failed,
        }
