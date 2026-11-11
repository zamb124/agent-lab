"""Единый каталог: мастер-карточка, overlay-цепочка, штрихкоды.

Инварианты под тестом:

* карточка — один ``product_id`` на компанию, базовые поля правятся
  только ``update_product`` (мастер-карта), ``uom_id`` иммутабелен;
* overlay — PUT-форма scope: значение заменяет, ``None`` наследует,
  цепочка резолва ``instance → facet → base``; все-``None`` сносит
  строку (полное наследование);
* штрихкод — много кодов на товар, код уникален на компанию
  (``barcode_conflict``), PUT-замена набора не трогает коды упаковок;
* архив — «выключатель везде»: ``suggest`` и ``resolve`` архивный
  товар не выдают как активный (признак читается в карточке);
* дедуп — ``suggest_duplicates`` находит по sku/коду/имени для потока
  «подключить или создать».
"""

from decimal import Decimal

import pytest

from core.catalog.contracts import CatalogOverlay, CatalogScope
from core.catalog.models import CatalogUom
from core.errors.boundary import PlatformConflictError, PlatformNotFoundError

STOCK_SCOPES = [CatalogScope(facet="stock")]


def _shop_scopes(shop_id: str) -> list[CatalogScope]:
    return [
        CatalogScope(facet="shop", instance_id=shop_id),
        CatalogScope(facet="shop"),
    ]


async def _env(stock_di, unique_id: str) -> str:
    company_id = f"co-{unique_id}"
    await stock_di.catalog_service.ensure_company_uoms(company_id=company_id)
    return company_id


async def _uom(stock_di, company_id: str) -> str:
    uom = await CatalogUom.by_name(company_id, "Units")
    assert uom is not None
    return uom.uom_id


class TestProductCard:
    async def test_create_and_resolve_base(
        self, stock_di, unique_id: str
    ) -> None:
        company_id = await _env(stock_di, unique_id)
        uom_id = await _uom(stock_di, company_id)
        product = await stock_di.catalog_service.create_product(
            company_id=company_id,
            name=f"Espresso {unique_id}",
            sku=f"ESP-{unique_id}",
            uom_id=uom_id,
            description="250g pack",
            weight=Decimal("0.25"),
        )
        resolved = await stock_di.catalog_service.resolve(
            company_id=company_id, product_id=product.product_id, scopes=STOCK_SCOPES
        )
        assert resolved.name == product.name
        assert resolved.sources == {
            "name": "base",
            "description": "base",
            "image_file_ids": "base",
        }

    async def test_sku_conflict(self, stock_di, unique_id: str) -> None:
        company_id = await _env(stock_di, unique_id)
        uom_id = await _uom(stock_di, company_id)
        await stock_di.catalog_service.create_product(
            company_id=company_id, name=f"A {unique_id}", sku=f"DUP-{unique_id}", uom_id=uom_id
        )
        with pytest.raises(PlatformConflictError) as exc:
            await stock_di.catalog_service.create_product(
                company_id=company_id,
                name=f"B {unique_id}",
                sku=f"DUP-{unique_id}",
                uom_id=uom_id,
            )
        assert exc.value.error_code == "sku_conflict"

    async def test_create_with_unknown_uom_fails(
        self, stock_di, unique_id: str
    ) -> None:
        company_id = await _env(stock_di, unique_id)
        with pytest.raises(PlatformNotFoundError) as exc:
            await stock_di.catalog_service.create_product(
                company_id=company_id, name=f"X {unique_id}", uom_id="uom-missing"
            )
        assert exc.value.error_code == "uom_not_found"

    async def test_archive_marks_card(
        self, stock_di, unique_id: str
    ) -> None:
        company_id = await _env(stock_di, unique_id)
        uom_id = await _uom(stock_di, company_id)
        product = await stock_di.catalog_service.create_product(
            company_id=company_id, name=f"Old {unique_id}", uom_id=uom_id
        )
        updated = await stock_di.catalog_service.update_product(
            company_id=company_id, product_id=product.product_id, is_archived=True
        )
        assert updated.is_archived is True
        page = await stock_di.catalog_service.list_products_page(
            company_id=company_id, query=f"Old {unique_id}"
        )
        assert all(p.product_id != product.product_id for p in page.items)


class TestOverlayChain:
    async def test_instance_beats_facet_beats_base(
        self, stock_di, unique_id: str
    ) -> None:
        company_id = await _env(stock_di, unique_id)
        uom_id = await _uom(stock_di, company_id)
        product = await stock_di.catalog_service.create_product(
            company_id=company_id, name=f"Base {unique_id}", uom_id=uom_id
        )
        scopes = _shop_scopes("s1")
        resolved = await stock_di.catalog_service.set_overlay(
            company_id=company_id,
            product_id=product.product_id,
            scope=CatalogScope(facet="shop"),
            overlay=CatalogOverlay(name="Shop name"),
            resolve_scopes=scopes,
        )
        assert resolved.name == "Shop name"
        assert resolved.sources["name"] == "shop"
        resolved = await stock_di.catalog_service.set_overlay(
            company_id=company_id,
            product_id=product.product_id,
            scope=CatalogScope(facet="shop", instance_id="s1"),
            overlay=CatalogOverlay(name="S1 name"),
            resolve_scopes=scopes,
        )
        assert resolved.name == "S1 name"
        assert resolved.sources["name"] == "shop:s1"
        # Другой экземпляр видит сервисный уровень, не чужой.
        other = await stock_di.catalog_service.resolve(
            company_id=company_id,
            product_id=product.product_id,
            scopes=_shop_scopes("s2"),
        )
        assert other.name == "Shop name"

    async def test_empty_overlay_form_resets_to_base(
        self, stock_di, unique_id: str
    ) -> None:
        company_id = await _env(stock_di, unique_id)
        uom_id = await _uom(stock_di, company_id)
        product = await stock_di.catalog_service.create_product(
            company_id=company_id, name=f"Base {unique_id}", uom_id=uom_id
        )
        scope = CatalogScope(facet="shop", instance_id="s1")
        resolved = await stock_di.catalog_service.set_overlay(
            company_id=company_id,
            product_id=product.product_id,
            scope=scope,
            overlay=CatalogOverlay(name="Own"),
            resolve_scopes=_shop_scopes("s1"),
        )
        assert resolved.name == "Own"
        resolved = await stock_di.catalog_service.set_overlay(
            company_id=company_id,
            product_id=product.product_id,
            scope=scope,
            overlay=CatalogOverlay(),
            resolve_scopes=_shop_scopes("s1"),
        )
        assert resolved.name == product.name
        assert resolved.sources["name"] == "base"

    async def test_field_level_independence(
        self, stock_di, unique_id: str
    ) -> None:
        """Поле без override наследуется, пока соседнее переопределено."""
        company_id = await _env(stock_di, unique_id)
        uom_id = await _uom(stock_di, company_id)
        product = await stock_di.catalog_service.create_product(
            company_id=company_id,
            name=f"Base {unique_id}",
            uom_id=uom_id,
            description="base desc",
        )
        resolved = await stock_di.catalog_service.set_overlay(
            company_id=company_id,
            product_id=product.product_id,
            scope=CatalogScope(facet="shop", instance_id="s1"),
            overlay=CatalogOverlay(name="Own name"),
            resolve_scopes=_shop_scopes("s1"),
        )
        assert resolved.name == "Own name"
        assert resolved.description == "base desc"
        assert resolved.sources["description"] == "base"


class TestBarcodes:
    async def test_bind_many_resolve_each(
        self, stock_di, unique_id: str
    ) -> None:
        company_id = await _env(stock_di, unique_id)
        uom_id = await _uom(stock_di, company_id)
        product = await stock_di.catalog_service.create_product(
            company_id=company_id,
            name=f"Multi {unique_id}",
            uom_id=uom_id,
            barcodes=[f"B1-{unique_id}", f"B2-{unique_id}"],
        )
        detail = await stock_di.catalog_service.get_product_detail(
            company_id=company_id, product_id=product.product_id
        )
        assert detail.barcodes == [f"B1-{unique_id}", f"B2-{unique_id}"]
        for code in detail.barcodes:
            row = await stock_di.catalog_service.resolve_code(
                company_id=company_id, barcode=code
            )
            assert row is not None and row.product_id == product.product_id

    async def test_conflict_and_idempotent_rebind(
        self, stock_di, unique_id: str
    ) -> None:
        company_id = await _env(stock_di, unique_id)
        uom_id = await _uom(stock_di, company_id)
        first = await stock_di.catalog_service.create_product(
            company_id=company_id, name=f"F {unique_id}", uom_id=uom_id,
            barcodes=[f"SH-{unique_id}"],
        )
        # Тот же код на тот же товар — идемпотентно.
        rebound = await stock_di.catalog_service.bind_barcode(
            company_id=company_id, product_id=first.product_id, barcode=f"SH-{unique_id}"
        )
        assert rebound.product_id == first.product_id
        second = await stock_di.catalog_service.create_product(
            company_id=company_id, name=f"S {unique_id}", uom_id=uom_id
        )
        with pytest.raises(PlatformConflictError) as exc:
            _ = await stock_di.catalog_service.bind_barcode(
                company_id=company_id,
                product_id=second.product_id,
                barcode=f"SH-{unique_id}",
            )
        assert exc.value.error_code == "barcode_conflict"

    async def test_empty_barcode_rejected(
        self, stock_di, unique_id: str
    ) -> None:
        company_id = await _env(stock_di, unique_id)
        uom_id = await _uom(stock_di, company_id)
        product = await stock_di.catalog_service.create_product(
            company_id=company_id, name=f"E {unique_id}", uom_id=uom_id
        )
        with pytest.raises(PlatformConflictError) as exc:
            _ = await stock_di.catalog_service.bind_barcode(
                company_id=company_id, product_id=product.product_id, barcode="   "
            )
        assert exc.value.error_code == "barcode_empty"

    async def test_replace_keeps_packaging_codes(
        self, stock_di, unique_id: str
    ) -> None:
        company_id = await _env(stock_di, unique_id)
        uom_id = await _uom(stock_di, company_id)
        product = await stock_di.catalog_service.create_product(
            company_id=company_id, name=f"P {unique_id}", uom_id=uom_id,
            barcodes=[f"OLD-{unique_id}"],
        )
        pack = await stock_di.catalog_service.create_packaging(
            company_id=company_id,
            product_id=product.product_id,
            name="Box24",
            quantity=Decimal("24"),
            barcode=f"PKG-{unique_id}",
        )
        await stock_di.catalog_service.replace_product_barcodes(
            company_id=company_id,
            product_id=product.product_id,
            barcodes=[f"NEW-{unique_id}"],
        )
        codes = await stock_di.catalog_service.list_product_barcodes(
            company_id=company_id, product_id=product.product_id
        )
        by_code = {c.barcode: c for c in codes}
        assert f"NEW-{unique_id}" in by_code
        assert f"OLD-{unique_id}" not in by_code
        # Код упаковки живёт своей жизнью.
        pkg = by_code.get(f"PKG-{unique_id}")
        assert pkg is not None and pkg.uom_id == pack.packaging_id

    async def test_delete_packaging_releases_code(
        self, stock_di, unique_id: str
    ) -> None:
        company_id = await _env(stock_di, unique_id)
        uom_id = await _uom(stock_di, company_id)
        product = await stock_di.catalog_service.create_product(
            company_id=company_id, name=f"D {unique_id}", uom_id=uom_id
        )
        pack = await stock_di.catalog_service.create_packaging(
            company_id=company_id,
            product_id=product.product_id,
            name="Box6",
            quantity=Decimal("6"),
            barcode=f"REL-{unique_id}",
        )
        _ = await stock_di.catalog_service.delete_packaging(
            company_id=company_id, packaging_id=pack.packaging_id
        )
        row = await stock_di.catalog_service.resolve_code(
            company_id=company_id, barcode=f"REL-{unique_id}"
        )
        assert row is None


class TestSuggest:
    async def test_suggest_by_sku_barcode_name(
        self, stock_di, unique_id: str
    ) -> None:
        company_id = await _env(stock_di, unique_id)
        uom_id = await _uom(stock_di, company_id)
        product = await stock_di.catalog_service.create_product(
            company_id=company_id,
            name=f"Caramel Syrup {unique_id}",
            sku=f"SYR-{unique_id}",
            uom_id=uom_id,
            barcodes=[f"GTIN-{unique_id}"],
        )
        by_sku = await stock_di.catalog_service.suggest_duplicates(
            company_id=company_id, sku=f"SYR-{unique_id}"
        )
        assert by_sku[0].product_id == product.product_id
        by_code = await stock_di.catalog_service.suggest_duplicates(
            company_id=company_id, barcode=f"GTIN-{unique_id}"
        )
        assert by_code[0].product_id == product.product_id
        by_name = await stock_di.catalog_service.suggest_duplicates(
            company_id=company_id, name=f"Caramel Syrup {unique_id}"
        )
        assert any(p.product_id == product.product_id for p in by_name)
