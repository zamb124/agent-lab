"""Shop TaskIQ tasks — demo-сид эталонных витрин (очередь ``shop``).

``shop_seed_demo_company`` ставится ``op_shop_company_init`` из idle
``company_init_new_company`` (внутренний контекст компании) и командой
досева ``shop/demos/seed``. Тяжёлое — заливка ~70 фото в S3 и создание
каталога — поэтому в воркере, а не в HTTP.
"""

from __future__ import annotations

from apps.shop.di import Di
from apps.shop.tasks.task_names import SHOP_SEED_DEMO_COMPANY
from core.context import clear_context, set_context
from core.context.job_context import build_job_context, pick_company_billing_user
from core.logging import get_logger
from core.models.identity_models import Company
from core.tasks import platform_task
from core.types import JsonObject

logger = get_logger(__name__)


@platform_task(SHOP_SEED_DEMO_COMPANY)
async def shop_seed_demo_company(
    company_id: str,
    owner_user_id: str = "",
    *,
    di: Di,
) -> JsonObject:
    """Развернуть эталонные витрины ``DEMO_TEMPLATES`` в компании.

    Идемпотентно по детерминированным PK — retry и повторная команда
    досева безопасны. Контекст — платёжный пользователь компании
    (``pick_company_billing_user``): файлы и записи принадлежат tenant'у.
    """
    if not di.settings.demo_seed_enabled:
        return JsonObject({"seeded": 0, "reason": "disabled"})
    company = await Company.get(company_id)
    if company is None:
        raise ValueError(f"shop_seed_demo_company: company {company_id} not found")
    billing_user = await pick_company_billing_user(company=company)
    trace_id = f"shop:seed:{company_id}"
    _ = set_context(
        build_job_context(
            company=company,
            user=billing_user,
            host="shop-job.local",
            trace_id=trace_id,
            session_id=trace_id,
            channel="shop",
        )
    )
    try:
        stats = await di.seed_service.seed_company(
            company=company,
            owner_user_id=owner_user_id or billing_user.user_id,
        )
        return JsonObject(stats)
    finally:
        clear_context()
