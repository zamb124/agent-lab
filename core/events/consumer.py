"""
Consumer-примитивы единой шины событий платформы.

Два режима чтения Redis Stream ``platform:events``:

- ``PlatformEventTailReader`` — live-хвост без consumer group (XREAD).
  Используется WebSocket-форвардером в каждом HTTP-поде: каждый под видит
  каждое событие и доставляет его в свои сокеты. Semantics at-most-once,
  но с resume от последнего прочитанного id при обрыве соединения.

- ``PlatformEventGroupConsumer`` — durable at-least-once потребитель
  (XGROUP/XREADGROUP/XACK + периодический XAUTOCLAIM осиротевших записей).
  Каждый сервис-потребитель заводит собственную группу и перехватывает
  любые события платформы. Ошибка обработчика оставляет запись pending —
  повторная доставка через autoclaim. Некорректная запись (не парсится
  ``PlatformEvent``) логируется и ACK'ается — poison-записи не блокируют
  группу.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Protocol, TypeAlias

from pydantic import ValidationError
from redis.exceptions import ResponseError as RedisResponseError

from core.clients.redis_from_url import redis_client_from_url
from core.config import get_settings
from core.events.contract import PLATFORM_EVENTS_STREAM, PlatformEvent
from core.logging import get_logger

logger = get_logger(__name__)

PlatformEventHandler = Callable[[PlatformEvent], Awaitable[None]]

_StreamEntry: TypeAlias = tuple[str, dict[str, str]]
_StreamReadResult: TypeAlias = list[tuple[str, list[_StreamEntry]]]
_AutoClaimResult: TypeAlias = tuple[str, list[_StreamEntry], list[str]]


class _EventsRedis(Protocol):
    def xread(
        self,
        streams: dict[str, str],
        count: int,
        block: int,
    ) -> Awaitable[_StreamReadResult]: ...

    def xreadgroup(
        self,
        groupname: str,
        consumername: str,
        streams: dict[str, str],
        count: int,
        block: int,
    ) -> Awaitable[_StreamReadResult]: ...

    def xgroup_create(
        self,
        name: str,
        groupname: str,
        id: str,
        mkstream: bool,
    ) -> Awaitable[bool]: ...

    def xack(self, name: str, groupname: str, *ids: str) -> Awaitable[int]: ...

    def xautoclaim(
        self,
        name: str,
        groupname: str,
        consumername: str,
        min_idle_time: int,
        start_id: str,
        count: int,
    ) -> Awaitable[_AutoClaimResult]: ...

    def aclose(self) -> Awaitable[None]: ...


def _events_redis_client(redis_url: str) -> _EventsRedis:
    return redis_client_from_url(_EventsRedis, redis_url, decode_responses=True)


def _events_redis_url() -> str:
    settings = get_settings()
    redis_url = settings.database.redis_url
    if not redis_url:
        raise RuntimeError("database.redis_url is required to consume platform events")
    return redis_url


def _parse_entry(entry_id: str, fields: dict[str, str]) -> PlatformEvent | None:
    """Распарсить запись стрима; некорректная запись — None (лог у вызывающего)."""
    raw_event = fields.get("event")
    if raw_event is None:
        logger.error("platform_event.entry_missing_event_field", entry_id=entry_id)
        return None
    try:
        return PlatformEvent.model_validate_json(raw_event)
    except ValidationError as exc:
        logger.error(
            "platform_event.entry_invalid",
            entry_id=entry_id,
            error=str(exc),
        )
        return None


class PlatformEventTailReader:
    """Live-хвост шины для WS-форвардера: каждый вызов run() — свой клиент."""

    def __init__(self, redis_url: str, on_event: PlatformEventHandler) -> None:
        self._redis_url: str = redis_url
        self._on_event: PlatformEventHandler = on_event
        self._last_id: str = "$"

    async def run(self) -> None:
        """Читать хвост стрима до отмены задачи; переподключение с resume."""
        settings = get_settings()
        block_ms = settings.events.consumer_block_ms
        while True:
            client = _events_redis_client(self._redis_url)
            try:
                await self._read_loop(client, block_ms)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning(
                    "platform_event.tail_reader_reconnect",
                    error=str(exc),
                    **{"exception.type": type(exc).__name__},
                )
                await asyncio.sleep(1.0)
            finally:
                try:
                    await client.aclose()
                except Exception as close_exc:
                    logger.warning(
                        "platform_event.tail_reader_close_failed",
                        error=str(close_exc),
                    )

    async def _read_loop(self, client: _EventsRedis, block_ms: int) -> None:
        while True:
            read_result = await client.xread(
                {PLATFORM_EVENTS_STREAM: self._last_id},
                count=100,
                block=block_ms,
            )
            if not read_result:
                continue
            for _stream_name, entries in read_result:
                for entry_id, fields in entries:
                    self._last_id = entry_id
                    event = _parse_entry(entry_id, fields)
                    if event is None:
                        continue
                    try:
                        await self._on_event(event)
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:
                        logger.error(
                            "platform_event.tail_handler_failed",
                            entry_id=entry_id,
                            event_type=event.type,
                            error=str(exc),
                            exc_info=True,
                        )


class PlatformEventGroupConsumer:
    """Durable at-least-once потребитель шины (consumer group)."""

    def __init__(
        self,
        *,
        group: str,
        consumer_name: str,
        on_event: PlatformEventHandler,
        redis_url: str | None = None,
    ) -> None:
        if not group:
            raise ValueError("PlatformEventGroupConsumer: group is required")
        if not consumer_name:
            raise ValueError("PlatformEventGroupConsumer: consumer_name is required")
        self._group: str = group
        self._consumer_name: str = consumer_name
        self._on_event: PlatformEventHandler = on_event
        self._redis_url: str = redis_url if redis_url is not None else _events_redis_url()

    async def run(self) -> None:
        """Читать группу до отмены задачи; переподключение при ошибках Redis."""
        settings = get_settings()
        block_ms = settings.events.consumer_block_ms
        autoclaim_idle_ms = settings.events.autoclaim_idle_ms
        while True:
            client = _events_redis_client(self._redis_url)
            try:
                await self._ensure_group(client)
                await self._consume_loop(client, block_ms, autoclaim_idle_ms)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning(
                    "platform_event.group_consumer_reconnect",
                    group=self._group,
                    error=str(exc),
                    **{"exception.type": type(exc).__name__},
                )
                await asyncio.sleep(1.0)
            finally:
                try:
                    await client.aclose()
                except Exception as close_exc:
                    logger.warning(
                        "platform_event.group_consumer_close_failed",
                        group=self._group,
                        error=str(close_exc),
                    )

    async def _ensure_group(self, client: _EventsRedis) -> None:
        try:
            _ = await client.xgroup_create(
                PLATFORM_EVENTS_STREAM,
                self._group,
                id="$",
                mkstream=True,
            )
            logger.info("platform_event.group_created", group=self._group)
        except RedisResponseError as exc:
            if "BUSYGROUP" not in str(exc).upper():
                raise

    async def _consume_loop(
        self,
        client: _EventsRedis,
        block_ms: int,
        autoclaim_idle_ms: int,
    ) -> None:
        last_autoclaim_at = 0.0
        while True:
            now = time.monotonic()
            if (now - last_autoclaim_at) * 1000 >= autoclaim_idle_ms:
                last_autoclaim_at = now
                await self._autoclaim_stale(client, autoclaim_idle_ms)

            read_result = await client.xreadgroup(
                self._group,
                self._consumer_name,
                {PLATFORM_EVENTS_STREAM: ">"},
                count=100,
                block=block_ms,
            )
            if not read_result:
                continue
            for _stream_name, entries in read_result:
                await self._handle_entries(client, entries)

    async def _autoclaim_stale(self, client: _EventsRedis, autoclaim_idle_ms: int) -> None:
        """Забрать pending-записи мёртвых consumers этой группы."""
        try:
            claim_result = await client.xautoclaim(
                PLATFORM_EVENTS_STREAM,
                self._group,
                self._consumer_name,
                min_idle_time=autoclaim_idle_ms,
                start_id="0-0",
                count=100,
            )
        except RedisResponseError as exc:
            if "NOGROUP" in str(exc).upper():
                return
            raise
        claimed_entries = claim_result[1]
        if claimed_entries:
            logger.warning(
                "platform_event.stale_reclaimed",
                group=self._group,
                claimed=len(claimed_entries),
            )
            await self._handle_entries(client, claimed_entries)

    async def _handle_entries(self, client: _EventsRedis, entries: list[_StreamEntry]) -> None:
        for entry_id, fields in entries:
            event = _parse_entry(entry_id, fields)
            if event is None:
                _ = await client.xack(PLATFORM_EVENTS_STREAM, self._group, entry_id)
                continue
            try:
                await self._on_event(event)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error(
                    "platform_event.group_handler_failed",
                    group=self._group,
                    entry_id=entry_id,
                    event_type=event.type,
                    error=str(exc),
                    exc_info=True,
                )
                continue
            _ = await client.xack(PLATFORM_EVENTS_STREAM, self._group, entry_id)
