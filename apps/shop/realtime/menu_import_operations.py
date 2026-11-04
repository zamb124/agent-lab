"""Операции импорта меню: старт работы агента, write-back агента, файловый импорт.

Старт (импорт, шаблон, обогащение, файл) — админ компании в своём namespace.
Write-back зовёт сотрудник ``flow_employee_shop_menu_agent`` своей сессией через
``ShopClient``: scope — участник компании, право исполнителя WorkItem проверяет
``MenuImportService``.
"""

from __future__ import annotations

from apps.shop.di import Di
from apps.shop.models.import_api import (
    ShopMenuFileImportReport,
    ShopMenuFileImportRunPayload,
    ShopMenuImportApplyPayload,
    ShopMenuImportApplyResult,
    ShopMenuImportStartPayload,
    ShopMenuTemplateBuildPayload,
    ShopProductsEnrichApplyPayload,
    ShopProductsEnrichApplyResult,
    ShopProductsEnrichPayload,
)
from apps.shop.realtime.operations import ShopIdPayload
from core.models.identity_models import User
from core.pagination import ListResponse
from core.request_scope import require_company_admin, require_company_viewer, require_namespace
from core.worktracker.models import WorkItem


async def op_menu_imports_start(
    payload: ShopMenuImportStartPayload, *, user: User, di: Di
) -> WorkItem:
    _ = (user, await require_company_admin(di.authz_service))
    scope = await require_namespace(di.namespace_service)
    return await di.menu_import_service.start_import(
        scope.company_id, scope.user_id, scope.namespace, payload
    )


async def op_menu_imports_list(
    payload: ShopIdPayload, *, user: User, di: Di
) -> ListResponse[WorkItem]:
    _ = user
    scope = await require_company_viewer(di.authz_service)
    items = await di.menu_import_service.list_active_imports(scope.company_id, payload.shop_id)
    return ListResponse(items=items)


async def op_menu_imports_apply(
    payload: ShopMenuImportApplyPayload, *, user: User, di: Di
) -> ShopMenuImportApplyResult:
    _ = user
    scope = await require_company_viewer(di.authz_service)
    return await di.menu_import_service.apply_import(scope.company_id, scope.user_id, payload)


async def op_menu_templates_build(
    payload: ShopMenuTemplateBuildPayload, *, user: User, di: Di
) -> WorkItem:
    _ = (user, await require_company_admin(di.authz_service))
    scope = await require_namespace(di.namespace_service)
    return await di.menu_import_service.start_template(
        scope.company_id, scope.user_id, scope.namespace, payload
    )


async def op_products_enrich(
    payload: ShopProductsEnrichPayload, *, user: User, di: Di
) -> WorkItem:
    _ = (user, await require_company_admin(di.authz_service))
    scope = await require_namespace(di.namespace_service)
    return await di.menu_import_service.start_enrich(
        scope.company_id, scope.user_id, scope.namespace, payload
    )


async def op_products_enrich_apply(
    payload: ShopProductsEnrichApplyPayload, *, user: User, di: Di
) -> ShopProductsEnrichApplyResult:
    _ = user
    scope = await require_company_viewer(di.authz_service)
    return await di.menu_import_service.enrich_apply(scope.company_id, scope.user_id, payload)


async def op_menu_file_imports_run(
    payload: ShopMenuFileImportRunPayload, *, user: User, di: Di
) -> ShopMenuFileImportReport:
    _ = (user, await require_company_admin(di.authz_service))
    scope = await require_namespace(di.namespace_service)
    return await di.menu_file_import_service.run(
        scope.company_id, scope.user_id, scope.namespace, payload
    )
