"""OrderEventsService — live-статусы заказа для покупателя по SSE.

Один ``PlatformEventTailReader`` на процесс (запускается лениво при первой
SSE-подписке) читает хвост ``platform:events`` и раздаёт события
``shop/order/*`` по очередям подписчиков, ключ — ``public_code``. Это не
второй bus: транспорт один — платформенный стрим, здесь только fanout.

Payload события заказа без PII (events.py) — стримить наружу безопасно.
Фолбэк на клиенте — текущий polling ``GET /public/orders/{code}``.
"""

from __future__ import annotations

import asyncio

from apps.shop.events import SHOP_ORDER_CREATED, SHOP_ORDER_STATUS_CHANGED
from core.clients.redis_client import RedisClient
from core.events.consumer import PlatformEventTailReader
from core.events.contract import PlatformEvent
from core.logging import get_logger
from core.types import JsonObject
from core.utils.background import run_with_log_context

logger = get_logger(__name__)

_ORDER_EVENT_TYPES = frozenset({SHOP_ORDER_CREATED, SHOP_ORDER_STATUS_CHANGED})
_QUEUE_MAXSIZE = 32


class OrderEventsService:
    """Реестр SSE-подписчиков на статусы заказов: public_code → очереди."""

    def __init__(self, redis: RedisClient) -> None:
        self._redis_url: str = redis.redis_url
        self._subscribers: dict[str, set[asyncio.Queue[JsonObject]]] = {}
        self._reader_task: asyncio.Task[None] | None = None

    def subscribe(self, public_code: str) -> asyncio.Queue[JsonObject]:
        """Новая очередь событий по коду заказа; reader поднимается лениво."""
        queue: asyncio.Queue[JsonObject] = asyncio.Queue(maxsize=_QUEUE_MAXSIZE)
        self._subscribers.setdefault(public_code, set()).add(queue)
        self._ensure_reader()
        return queue

    def unsubscribe(
        self, public_code: str, queue: asyncio.Queue[JsonObject]
    ) -> None:
        subscribers = self._subscribers.get(public_code)
        if subscribers is None:
            return
        subscribers.discard(queue)
        if not subscribers:
            del self._subscribers[public_code]

    async def _on_event(self, event: PlatformEvent) -> None:
        """Раздать доменное событие заказа очередям по ``public_code``."""
        if event.type not in _ORDER_EVENT_TYPES or not isinstance(event.payload, dict):
            return
        public_code = event.payload.get("public_code")
        if not isinstance(public_code, str):
            return
        queues = self._subscribers.get(public_code)
        if not queues:
            return
        message: JsonObject = {
            "type": event.type,
            "public_code": public_code,
            "status": event.payload.get("status"),
            "status_label": event.payload.get("status_label"),
            "total_minor": event.payload.get("total_minor"),
            "currency": event.payload.get("currency"),
        }
        for queue in queues:
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                # Медленный клиент не блокирует остальных: polling-пассаж
                # на клиенте доберёт статус сам.
                logger.warning(
                    "shop.order_events.queue_full", public_code=public_code
                )

    def _ensure_reader(self) -> None:
        if self._reader_task is not None and not self._reader_task.done():
            return
        reader = PlatformEventTailReader(self._redis_url, self._on_event)
        self._reader_task = run_with_log_context(
            reader.run(),
            name="shop-order-events-tail",
            background_kind="startup",
        )
