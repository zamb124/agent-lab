"""Каталог событий платформы для UI триггеров.

`GET /flows/api/v1/platform-events/catalog` — полный каталог типов событий
шины `platform:events` (регистрации всех сервисов из Redis, см.
`core/events/catalog.py`): тип, описание, JSON Schema payload и
`filter_fields` (leaf-пути для autocomplete фильтров). Используется
пикером события в редакторе триггера `platform_event`.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import Field

from apps.flows.src.dependencies import ContainerDep
from core.events import PlatformEventCatalogEntry, load_platform_event_catalog
from core.models import StrictBaseModel

router = APIRouter(tags=["platform-events"])


class PlatformEventCatalogResponse(StrictBaseModel):
    """Каталог типов событий платформы."""

    items: list[PlatformEventCatalogEntry] = Field(default_factory=list)


@router.get("/catalog")
async def platform_events_catalog(container: ContainerDep) -> PlatformEventCatalogResponse:
    """Полный каталог типов событий платформы (все сервисы)."""
    _ = container
    entries = await load_platform_event_catalog()
    return PlatformEventCatalogResponse(items=entries)
