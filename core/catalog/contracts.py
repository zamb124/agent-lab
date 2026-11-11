"""Контракты каталога: scope наследования, overlay, resolved-форма.

``CatalogScope`` — контекст, в котором товар читается/переопределяется:
``facet`` — имя сервиса-владельца (``stock`` | ``shop``),
``instance_id`` — его экземпляр (``shop_id``) либо ``None`` — уровень
сервиса целиком. Цепочка наследования задаётся списком scope'ов от
конкретного к общему: ``[(shop, <id>), (shop, None)]``.

``CatalogOverlay`` — полная форма полевых override'ов одного scope:
``None`` = «наследовать»; форма со всеми ``None`` = вернуть наследование.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Self

from pydantic import Field

from core.catalog.models.override import CatalogProductOverride
from core.catalog.models.product import CatalogProduct
from core.models.base import StrictBaseModel

CONTENT_FIELDS: tuple[str, ...] = ("name", "description", "image_file_ids")
"""Наследуемые поля карточки — их покрывают overlay'ы и chain-toggle UI."""

BASE_SOURCE = "base"


class CatalogScope(StrictBaseModel):
    """Контекст наследования: сервис + опциональный экземпляр."""

    facet: str = Field(min_length=1, max_length=32)
    instance_id: str | None = None

    @property
    def source(self) -> str:
        """Метка источника значения для UI: ``shop`` либо ``shop:<id>``."""
        if self.instance_id is None:
            return self.facet
        return f"{self.facet}:{self.instance_id}"

    @property
    def key(self) -> tuple[str, str | None]:
        return (self.facet, self.instance_id)


class CatalogOverlay(StrictBaseModel):
    """Полная форма override'ов контента одного scope (PUT-семантика)."""

    name: str | None = Field(default=None, max_length=300)
    description: str | None = None
    image_file_ids: list[str] | None = None

    @property
    def is_empty(self) -> bool:
        """Все поля None — полное наследование, строка не нужна."""
        return (
            self.name is None
            and self.description is None
            and self.image_file_ids is None
        )


class ResolvedProduct(StrictBaseModel):
    """Эффективная карточка в контексте: база + победившие override'ы.

    ``sources[field]`` — источник значения: ``base`` либо ``scope.source``
    (``shop``, ``shop:<id>``, ``stock``) — по нему UI рисует цепочку
    наследования («Общее» / «Все витрины» / «Эта витрина»).
    """

    product: CatalogProduct
    name: str
    description: str
    image_file_ids: list[str]
    sources: dict[str, str]

    @classmethod
    def resolve(
        cls,
        product: CatalogProduct,
        overrides: dict[tuple[str, str | None], CatalogProductOverride],
        scopes: list[CatalogScope],
    ) -> Self:
        """Слияние базы и overlay'ов по цепочке ``scopes`` (первый — конкретнейший)."""
        name, description, image_file_ids = (
            product.name,
            product.description,
            product.image_file_ids,
        )
        sources = {field: BASE_SOURCE for field in CONTENT_FIELDS}
        for scope in scopes:
            row = overrides.get(scope.key)
            if row is None:
                continue
            if sources["name"] == BASE_SOURCE and row.name is not None:
                name = row.name
                sources["name"] = scope.source
            if sources["description"] == BASE_SOURCE and row.description is not None:
                description = row.description
                sources["description"] = scope.source
            if (
                sources["image_file_ids"] == BASE_SOURCE
                and row.image_file_ids is not None
            ):
                image_file_ids = row.image_file_ids
                sources["image_file_ids"] = scope.source
        return cls(
            product=product,
            name=name,
            description=description,
            image_file_ids=image_file_ids,
            sources=sources,
        )


class CatalogPackagingView(StrictBaseModel):
    """Упаковка товара в терминах каталога: ``quantity`` базовых ЕИ в одной."""

    packaging_id: str
    product_id: str
    name: str
    quantity: Decimal
    weight: Decimal | None
    volume: Decimal | None


class CatalogProductDetail(StrictBaseModel):
    """Полная картина мастер-карты: база + все overlay'ы + коды + упаковки."""

    product: CatalogProduct
    overlays: list[CatalogProductOverride]
    barcodes: list[str]
    packagings: list[CatalogPackagingView]
