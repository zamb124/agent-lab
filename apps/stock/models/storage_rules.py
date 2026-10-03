"""Чистые правила размещения и ресурсной совместимости (без IO).

Вызываются из `StockMove.post_step` (коммит) и из подсказок
(`PlacementService`) — контракт один: код ошибки `platform:errors`
или `None`.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol, runtime_checkable

from apps.stock.models.enums import (
    StockContainerPolicy,
    StockProductMixing,
)


@dataclass(frozen=True)
class BinContent:
    """Снимок содержимого ячейки для проверок смешивания и ёмкости."""

    product_ids: frozenset[str]
    lot_ids: frozenset[str]
    container_type_ids: frozenset[str]
    container_count: int
    has_loose: bool
    total_weight: Decimal
    total_volume: Decimal


@dataclass(frozen=True)
class PlacementItem:
    """Размещаемая единица: строка количества или контейнер целиком."""

    product_ids: frozenset[str]
    lot_ids: frozenset[str]
    container_type_id: str | None
    """Тип контейнера, который ставится в ячейку; `None` — россыпь."""
    total_weight: Decimal | None
    total_volume: Decimal | None


@runtime_checkable
class StorageTypeLike(Protocol):
    """Минимальный контракт типа хранения для правил (model или тестовый double)."""

    @property
    def container_policy(self) -> StockContainerPolicy: ...
    @property
    def allowed_container_type_ids(self) -> list[str]: ...
    @property
    def max_containers(self) -> int | None: ...
    @property
    def product_mixing(self) -> StockProductMixing: ...
    @property
    def allow_mixed_lots(self) -> bool: ...
    @property
    def max_weight(self) -> Decimal | None: ...
    @property
    def max_volume(self) -> Decimal | None: ...


def check_placement(
    *,
    storage_type: StorageTypeLike,
    placing: PlacementItem,
    existing: BinContent,
) -> str | None:
    """Код `error_code` нарушения либо `None` — размещение допустимо."""
    if placing.container_type_id is not None:
        if storage_type.container_policy == StockContainerPolicy.LOOSE_ONLY:
            return "storage_loose_only"
        if (
            storage_type.allowed_container_type_ids
            and placing.container_type_id
            not in storage_type.allowed_container_type_ids
        ):
            return "storage_container_type_denied"
    elif storage_type.container_policy == StockContainerPolicy.CONTAINER_ONLY:
        return "storage_container_required"

    if storage_type.max_containers is not None:
        incoming = 1 if placing.container_type_id is not None else 0
        if existing.container_count + incoming > storage_type.max_containers:
            return "storage_max_containers"

    if storage_type.product_mixing == StockProductMixing.EMPTY_ONLY:
        if existing.product_ids or existing.container_count or existing.has_loose:
            return "storage_not_empty"
    elif storage_type.product_mixing == StockProductMixing.SAME_PRODUCT:
        union = existing.product_ids | placing.product_ids
        if len(union) > 1:
            return "storage_product_mixed"

    if not storage_type.allow_mixed_lots:
        if len(existing.lot_ids | placing.lot_ids) > 1:
            return "storage_lot_mixed"

    if storage_type.max_weight is not None and placing.total_weight is not None:
        if existing.total_weight + placing.total_weight > storage_type.max_weight:
            return "storage_capacity_exceeded"
    if storage_type.max_volume is not None and placing.total_volume is not None:
        if existing.total_volume + placing.total_volume > storage_type.max_volume:
            return "storage_capacity_exceeded"
    return None


@runtime_checkable
class ResourceTypeLike(Protocol):
    """Минимальный контракт типа ресурса для `resource_allows`."""

    @property
    def allowed_container_type_ids(self) -> list[str]: ...
    @property
    def handles_loose(self) -> bool: ...
    @property
    def max_level(self) -> int | None: ...
    @property
    def max_load_weight(self) -> Decimal | None: ...
    @property
    def storage_type_ids(self) -> list[str]: ...


def resource_allows(
    *,
    resource_type: ResourceTypeLike,
    container_type_id: str | None,
    loose: bool,
    src_level: int | None,
    dst_level: int | None,
    src_storage_type_id: str | None,
    dst_storage_type_id: str | None,
    load_weight: Decimal | None,
) -> str | None:
    """Код `error_code` либо `None` — ресурс может исполнить задание."""
    if (
        resource_type.max_level is not None
        and max(src_level or 1, dst_level or 1) > resource_type.max_level
    ):
        return "resource_level_exceeded"
    if loose and not resource_type.handles_loose:
        return "resource_loose_denied"
    if (
        container_type_id is not None
        and resource_type.allowed_container_type_ids
        and container_type_id not in resource_type.allowed_container_type_ids
    ):
        return "resource_container_denied"
    if (
        resource_type.max_load_weight is not None
        and load_weight is not None
        and load_weight > resource_type.max_load_weight
    ):
        return "resource_overweight"
    if resource_type.storage_type_ids:
        for side in (src_storage_type_id, dst_storage_type_id):
            if (
                side is not None
                and side not in resource_type.storage_type_ids
            ):
                return "resource_zone_denied"
    return None
