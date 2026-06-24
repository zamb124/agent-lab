"""
Контракт диспатчера хуков жизненного цикла WorkItem.

Ядро (`WorkItemService`) нейтрально и не делает кросс-сервисных вызовов напрямую.
На событиях (`assigned`/`comment`/`completed`) оно вызывает инъектированный
`WorkItemHookDispatcher`; конкретная реализация (apps/worktracker, flows) дёргает
`{hook.service, hook.path}` через `ServiceClient`. Так соблюдается запрет
`core -> apps`, а срабатывание хуков единообразно независимо от вызывающего.
"""

from __future__ import annotations

from typing import Protocol

from core.clients.service_client import ServiceClient
from core.logging import get_logger
from core.types import JsonObject
from core.worktracker.models import WorkItem, WorkItemHook

logger = get_logger(__name__)


class WorkItemHookDispatcher(Protocol):
    async def dispatch(self, work_item: WorkItem, hook: WorkItemHook, payload: JsonObject) -> None:
        ...  # pragma: no cover


class NoopHookDispatcher:
    """Дефолтная реализация: хуки не дёргаются (pure-сценарии без апп-слоя)."""

    async def dispatch(self, work_item: WorkItem, hook: WorkItemHook, payload: JsonObject) -> None:
        _ = (work_item, hook, payload)


class ServiceClientHookDispatcher:
    """Дёргает `{hook.service, hook.path}` через платформенный ServiceClient.

    `binding` внутри payload — непрозрачные данные потребителя (например
    flows-сессия для возобновления durable workflow).
    """

    def __init__(self, service_client: ServiceClient) -> None:
        self._service_client: ServiceClient = service_client

    async def dispatch(self, work_item: WorkItem, hook: WorkItemHook, payload: JsonObject) -> None:
        logger.info(
            "worktracker.hook.dispatch",
            work_item_id=work_item.work_item_id,
            hook_event=hook.event.value,
            service=hook.service,
            path=hook.path,
        )
        _ = await self._service_client.post(hook.service, hook.path, json=payload)


__all__ = ["WorkItemHookDispatcher", "NoopHookDispatcher", "ServiceClientHookDispatcher"]
