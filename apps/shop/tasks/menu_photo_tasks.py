"""Скачивание фото блюд по URL файлового импорта меню (очередь ``shop``).

Задача исполняется от имени пользователя, запустившего импорт, в его namespace:
фото ложатся в Документы ``Shop/{shop_id}`` той же компании.
"""

from __future__ import annotations

from apps.shop.di import Di
from apps.shop.tasks.task_names import SHOP_MENU_PHOTO_DOWNLOAD
from core.context import reset_context, set_context
from core.context.job_context import build_job_context
from core.models.identity_models import Company, User
from core.tasks import platform_task
from core.types import JsonArray, JsonObject


@platform_task(SHOP_MENU_PHOTO_DOWNLOAD)
async def shop_menu_photo_download(
    company_id: str,
    user_id: str,
    namespace: str,
    shop_id: str,
    photo_urls: dict[str, str],
    *,
    di: Di,
) -> JsonObject:
    """Фото блюд ``shop_product_id → url``; блюда с уже заданным фото пропускаются."""
    company = await Company.get(company_id)
    if company is None:
        raise ValueError(f"shop_menu_photo_download: company {company_id} not found")
    user = await User.get(user_id)
    if user is None:
        raise ValueError(f"shop_menu_photo_download: user {user_id} not found")
    trace_id = f"shop:menu_photo:{shop_id}"
    token = set_context(
        build_job_context(
            company=company,
            user=user,
            host="shop_worker",
            trace_id=trace_id,
            session_id=trace_id,
            channel="shop",
        ).model_copy(update={"active_namespace": namespace})
    )
    try:
        updated = await di.menu_file_import_service.download_photos(
            company_id, shop_id, photo_urls
        )
    finally:
        reset_context(token)
    shop_product_ids: JsonArray = [pid for pid in updated]
    return JsonObject({"shop_id": shop_id, "shop_product_ids": shop_product_ids})
