"""Куда класть файл: существующий каталог или путь от корня namespace."""

from __future__ import annotations

from typing import Literal

from core.models.base import StrictBaseModel

PlacementConflict = Literal["autorename", "fail", "replace"]


class DocumentPlacement(StrictBaseModel):
    """Путь от catalog_id (корень namespace, если catalog_id пуст) любой глубины."""

    catalog_id: str | None = None
    catalog_path: list[str] = []
    conflict: PlacementConflict = "autorename"


class DocumentEnsureRequest(StrictBaseModel):
    parent_catalog_id: str | None = None
    catalog_path: list[str]
    company_visible: bool = False


class DocumentEnsureResult(StrictBaseModel):
    catalog_id: str
    catalog_path: list[str]
