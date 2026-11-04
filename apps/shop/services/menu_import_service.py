"""MenuImportService — агентный импорт меню: WorkItem агента и идемпотентный write-back.

Старт импорта, шаблона или обогащения создаёт ``WorkItem(kind=agent_job)`` на
сотрудника ``flow_employee_shop_menu_agent`` со связью ``ShopLink`` и режимом в
``variables.mode``. Агент читает вложения и пишет план обратно через
``apply_import`` / ``enrich_apply``. Повтор write-back с тем же ``work_item_id``
возвращает сохранённый ``variables.apply_result``; id блюд, меню, разделов и
позиций выводятся из ``work_item_id``, поэтому прерванный write-back доигрывается
без дублей.
"""

from __future__ import annotations

import asyncio
import hashlib

from apps.shop.events import publish_shop_catalog_changed
from apps.shop.models import (
    Shop,
    ShopMenu,
    ShopMenuImportMode,
    ShopMenuImportTarget,
    ShopMenuItem,
    ShopMenuSection,
    ShopMenuStatus,
    ShopProduct,
)
from apps.shop.models.import_api import (
    ShopMenuImportApplyPayload,
    ShopMenuImportApplyResult,
    ShopMenuImportItemPlan,
    ShopMenuImportStartPayload,
    ShopMenuImportTargetSpec,
    ShopMenuPhotoCrop,
    ShopMenuTemplateBuildPayload,
    ShopProductsEnrichApplyPayload,
    ShopProductsEnrichApplyResult,
    ShopProductsEnrichPayload,
)
from apps.shop.services.menu_photo_crop import MENU_PHOTO_CONTENT_TYPE, crop_menu_photo
from apps.shop.services.shop_service import ShopService
from apps.shop.services.storefront_service import StorefrontService
from apps.shop.tasks.task_names import SHOP_REBUILD_STOREFRONT
from core.authz.service import AuthzService
from core.context import require_context, reset_context, set_context
from core.errors.boundary import (
    PlatformAccessDeniedError,
    PlatformConflictError,
    PlatformNotFoundError,
)
from core.files.create_spec import FileCreateSpec, FilePostCreate, FileSourceKind, FileSourceRef
from core.files.file_ref import FileRef, stored_file_ref
from core.files.reader.service import read_stored_file_by_id
from core.files.registry import default_retention_for_source
from core.files.service import FilesService
from core.identity.flow_employee import ensure_flow_employee, flow_employee_user_id
from core.tasks import enqueue
from core.types import JsonValue
from core.utils.time import utcnow
from core.variables.models import VariableEntry, VariableMap
from core.worktracker.models import (
    TERMINAL_WORK_ITEM_STATES,
    ShopLink,
    UserActor,
    UsersAssignment,
    WorkItem,
    WorkItemKind,
    WorkItemResolution,
)
from core.worktracker.service import WorkItemService

SHOP_MENU_AGENT_FLOW_ID = "shop_menu_agent"
APPLY_RESULT_VARIABLE = "apply_result"

_IMPORT_MODES = frozenset({ShopMenuImportMode.IMPORT.value, ShopMenuImportMode.TEMPLATE.value})


def derived_id(prefix: str, seed: str) -> str:
    """Детерминированный id формы ``new_id``: повтор write-back попадает в те же строки."""
    return f"{prefix}_{hashlib.sha256(seed.encode()).hexdigest()[:24]}"


def _variable_text(item: WorkItem, key: str) -> str | None:
    entry = item.variables.get(key)
    if entry is None or entry.value is None:
        return None
    if not isinstance(entry.value, str):
        raise PlatformConflictError(
            f"WorkItem variable {key} must be a string", error_code="shop_menu_import_invalid"
        )
    return entry.value


def _variables(values: dict[str, JsonValue]) -> VariableMap:
    return {key: VariableEntry(value=value) for key, value in values.items() if value is not None}


class MenuImportService:
    """WorkItem агента меню и запись импорта в каталог и меню заведения."""

    def __init__(
        self,
        shop_service: ShopService,
        storefront_service: StorefrontService,
        work_item_service: WorkItemService,
        files_service: FilesService,
        authz_service: AuthzService,
    ) -> None:
        self._shops: ShopService = shop_service
        self._storefront: StorefrontService = storefront_service
        self._work_items: WorkItemService = work_item_service
        self._files: FilesService = files_service
        self._authz: AuthzService = authz_service

    # --- Старт работы агента ---

    async def start_import(
        self,
        company_id: str,
        user_id: str,
        namespace: str,
        payload: ShopMenuImportStartPayload,
    ) -> WorkItem:
        shop = await self._shops.get_shop(company_id, payload.shop_id)
        _ = await self.require_target_menu(shop, payload)
        attachments = [await self.company_file_ref(company_id, fid) for fid in payload.file_ids]
        return await self._create_agent_work_item(
            company_id,
            user_id,
            namespace,
            shop,
            title=f"Импорт меню: {shop.name}",
            description="Распознать меню из вложений и записать блюда через shop_menu_import_apply.",
            variables={
                "mode": ShopMenuImportMode.IMPORT.value,
                "shop_id": shop.shop_id,
                "target": payload.target,
                "shop_menu_id": payload.shop_menu_id,
                "menu_name": payload.menu_name,
            },
            attachments=attachments,
        )

    async def start_template(
        self,
        company_id: str,
        user_id: str,
        namespace: str,
        payload: ShopMenuTemplateBuildPayload,
    ) -> WorkItem:
        shop = await self._shops.get_shop(company_id, payload.shop_id)
        return await self._create_agent_work_item(
            company_id,
            user_id,
            namespace,
            shop,
            title=f"Меню из каталога: {payload.menu_name}",
            description=payload.brief,
            variables={
                "mode": ShopMenuImportMode.TEMPLATE.value,
                "shop_id": shop.shop_id,
                "target": ShopMenuImportTarget.NEW_MENU.value,
                "menu_name": payload.menu_name,
                "brief": payload.brief,
            },
            attachments=[],
        )

    async def start_enrich(
        self,
        company_id: str,
        user_id: str,
        namespace: str,
        payload: ShopProductsEnrichPayload,
    ) -> WorkItem:
        """Обогащение блюд; пустой ``shop_product_ids`` — все блюда без фото, КБЖУ или состава."""
        shop = await self._shops.get_shop(company_id, payload.shop_id)
        if payload.shop_product_ids:
            products = [
                await self._shops.get_product(company_id, shop.shop_id, pid)
                for pid in payload.shop_product_ids
            ]
        else:
            products = await ShopProduct.list_incomplete_by_shop_by_sort_asc(shop.shop_id)
        if not products:
            raise PlatformConflictError(
                "No dishes to enrich", error_code="shop_enrich_nothing"
            )
        product_ids: list[JsonValue] = [p.shop_product_id for p in products]
        return await self._create_agent_work_item(
            company_id,
            user_id,
            namespace,
            shop,
            title=f"Обогащение блюд: {shop.name}",
            description="Заполнить пустые поля блюд через shop_products_enrich_apply.",
            variables={
                "mode": ShopMenuImportMode.ENRICH.value,
                "shop_id": shop.shop_id,
                "shop_product_ids": product_ids,
            },
            attachments=[],
        )

    async def list_active_imports(self, company_id: str, shop_id: str) -> list[WorkItem]:
        shop = await self._shops.get_shop(company_id, shop_id)
        return await WorkItem.list_open_for_shop_by_created_at_desc(company_id, shop.shop_id)

    # --- Write-back агента ---

    async def apply_import(
        self, company_id: str, user_id: str, payload: ShopMenuImportApplyPayload
    ) -> ShopMenuImportApplyResult:
        item = await self._agent_work_item(company_id, user_id, payload.shop_id, payload.work_item_id)
        stored = item.variables.get(APPLY_RESULT_VARIABLE)
        if stored is not None:
            return ShopMenuImportApplyResult.model_validate(stored.value)
        if _variable_text(item, "mode") not in _IMPORT_MODES:
            raise PlatformConflictError(
                "WorkItem is not a menu import", error_code="shop_menu_import_mode_mismatch"
            )
        target = _variable_text(item, "target")
        if target is None:
            raise PlatformConflictError(
                "WorkItem has no import target", error_code="shop_menu_import_invalid"
            )
        shop = await self._shops.get_shop(company_id, payload.shop_id)
        spec = ShopMenuImportTargetSpec(
            shop_id=shop.shop_id,
            target=ShopMenuImportTarget(target),
            shop_menu_id=_variable_text(item, "shop_menu_id"),
            menu_name=_variable_text(item, "menu_name"),
        )
        menu = await self.ensure_target_menu(
            shop, spec, shop_menu_id=derived_id("shopmenu", item.work_item_id)
        )
        attachment_ids = {ref.file_id for ref in item.attachments if ref.file_id is not None}
        created: list[str] = []
        similar_count = 0
        token = set_context(require_context().model_copy(update={"active_namespace": item.namespace}))
        try:
            for section_index, section_plan in enumerate(payload.sections):
                seed = f"{item.work_item_id}:{section_index}"
                section = None
                if menu is not None:
                    section = await self.ensure_section(
                        menu, section_plan.name, shop_menu_section_id=derived_id("shopmsec", seed)
                    )
                for item_index, plan in enumerate(section_plan.items):
                    item_seed = f"{seed}:{item_index}"
                    product, is_new = await self._plan_product(
                        company_id, shop, plan, attachment_ids, derived_id("shopprod", item_seed)
                    )
                    if is_new:
                        created.append(product.shop_product_id)
                        if product.similar_shop_product_id is not None:
                            similar_count += 1
                    if menu is not None and section is not None:
                        _ = await self.ensure_menu_item(
                            menu,
                            section,
                            product,
                            shop_menu_item_id=derived_id("shopmitem", item_seed),
                        )
        finally:
            reset_context(token)
        result = ShopMenuImportApplyResult(
            work_item_id=item.work_item_id,
            shop_id=shop.shop_id,
            shop_menu_id=menu.shop_menu_id if menu is not None else None,
            shop_product_ids=created,
            similar_count=similar_count,
        )
        await self._finish_work_item(
            company_id,
            item,
            result.model_dump(mode="json"),
            f"Создано блюд: {len(created)}, похожих: {similar_count}.",
        )
        await self.publish_catalog_changed(shop)
        return result

    async def enrich_apply(
        self, company_id: str, user_id: str, payload: ShopProductsEnrichApplyPayload
    ) -> ShopProductsEnrichApplyResult:
        """Пишет только в пустые поля блюд; каждое изменённое блюдо получает ``ai_unverified``."""
        item = await self._agent_work_item(company_id, user_id, payload.shop_id, payload.work_item_id)
        stored = item.variables.get(APPLY_RESULT_VARIABLE)
        if stored is not None:
            return ShopProductsEnrichApplyResult.model_validate(stored.value)
        if _variable_text(item, "mode") != ShopMenuImportMode.ENRICH.value:
            raise PlatformConflictError(
                "WorkItem is not a dish enrichment", error_code="shop_menu_import_mode_mismatch"
            )
        updated: list[str] = []
        for update in payload.updates:
            product = await self._shops.get_product(
                company_id, payload.shop_id, update.shop_product_id
            )
            changed = False
            if update.description is not None and not product.description.strip():
                product.description = update.description
                changed = True
            if update.measure is not None and product.measure is None:
                product.measure = update.measure
                if update.measure_unit is not None:
                    product.measure_unit = update.measure_unit
                changed = True
            if update.ingredients is not None and not product.ingredients:
                product.ingredients = list(update.ingredients)
                changed = True
            if update.nutrition is not None and product.nutrition is None:
                product.nutrition = update.nutrition
                changed = True
            if update.allergens is not None and not product.allergens:
                product.allergens = list(update.allergens)
                changed = True
            if update.photo_file_id is not None and product.photo_file_id is None:
                _ = await self.company_file_ref(company_id, update.photo_file_id)
                product.photo_file_id = update.photo_file_id
                changed = True
            if changed:
                product.ai_unverified = True
                product.updated_at = utcnow()
                _ = await product.save()
                updated.append(product.shop_product_id)
        result = ShopProductsEnrichApplyResult(
            work_item_id=item.work_item_id,
            shop_id=payload.shop_id,
            shop_product_ids=updated,
        )
        await self._finish_work_item(
            company_id, item, result.model_dump(mode="json"), f"Обогащено блюд: {len(updated)}."
        )
        if updated:
            await self.publish_catalog_changed(await self._shops.get_shop(company_id, payload.shop_id))
        return result

    # --- Запись импорта: общая для агента и файла ---

    async def require_target_menu(
        self, shop: Shop, spec: ShopMenuImportTargetSpec
    ) -> ShopMenu | None:
        """Меню ``into_menu`` заведения в редактируемом статусе; иначе ``None``."""
        if spec.target != ShopMenuImportTarget.INTO_MENU:
            return None
        if spec.shop_menu_id is None:
            raise PlatformConflictError(
                "target into_menu requires shop_menu_id", error_code="shop_menu_import_invalid"
            )
        menu = await ShopMenu.get_by_id(spec.shop_menu_id)
        if menu is None or menu.shop_id != shop.shop_id:
            raise PlatformNotFoundError("Menu not found", error_code="menu_not_found")
        if menu.status == ShopMenuStatus.ARCHIVED:
            raise PlatformConflictError("Archived menu is read-only", error_code="menu_status_invalid")
        return menu

    async def ensure_target_menu(
        self, shop: Shop, spec: ShopMenuImportTargetSpec, *, shop_menu_id: str
    ) -> ShopMenu | None:
        """Меню результата: ``new_menu`` — черновик с ``shop_menu_id``, ``catalog`` — ``None``."""
        if spec.target != ShopMenuImportTarget.NEW_MENU:
            return await self.require_target_menu(shop, spec)
        existing = await ShopMenu.get_by_id(shop_menu_id)
        if existing is not None:
            return existing
        if spec.menu_name is None:
            raise PlatformConflictError(
                "target new_menu requires menu_name", error_code="shop_menu_import_invalid"
            )
        now = utcnow()
        return await ShopMenu.create(
            ShopMenu(
                shop_menu_id=shop_menu_id,
                shop_id=shop.shop_id,
                name=spec.menu_name,
                status=ShopMenuStatus.DRAFT,
                sort=await ShopMenu.next_sort_by_sort_desc(shop.shop_id),
                created_at=now,
                updated_at=now,
            )
        )

    async def ensure_section(
        self,
        menu: ShopMenu,
        name: str,
        *,
        shop_menu_section_id: str,
        parent_id: str | None = None,
    ) -> ShopMenuSection:
        """Раздел ``name`` под ``parent_id``: существующий по id или имени, иначе новый."""
        existing = await ShopMenuSection.get_by_id(shop_menu_section_id)
        if existing is not None:
            return existing
        siblings = await ShopMenuSection.list_children_by_parent_by_sort_asc(
            menu.shop_menu_id, parent_id
        )
        for sibling in siblings:
            if sibling.name == name:
                return sibling
        now = utcnow()
        return await ShopMenuSection.create(
            ShopMenuSection(
                shop_menu_section_id=shop_menu_section_id,
                shop_menu_id=menu.shop_menu_id,
                parent_id=parent_id,
                name=name,
                sort=await ShopMenuSection.next_sort_by_sort_desc(menu.shop_menu_id, parent_id),
                created_at=now,
                updated_at=now,
            )
        )

    async def ensure_menu_item(
        self,
        menu: ShopMenu,
        section: ShopMenuSection,
        product: ShopProduct,
        *,
        shop_menu_item_id: str,
    ) -> ShopMenuItem:
        """Позиция блюда в меню; блюдо, уже стоящее в меню, не дублируется."""
        existing = await ShopMenuItem.find_by_menu_and_product(
            menu.shop_menu_id, product.shop_product_id
        )
        if existing is not None:
            return existing
        return await ShopMenuItem.create(
            ShopMenuItem(
                shop_menu_item_id=shop_menu_item_id,
                shop_menu_id=menu.shop_menu_id,
                shop_menu_section_id=section.shop_menu_section_id,
                shop_product_id=product.shop_product_id,
                sort=await ShopMenuItem.next_sort_by_sort_desc(section.shop_menu_section_id),
            )
        )

    async def create_imported_product(self, product: ShopProduct) -> ShopProduct:
        """Импорт всегда создаёт новое блюдо; похожее имя ставит ``similar_shop_product_id``."""
        product.similar_shop_product_id = await self._shops.similar_shop_product_id(
            product.shop_id, product.name, exclude_shop_product_id=None
        )
        product.sort = await ShopProduct.next_sort_by_sort_desc(product.shop_id)
        return await ShopProduct.create(product)

    async def upload_product_photo(
        self, shop_id: str, shop_product_id: str, data: bytes
    ) -> str:
        """JPEG блюда в Документы ``Shop/{shop_id}``; публичный — витрина анонимна."""
        record = await self._files.create(
            FileCreateSpec(
                source_kind=FileSourceKind.SHOP_PRODUCT,
                source_ref=FileSourceRef(shop_id=shop_id, shop_product_id=shop_product_id),
                retention=default_retention_for_source(FileSourceKind.SHOP_PRODUCT),
                post_create=FilePostCreate(is_public=True),
            ),
            data,
            original_name=f"{shop_product_id}.jpg",
            content_type=MENU_PHOTO_CONTENT_TYPE,
        )
        return record.file_id

    async def publish_catalog_changed(self, shop: Shop) -> None:
        await self._storefront.invalidate_snapshot(shop.shop_id)
        await publish_shop_catalog_changed(shop.shop_id, shop.slug, shop.company_id)
        _ = await enqueue(SHOP_REBUILD_STOREFRONT, slug=shop.slug)

    # --- Внутреннее ---

    async def _create_agent_work_item(
        self,
        company_id: str,
        user_id: str,
        namespace: str,
        shop: Shop,
        *,
        title: str,
        description: str,
        variables: dict[str, JsonValue],
        attachments: list[FileRef],
    ) -> WorkItem:
        await self._ensure_menu_agent_employee(company_id, user_id)
        return await self._work_items.create_manual_task(
            company_id=company_id,
            title=title,
            description=description,
            created_by=UserActor(user_id=user_id),
            kind=WorkItemKind.AGENT_JOB,
            namespace=namespace,
            assignment=UsersAssignment(user_ids=[flow_employee_user_id(SHOP_MENU_AGENT_FLOW_ID)]),
            links=[ShopLink(shop_id=shop.shop_id)],
            variables=_variables(variables),
            attachments=attachments,
        )

    async def _ensure_menu_agent_employee(self, company_id: str, curator_user_id: str) -> None:
        """Идемпотентно создаёт ``flow_employee_shop_menu_agent`` в компании.

        Куратор — админ, стартовавший задачу. Бандл при company init / reload
        провижинит того же сотрудника с owner компании.
        """
        _ = await ensure_flow_employee(
            self._authz,
            flow_id=SHOP_MENU_AGENT_FLOW_ID,
            company_id=company_id,
            name="Shop Menu Agent",
            roles=["member"],
            curator_user_ids=[curator_user_id],
        )

    async def _agent_work_item(
        self, company_id: str, user_id: str, shop_id: str, work_item_id: str
    ) -> WorkItem:
        """WorkItem агента меню этого заведения; писать может исполнитель или админ компании."""
        item = await WorkItem.get(work_item_id)
        if item is None or item.company_id != company_id or not any(
            isinstance(link, ShopLink) and link.shop_id == shop_id for link in item.links
        ):
            raise PlatformNotFoundError(
                "Menu import WorkItem not found", error_code="shop_menu_import_not_found"
            )
        assignees = item.assignment.user_ids if isinstance(item.assignment, UsersAssignment) else []
        if user_id not in assignees and not await self._authz.check_company_admin(
            company_id=company_id, user_id=user_id
        ):
            raise PlatformAccessDeniedError(
                "Only the assignee writes back the import", error_code="shop_menu_import_forbidden"
            )
        if item.state in TERMINAL_WORK_ITEM_STATES and APPLY_RESULT_VARIABLE not in item.variables:
            raise PlatformConflictError(
                "Menu import WorkItem is closed", error_code="shop_menu_import_closed"
            )
        return item

    async def _plan_product(
        self,
        company_id: str,
        shop: Shop,
        plan: ShopMenuImportItemPlan,
        attachment_ids: set[str],
        shop_product_id: str,
    ) -> tuple[ShopProduct, bool]:
        """Блюдо позиции плана и признак «создано этим write-back»."""
        if plan.shop_product_id is not None:
            product = await self._shops.get_product(company_id, shop.shop_id, plan.shop_product_id)
            return product, False
        existing = await ShopProduct.get_by_id(shop_product_id)
        if existing is not None:
            return existing, True
        if plan.price_minor is None:
            raise PlatformConflictError(
                "new dish requires price_minor", error_code="shop_menu_import_invalid"
            )
        photo_file_id = None
        if plan.photo is not None:
            photo_file_id = await self._crop_photo(
                shop.shop_id, shop_product_id, plan.photo, attachment_ids
            )
        now = utcnow()
        product = await self.create_imported_product(
            ShopProduct(
                shop_product_id=shop_product_id,
                shop_id=shop.shop_id,
                name=plan.name,
                description=plan.description,
                measure=plan.measure,
                measure_unit=plan.measure_unit,
                ingredients=list(plan.ingredients),
                nutrition=plan.nutrition,
                allergens=list(plan.allergens),
                price_minor=plan.price_minor,
                photo_file_id=photo_file_id,
                ai_unverified=True,
                created_at=now,
                updated_at=now,
            )
        )
        return product, True

    async def _crop_photo(
        self,
        shop_id: str,
        shop_product_id: str,
        crop: ShopMenuPhotoCrop,
        attachment_ids: set[str],
    ) -> str:
        if crop.file_id not in attachment_ids:
            raise PlatformConflictError(
                "Crop source is not a WorkItem attachment",
                error_code="shop_menu_photo_source_invalid",
            )
        data, _ = await read_stored_file_by_id(crop.file_id)
        jpeg = await asyncio.to_thread(crop_menu_photo, data, crop)
        return await self.upload_product_photo(shop_id, shop_product_id, jpeg)

    async def company_file_ref(self, company_id: str, file_id: str) -> FileRef:
        record = await self._files.get_optional(file_id)
        if record is None or record.company_id != company_id:
            raise PlatformNotFoundError(f"File {file_id!r} not found.", error_code="file_not_found")
        return stored_file_ref(record)

    async def _finish_work_item(
        self,
        company_id: str,
        item: WorkItem,
        apply_result: JsonValue,
        resolution_text: str,
    ) -> None:
        variables = dict(item.variables)
        variables[APPLY_RESULT_VARIABLE] = VariableEntry(value=apply_result)
        _ = await self._work_items.update(
            company_id=company_id, work_item_id=item.work_item_id, variables=variables
        )
        _ = await self._work_items.complete(
            company_id=company_id,
            work_item_id=item.work_item_id,
            resolution=WorkItemResolution(text=resolution_text),
        )
