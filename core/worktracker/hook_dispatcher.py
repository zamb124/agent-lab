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
from core.internal_context_headers import build_internal_context_headers
from core.logging import get_logger
from core.types import JsonObject
from core.worktracker.models import (
    AgentActor,
    UserActor,
    WorkItem,
    WorkItemHook,
)

logger = get_logger(__name__)

_PLATFORM_SYSTEM_HOOK_USER_ID = "platform-worktracker-system"


def hook_dispatch_internal_user_id(work_item: WorkItem) -> str:
    """user_id для signed internal context при service-to-service вызове хука."""
    created_by = work_item.created_by
    if isinstance(created_by, UserActor):
        return created_by.user_id
    if isinstance(created_by, AgentActor):
        return f"platform-agent:{created_by.flow_id}"
    return _PLATFORM_SYSTEM_HOOK_USER_ID


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
        internal_headers = build_internal_context_headers(
            company_id=work_item.company_id,
            user_id=hook_dispatch_internal_user_id(work_item),
        )
        _ = await self._service_client.post(
            hook.service,
            hook.path,
            json=payload,
            headers=internal_headers,
        )


__all__ = [
    "WorkItemHookDispatcher",
    "NoopHookDispatcher",
    "ServiceClientHookDispatcher",
    "hook_dispatch_internal_user_id",
]
