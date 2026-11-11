"""CatalogService — сценарии единого каталога товаров.

Владелец мастер-карточки: базовые поля (имя/описание/галерея/SKU/ЕИ/
вес), наследуемые overlay'ы сервисов, ЕИ и упаковки, торговые
штрихкоды. Сервисы (stock/shop) вызывают его из своих op_* — право
и владение ``instance_id`` проверяет boundary сервиса, каталог
проверяет только доменные инварианты (uom существует, sku уникален,
код свободен).

Публикация доменных событий — отсюда же: ``catalog/product/*`` идут
на шину и разбудят durable-подписчиков (consumer group ``shop`` —
инвалидация снапшотов и агрегата).
"""

from __future__ import annotations

from decimal import Decimal

from oxyde.exceptions import UniqueViolationError

from core.catalog.contracts import (
    CatalogOverlay,
    CatalogPackagingView,
    CatalogProductDetail,
    CatalogScope,
    ResolvedProduct,
)
from core.catalog.events import (
    publish_catalog_overlay_changed,
    publish_catalog_product_created,
    publish_catalog_product_updated,
)
from core.catalog.models import (
    CatalogBarcode,
    CatalogProduct,
    CatalogProductOverride,
    CatalogUom,
)
from core.errors.boundary import PlatformConflictError, PlatformNotFoundError
from core.pagination import CursorPage
from core.utils.ids import new_id
from core.utils.time import utcnow


def _not_found(message: str, error_code: str) -> PlatformNotFoundError:
    return PlatformNotFoundError(message, error_code=error_code)


def _conflict(message: str, error_code: str) -> PlatformConflictError:
    return PlatformConflictError(message, error_code=error_code)


class CatalogService:
    """Сценарии каталога: карточка, overlay'ы, ЕИ/упаковки, штрихкоды."""

    # --- Карточка ---

    async def create_product(
        self,
        *,
        company_id: str,
        name: str,
        uom_id: str,
        description: str = "",
        image_file_ids: list[str] | None = None,
        sku: str | None = None,
        weight: Decimal | None = None,
        volume: Decimal | None = None,
        barcodes: list[str] | None = None,
        product_id: str | None = None,
    ) -> CatalogProduct:
        """Завести товар компании: карточка + торговые коды.

        ``sku`` уникален на компанию → ``sku_conflict``; ``uom_id``
        обязан существовать и дальше иммутабелен. ``product_id`` —
        только для детерминированных сидов (демо); обычный путь —
        ``new_id("prd")``. Коды привязываются к товару
        (``uom_id=None``); дубль кода → ``barcode_conflict``.
        """
        if await CatalogUom.by_id(company_id, uom_id) is None:
            raise _not_found("Unit of measure not found", "uom_not_found")
        now = utcnow()
        try:
            product = await CatalogProduct.create(
                CatalogProduct(
                    product_id=product_id or new_id("prd"),
                    company_id=company_id,
                    sku=sku,
                    name=name,
                    description=description,
                    image_file_ids=image_file_ids or [],
                    uom_id=uom_id,
                    weight=weight,
                    volume=volume,
                    is_archived=False,
                    created_at=now,
                    updated_at=now,
                )
            )
        except UniqueViolationError as exc:
            raise _conflict("SKU already exists", "sku_conflict") from exc
        for code in barcodes or []:
            _ = await self.bind_barcode(
                company_id=company_id, product_id=product.product_id, barcode=code
            )
        await publish_catalog_product_created(product)
        return product

    async def update_product(
        self,
        *,
        company_id: str,
        product_id: str,
        name: str | None = None,
        description: str | None = None,
        image_file_ids: list[str] | None = None,
        sku: str | None = None,
        weight: Decimal | None = None,
        volume: Decimal | None = None,
        barcodes: list[str] | None = None,
        is_archived: bool | None = None,
    ) -> CatalogProduct:
        """Правка базовых полей карточки (мастер-карта).

        ``uom_id`` намеренно не принимается — базовая ЕИ иммутабельна.
        ``sku`` смена подчинена унику компании. ``barcodes`` — PUT-форма
        набора кодов самого товара (коды упаковок не трогает).
        ``is_archived`` — «выключатель везде»: витрины убирают позицию
        из снапшота, склад отказывает новым документам.
        """
        product = await self.get_product(company_id=company_id, product_id=product_id)
        if name is not None:
            product.name = name
        if description is not None:
            product.description = description
        if image_file_ids is not None:
            product.image_file_ids = image_file_ids
        if sku is not None:
            product.sku = sku if sku != "" else None
        if weight is not None:
            product.weight = weight
        if volume is not None:
            product.volume = volume
        if is_archived is not None:
            product.is_archived = is_archived
        product.updated_at = utcnow()
        try:
            _ = await product.save()
        except UniqueViolationError as exc:
            raise _conflict("SKU already exists", "sku_conflict") from exc
        if barcodes is not None:
            _ = await self._set_product_barcodes(
                company_id=company_id,
                product_id=product_id,
                barcodes=barcodes,
            )
        await publish_catalog_product_updated(product)
        return product

    async def get_product(
        self, *, company_id: str, product_id: str
    ) -> CatalogProduct:
        product = await CatalogProduct.by_id(company_id, product_id)
        if product is None:
            raise _not_found("Product not found", "product_not_found")
        return product

    async def get_product_detail(
        self, *, company_id: str, product_id: str
    ) -> CatalogProductDetail:
        """Карточка мастера: база + все scope-override'ы + коды + упаковки."""
        product = await self.get_product(company_id=company_id, product_id=product_id)
        overlays = await CatalogProductOverride.list_by_product_by_facet_asc(company_id, product_id)
        codes = await CatalogBarcode.list_by_product_by_barcode_asc(company_id, product_id)
        packagings = await self.list_packagings(
            company_id=company_id, product_id=product_id
        )
        return CatalogProductDetail(
            product=product,
            overlays=overlays,
            barcodes=[c.barcode for c in codes],
            packagings=packagings,
        )

    async def list_products_page(
        self,
        *,
        company_id: str,
        query: str | None = None,
        include_archived: bool = False,
        limit: int = 50,
        cursor: str | None = None,
    ) -> CursorPage[CatalogProduct]:
        return await CatalogProduct.list_page_by_created_desc(
            company_id,
            query=query,
            include_archived=include_archived,
            limit=limit,
            cursor=cursor,
        )

    async def suggest_duplicates(
        self,
        *,
        company_id: str,
        name: str | None = None,
        sku: str | None = None,
        barcode: str | None = None,
        limit: int = 8,
    ) -> list[CatalogProduct]:
        """Кандидаты «такой товар уже есть»: точный sku/код + похожие имена.

        Вызывается UI до create («подключить или создать») и из импорта.
        Точное совпадение sku/кода ставится первым.
        """
        found: dict[str, CatalogProduct] = {}
        ordered: list[str] = []
        if sku:
            by_sku = await CatalogProduct.by_sku(company_id, sku.strip())
            if by_sku is not None:
                found[by_sku.product_id] = by_sku
                ordered.append(by_sku.product_id)
        if barcode:
            code = await CatalogBarcode.resolve(company_id, barcode.strip())
            if code is not None:
                product = await CatalogProduct.by_id(company_id, code.product_id)
                if product is not None and product.product_id not in found:
                    found[product.product_id] = product
                    ordered.append(product.product_id)
        if name:
            for product in await CatalogProduct.suggest_by_text_by_score_desc(
                company_id, name, limit=limit
            ):
                if product.product_id not in found:
                    found[product.product_id] = product
                    ordered.append(product.product_id)
        return [found[pid] for pid in ordered[:limit]]

    # --- Overlay'ы ---

    async def set_overlay(
        self,
        *,
        company_id: str,
        product_id: str,
        scope: CatalogScope,
        overlay: CatalogOverlay,
        resolve_scopes: list[CatalogScope],
    ) -> ResolvedProduct:
        """Записать форму override'ов scope и вернуть карточку в контексте.

        PUT-семантика: форма заменяет строку целиком; все-``None`` —
        наследование, строка удаляется. ``resolve_scopes`` — цепочка
        вызывающего сервиса (instance → сервис) для ответа.
        """
        product = await self.get_product(company_id=company_id, product_id=product_id)
        if overlay.is_empty:
            await CatalogProductOverride.delete_by_scope(
                company_id, product_id, scope.facet, scope.instance_id
            )
            saved: CatalogProductOverride | None = None
        else:
            saved = await CatalogProductOverride.by_scope(
                company_id, product_id, scope.facet, scope.instance_id
            )
            if saved is None:
                saved = await CatalogProductOverride.create(
                    CatalogProductOverride(
                        override_id=new_id("ovr"),
                        company_id=company_id,
                        product_id=product_id,
                        facet=scope.facet,
                        instance_id=scope.instance_id,
                        name=overlay.name,
                        description=overlay.description,
                        image_file_ids=overlay.image_file_ids,
                        created_at=utcnow(),
                        updated_at=utcnow(),
                    )
                )
            else:
                saved.name = overlay.name
                saved.description = overlay.description
                saved.image_file_ids = overlay.image_file_ids
                saved.updated_at = utcnow()
                _ = await saved.save()
        await publish_catalog_overlay_changed(
            product_id,
            company_id,
            facet=scope.facet,
            instance_id=scope.instance_id,
            overlay=overlay if not overlay.is_empty else None,
        )
        _ = saved
        return await self.resolve(
            company_id=company_id,
            product_id=product.product_id,
            scopes=resolve_scopes,
        )

    async def resolve(
        self,
        *,
        company_id: str,
        product_id: str,
        scopes: list[CatalogScope],
    ) -> ResolvedProduct:
        product = await self.get_product(company_id=company_id, product_id=product_id)
        rows = await CatalogProductOverride.list_for_scopes(
            company_id, [product_id], [s.key for s in scopes]
        )
        return ResolvedProduct.resolve(
            product, {(r.facet, r.instance_id): r for r in rows}, scopes
        )

    async def resolve_many(
        self,
        *,
        company_id: str,
        product_ids: list[str],
        scopes: list[CatalogScope],
    ) -> dict[str, ResolvedProduct]:
        """Батч-резолв: два запроса на любой размер страницы."""
        bases = await CatalogProduct.found_in_company_by_ids(company_id, product_ids)
        if not bases:
            return {}
        rows = await CatalogProductOverride.list_for_scopes(
            company_id, list(bases.keys()), [s.key for s in scopes]
        )
        by_product: dict[str, dict[tuple[str, str | None], CatalogProductOverride]] = {}
        for row in rows:
            by_product.setdefault(row.product_id, {})[(row.facet, row.instance_id)] = row
        return {
            pid: ResolvedProduct.resolve(
                base, by_product.get(pid, {}), scopes
            )
            for pid, base in bases.items()
        }

    # --- ЕИ и упаковки ---

    async def list_uoms(self, *, company_id: str) -> list[CatalogUom]:
        return await CatalogUom.list_by_category_and_name_asc(company_id)

    async def ensure_company_uoms(self, *, company_id: str) -> None:
        """Идемпотентный сид reference-ЕИ компании (Units/kg/g/m/l).

        Вызывается из ``*/company/init`` сервисов — до первого
        ``create_product`` базовая ЕИ обязана существовать.
        """
        for name, category, factor, is_reference in (
            ("Units", "unit", Decimal("1"), True),
            ("kg", "weight", Decimal("1"), True),
            ("g", "weight", Decimal("0.001"), False),
            ("m", "length", Decimal("1"), True),
            ("l", "volume", Decimal("1"), True),
        ):
            if await CatalogUom.exists_by_name(company_id, name):
                continue
            _ = await CatalogUom.create(
                CatalogUom(
                    uom_id=new_id("uom"),
                    company_id=company_id,
                    name=name,
                    category=category,
                    factor=factor,
                    is_reference=is_reference,
                )
            )

    async def list_packagings(
        self, *, company_id: str, product_id: str | None = None
    ) -> list[CatalogPackagingView]:
        """Фасовки компании/товара в терминах каталога (базовых ЕИ в упаковке)."""
        uoms = await CatalogUom.list_packagings_by_product_id_and_factor_asc(
            company_id, product_id
        )
        if not uoms:
            return []
        products = await CatalogProduct.found_in_company_by_ids(
            company_id, [u.product_id or "" for u in uoms]
        )
        bases = await CatalogUom.get_many(
            [p.uom_id for p in products.values()]
        )
        views: list[CatalogPackagingView] = []
        for uom in uoms:
            product = products.get(uom.product_id) if uom.product_id else None
            base = bases.get(product.uom_id) if product is not None else None
            if product is None or base is None:
                raise _conflict(
                    "Packaging references missing product or uom",
                    "packaging_orphan",
                )
            views.append(
                CatalogPackagingView(
                    packaging_id=uom.uom_id,
                    product_id=product.product_id,
                    name=uom.name,
                    quantity=uom.factor / base.factor,
                    weight=uom.weight,
                    volume=uom.volume,
                )
            )
        return views

    async def create_packaging(
        self,
        *,
        company_id: str,
        product_id: str,
        name: str,
        quantity: Decimal,
        barcode: str | None = None,
        weight: Decimal | None = None,
        volume: Decimal | None = None,
    ) -> CatalogPackagingView:
        """«Короб по 24»: AUoM-строка с ``factor = quantity × factor базовой ЕИ``."""
        product = await self.get_product(company_id=company_id, product_id=product_id)
        base = await CatalogUom.by_id(company_id, product.uom_id)
        if base is None:
            raise _not_found("Product base uom not found", "uom_not_found")
        try:
            uom = await CatalogUom.create(
                CatalogUom(
                    uom_id=new_id("uom"),
                    company_id=company_id,
                    name=name,
                    category=base.category,
                    factor=quantity * base.factor,
                    product_id=product_id,
                    weight=weight,
                    volume=volume,
                )
            )
        except UniqueViolationError as exc:
            raise _conflict(
                "Packaging name already exists", "packaging_conflict"
            ) from exc
        if barcode is not None:
            _ = await self.bind_barcode(
                company_id=company_id,
                product_id=product_id,
                barcode=barcode,
                uom_id=uom.uom_id,
            )
        await publish_catalog_product_updated(product)
        return CatalogPackagingView(
            packaging_id=uom.uom_id,
            product_id=product_id,
            name=name,
            quantity=quantity,
            weight=weight,
            volume=volume,
        )

    async def delete_packaging(
        self, *, company_id: str, packaging_id: str
    ) -> CatalogPackagingView:
        """Удалить фасовку (штрихкод упаковки перестаёт резолвиться)."""
        uom = await CatalogUom.by_id(company_id, packaging_id)
        if uom is None or uom.product_id is None:
            raise _not_found("Packaging not found", "packaging_not_found")
        product = await self.get_product(
            company_id=company_id, product_id=uom.product_id
        )
        base = await CatalogUom.by_id(company_id, product.uom_id)
        if base is None:
            raise _not_found("Product base uom not found", "uom_not_found")
        view = CatalogPackagingView(
            packaging_id=uom.uom_id,
            product_id=uom.product_id,
            name=uom.name,
            quantity=uom.factor / base.factor,
            weight=uom.weight,
            volume=uom.volume,
        )
        await CatalogBarcode.release_uom(company_id, packaging_id)
        await CatalogUom.delete_uom(company_id, packaging_id)
        await publish_catalog_product_updated(product)
        return view

    # --- Штрихкоды ---

    async def bind_barcode(
        self,
        *,
        company_id: str,
        product_id: str,
        barcode: str,
        uom_id: str | None = None,
    ) -> CatalogBarcode:
        """Привязать код к товару (``uom_id=None``) или упаковке."""
        _ = await self.get_product(company_id=company_id, product_id=product_id)
        return await CatalogBarcode.bind(
            company_id=company_id,
            barcode=barcode,
            product_id=product_id,
            uom_id=uom_id,
        )

    async def _set_product_barcodes(
        self, *, company_id: str, product_id: str, barcodes: list[str]
    ) -> bool:
        """PUT-замена набора кодов товара без события; True при изменении."""
        wanted = {code.strip() for code in barcodes if code.strip() != ""}
        existing = await CatalogBarcode.list_by_product_by_barcode_asc(
            company_id, product_id
        )
        current = {row.barcode for row in existing if row.uom_id is None}
        if wanted == current:
            return False
        for row in existing:
            if row.uom_id is None and row.barcode not in wanted:
                _ = await row.delete()
        for code in wanted:
            _ = await CatalogBarcode.bind(
                company_id=company_id, barcode=code, product_id=product_id
            )
        return True

    async def replace_product_barcodes(
        self, *, company_id: str, product_id: str, barcodes: list[str]
    ) -> None:
        """PUT-замена набора кодов самого товара (``uom_id IS NULL``).

        Коды упаковок не трогаются; лишние снимаются, новые встают
        через ``bind`` — дубль чужого кода → ``barcode_conflict``.
        """
        product = await self.get_product(company_id=company_id, product_id=product_id)
        changed = await self._set_product_barcodes(
            company_id=company_id, product_id=product_id, barcodes=barcodes
        )
        if changed:
            await publish_catalog_product_updated(product)

    async def list_product_barcodes(
        self, *, company_id: str, product_id: str
    ) -> list[CatalogBarcode]:
        return await CatalogBarcode.list_by_product_by_barcode_asc(company_id, product_id)

    async def resolve_code(
        self, *, company_id: str, barcode: str
    ) -> CatalogBarcode | None:
        return await CatalogBarcode.resolve(company_id, barcode.strip())
