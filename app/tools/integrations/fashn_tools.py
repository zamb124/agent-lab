"""
Инструменты для виртуальной примерки с FASHN API
"""

import json
import uuid
import httpx
import logging
from typing import Optional
from datetime import datetime, timezone
from app.core.tool_decorator import tool

from app.clients.fashn_client import get_fashn_client
from app.models import FileRecord
from app.core.container import get_container
from app.models.fashn_models import TryOnRecord, TryOnParameters
from app.core.core_clients.s3_client import get_default_s3_client
from app.core.context import get_context

logger = logging.getLogger(__name__)


@tool(group="Изображения")
async def virtual_try_on(
    model_image_file_id: str,
    product_image_file_id: str,
    model_height_cm: float,
    product_width_cm: float = 0,
    product_height_cm: float = 0,
    item_kind: str = "bag",
    placement: str = "left_shoulder",
    offset_x_pct: float = -6.0,
    offset_y_pct: float = 0.0,
    visible_top_pct: float = 0.04,
    visible_bottom_pct: float = 0.98,
    scale_bias: float = 1.0,
    variations: int = 0,
    product_url: Optional[str] = None,
) -> str:
    """
    Выполняет виртуальную примерку одежды или аксессуаров.

    Args:
        model_image_file_id: ID файла с фото модели
        product_image_file_id: ID файла с изображением продукта
        model_height_cm: Рост модели в сантиметрах
        product_width_cm: Ширина продукта в сантиметрах (для сумок, обязательно)
        product_height_cm: Высота продукта в сантиметрах (для сумок, опционально - если не указана, сохраняются пропорции)
        item_kind: Тип продукта ("bag" для сумок, "garment" для одежды)
        placement: Размещение для сумок ("left_shoulder", "right_shoulder", "left_hand", "right_hand", "center")
        offset_x_pct: Смещение по X в процентах (отрицательное - левее)
        offset_y_pct: Смещение по Y в процентах
        visible_top_pct: Верхний срез фигуры, доля высоты кадра (0..1)
        visible_bottom_pct: Нижний срез фигуры, доля высоты кадра (0..1)
        scale_bias: Финальный множитель размера продукта
        variations: Количество дополнительных вариаций модели (0-3)

    Returns:
        Информация о результатах виртуальной примерки (основной + вариации)
    """
    try:
        logger.info(
            f"Начинаем виртуальную примерку: модель={model_image_file_id}, продукт={product_image_file_id}"
        )

        # Получаем файлы из хранилища
        storage = get_container().storage

        model_data = await storage.get(model_image_file_id)
        if not model_data:
            return f"❌ Файл модели {model_image_file_id} не найден"

        product_data = await storage.get(product_image_file_id)
        if not product_data:
            return f"❌ Файл продукта {product_image_file_id} не найден"

        # Парсим FileRecord из JSON
        if isinstance(model_data, str):
            model_record = FileRecord(**json.loads(model_data))
        else:
            model_record = FileRecord(**model_data)

        if isinstance(product_data, str):
            product_record = FileRecord(**json.loads(product_data))
        else:
            product_record = FileRecord(**product_data)

        # Скачиваем файлы из S3
        s3_client = await get_default_s3_client()
        if not s3_client:
            return "❌ S3 клиент недоступен"

        model_bytes = await s3_client.download_bytes(model_record.s3_key)
        if model_bytes is None:
            return "❌ Не удалось скачать файл модели из S3"

        product_bytes = await s3_client.download_bytes(product_record.s3_key)
        if product_bytes is None:
            return "❌ Не удалось скачать файл продукта из S3"

        # Подготавливаем список моделей для примерки
        model_images_list = [model_bytes]  # Начинаем с оригинала

        fashn_client = get_fashn_client()

        # Если нужны вариации - создаем их сначала
        if variations > 0:
            # Загружаем исходную модель в S3 для создания вариаций
            model_url = await fashn_client._upload_image(
                model_bytes, "model_for_variations.png"
            )

            # Создаем вариации модели через FASHN model-variation API
            for i in range(variations):
                variation_strength = "subtle" if i % 2 == 0 else "strong"

                # Запускаем model-variation
                var_job_id = await fashn_client._fashn_run_model_variation(
                    model_image_url=model_url, variation_strength=variation_strength
                )

                # Получаем результат вариации
                var_fashn_url = await fashn_client._fashn_poll(var_job_id)

                # Скачиваем вариацию модели
                async with httpx.AsyncClient(timeout=180) as client:
                    var_response = await client.get(var_fashn_url)
                    var_response.raise_for_status()
                    var_model_bytes = var_response.content

                model_images_list.append(var_model_bytes)

        # Теперь делаем примерку на всех моделях (оригинал + вариации)
        all_results = []
        for i, model_img_bytes in enumerate(model_images_list):
            tryon_result = await fashn_client.try_on(
                model_image_bytes=model_img_bytes,
                product_image_bytes=product_bytes,
                model_height_cm=model_height_cm,
                product_width_cm=product_width_cm,
                product_height_cm=product_height_cm,
                item_kind=item_kind,
                placement=placement,
                offset_x_pct=offset_x_pct,
                offset_y_pct=offset_y_pct,
                visible_top_pct=visible_top_pct,
                visible_bottom_pct=visible_bottom_pct,
                scale_bias=scale_bias,
            )
            all_results.append(tryon_result)

        # Закрываем ресурсы
        await s3_client.close()
        await fashn_client.close()

        logger.info(
            f"Виртуальная примерка завершена, создано {len(all_results)} результатов"
        )

        # Сохраняем запись примерки в историю
        context = get_context()
        if not context or not context.user:
            raise ValueError("Нет контекста пользователя для сохранения примерки")
        
        user_id = context.user.user_id
        
        # Генерируем ID примерки
        try_on_uuid = uuid.uuid4().hex
        try_on_id = f"try_on:{user_id}:{try_on_uuid}"
        
        # Получаем прямые S3 URLs модели и товара из FileRecord
        model_url = model_record.direct_s3_url or model_record.url
        product_image_url = product_record.direct_s3_url or product_record.url
        
        # Собираем URLs результатов
        result_urls = []
        if variations == 0:
            result_urls = [all_results[0].output_url]
        else:
            result_urls = [result.output_url for result in all_results]
        
        # Создаем запись примерки
        try_on_record = TryOnRecord(
            id=try_on_id,
            user_id=user_id,
            created_at=datetime.now(timezone.utc).isoformat(),
            model_file_id=model_image_file_id,
            model_url=model_url,
            product_file_id=product_image_file_id,
            product_image_url=product_image_url,
            product_url=product_url,
            result_urls=result_urls,
            parameters=TryOnParameters(
                model_height_cm=model_height_cm,
                product_width_cm=product_width_cm,
                product_height_cm=product_height_cm,
                item_kind=item_kind,
                placement=placement,
                offset_x_pct=offset_x_pct,
                offset_y_pct=offset_y_pct,
                visible_top_pct=visible_top_pct,
                visible_bottom_pct=visible_bottom_pct,
                scale_bias=scale_bias,
                variations=variations
            )
        )
        
        # Сохраняем в Storage
        storage = get_container().storage
        await storage.set(try_on_id, json.dumps(try_on_record.model_dump()))
        
        logger.info(f"Примерка сохранена в историю: {try_on_id}")

        # Форматируем результат
        if variations == 0:
            # Одно изображение
            result = all_results[0]
            return f"""✅ Виртуальная примерка завершена успешно!

📊 Детали:
• Job ID: {result.job_id}
• Тип продукта: {item_kind}
• Рост модели: {model_height_cm} см

🔗 Результаты:
• Финальное изображение: {result.output_url}
• Изображение модели: {result.model_url}
• Изображение продукта: {result.product_scaled_url}"""
        else:
            # Множественные изображения
            results_text = "✅ Виртуальная примерка с вариациями завершена успешно!\n\n"
            results_text += f"📊 Создано {len(all_results)} изображений (основное + {variations} вариаций)\n\n"

            for i, res in enumerate(all_results):
                variant_name = "Основное" if i == 0 else f"Вариация {i}"
                results_text += f"🔗 {variant_name}:\n"
                results_text += f"• Job ID: {res.job_id}\n"
                results_text += f"• Финальное изображение: {res.output_url}\n"
                results_text += f"• Модель: {res.model_url}\n\n"

            results_text += f"• Продукт: {all_results[0].product_scaled_url}"
            return results_text

    except Exception as e:
        logger.error(f"Ошибка виртуальной примерки: {e}")

        # Возвращаем понятное сообщение об ошибке вместо raise
        if "ReadTimeout" in str(e) or "timeout" in str(e).lower():
            return "❌ Превышено время ожидания ответа от FASHN API. Попробуйте еще раз через несколько минут."
        elif "cannot identify image file" in str(e):
            return "❌ Не удалось обработать изображение товара. Проверьте ссылку на товар."
        elif "Content-Type" in str(e):
            return "❌ Ссылка не содержит изображение. Убедитесь, что ссылка корректна."
        elif "Файл модели" in str(e) or "Файл продукта" in str(e):
            return f"❌ Ошибка доступа к файлам: {str(e)}"
        else:
            return f"❌ Ошибка виртуальной примерки: {str(e)}"


@tool
async def upload_image_for_try_on(image_bytes: bytes, filename: str) -> str:
    """
    Загружает изображение для использования в виртуальной примерке.

    Args:
        image_bytes: Байты изображения
        filename: Имя файла

    Returns:
        ID загруженного файла для использования в virtual_try_on
    """
    try:
        # Генерируем уникальный ID
        file_id = f"fashn_{uuid.uuid4().hex}"

        # Сохраняем в хранилище
        storage = get_container().storage
        await storage.set(
            file_id,
            {
                "content": image_bytes,
                "filename": filename,
                "content_type": "image/*",
                "size": len(image_bytes),
            },
        )

        logger.info(f"Изображение {filename} загружено с ID: {file_id}")
        return f"✅ Изображение загружено успешно. ID файла: {file_id}"

    except Exception as e:
        logger.error(f"Ошибка загрузки изображения: {e}")
        return f"❌ Ошибка загрузки изображения: {str(e)}"


# Список доступных инструментов для экспорта
FASHN_TOOLS = [
    virtual_try_on,
    upload_image_for_try_on,
]
