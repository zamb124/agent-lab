"""Операции инициализации компании и досева demo-витрин shop.

``op_shop_company_init`` вызывается idle-воркером ``company_init_new_company``
(аналог ``op_stock_company_init``): ставит тяжёлый сид в очередь ``shop``
и возвращает ``task_id``. ``op_demos_seed`` — та же задача по явной
команде админа для компаний, созданных до появления сида.
"""

from __future__ import annotations

from typing import Literal

from apps.shop.di import Di
from apps.shop.tasks.task_names import SHOP_SEED_DEMO_COMPANY
from core.models import StrictBaseModel
from core.models.identity_models import User
from core.request_scope import require_company, require_company_admin
from core.tasks import enqueue
from core.websocket import EmptyPayload, raise_forbidden


class ShopCompanyInitPayload(StrictBaseModel):
    company_id: str


class ShopScheduledResponse(StrictBaseModel):
    """Постановка фоновой задачи: демо-сид идёт в очереди ``shop``."""

    task_id: str
    status: Literal["scheduled"] = "scheduled"


async def _enqueue_demo_seed(company_id: str, user_id: str) -> ShopScheduledResponse:
    task = await enqueue(
        SHOP_SEED_DEMO_COMPANY,
        company_id=company_id,
        owner_user_id=user_id,
    )
    return ShopScheduledResponse(task_id=task.task_id)


async def op_shop_company_init(
    payload: ShopCompanyInitPayload, *, user: User, di: Di
) -> ShopScheduledResponse:
    """Поставить demo-сид витрин при инициализации компании.

    Рассинхрон ``company_id`` payload и активной компании из internal
    контекста — ``forbidden``: сид никогда не сеет в чужого tenant'а.
    """
    _ = user, di
    scope = require_company()
    if payload.company_id != scope.company_id:
        raise_forbidden(
            ValueError(
                f"company_id {payload.company_id!r} does not match active company {scope.company_id!r}"
            )
        )
    return await _enqueue_demo_seed(scope.company_id, scope.user_id)


async def op_demos_seed(
    payload: EmptyPayload, *, user: User, di: Di
) -> ShopScheduledResponse:
    """Досеять эталонные витрины в существующую компанию (админ).

    Идемпотентно: шаблоны, чьи строки уже есть или удалены владельцем,
    пропускаются — повторный запуск ничего не дублирует.
    """
    _ = payload, user
    scope = await require_company_admin(di.authz_service)
    return await _enqueue_demo_seed(scope.company_id, scope.user_id)
