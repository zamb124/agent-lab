"""
API эндпоинты для FASHN виртуальной примерки.
"""

import io
import re
import logging
import httpx
import json
from typing import Optional, List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from PIL import Image

from ...core.file_processor import FileProcessor, get_default_file_processor
from ...tools.fashn_tools import virtual_try_on
from ...core.context import get_context
from ...core.storage import Storage
from ...core.context import get_context
from ...core.storage import Storage
logger = logging.getLogger(__name__)

router = APIRouter()


class TryOnRequest(BaseModel):
    """Запрос на виртуальную примерку"""

    model_image_url: str = Field(..., description="URL изображения модели")
    product_image_url: str = Field(..., description="URL изображения продукта")
    product_url: Optional[str] = Field(None, description="Исходный URL товара с сайта")
    model_height_cm: float = Field(..., description="Рост модели в см", ge=100, le=250)
    product_width_cm: float = Field(
        default=30, description="Ширина продукта в см", ge=1, le=200
    )
    product_height_cm: float = Field(
        default=0,
        description="Высота продукта в см (0 = сохранить пропорции)",
        ge=0,
        le=200,
    )
    item_kind: str = Field(default="bag", description="Тип продукта: bag или garment")
    placement: str = Field(default="left_shoulder", description="Размещение для сумок")
    offset_x_pct: float = Field(default=-6.0, description="Смещение по X в %")
    offset_y_pct: float = Field(default=0.0, description="Смещение по Y в %")
    visible_top_pct: float = Field(
        default=0.04, description="Верхний срез фигуры (0..1)"
    )
    visible_bottom_pct: float = Field(
        default=0.98, description="Нижний срез фигуры (0..1)"
    )
    scale_bias: float = Field(default=1.0, description="Финальный множитель размера")
    variations: int = Field(
        default=0,
        description="Количество дополнительных вариаций модели (0-3)",
        ge=0,
        le=3,
    )


class TryOnResponse(BaseModel):
    """Ответ виртуальной примерки"""

    status: str
    job_ids: list[str]
    output_urls: list[str]  # Список всех результатов (основной + вариации)
    model_urls: list[str]  # Список URL моделей (основная + вариации)
    product_scaled_url: str
    message: str


async def download_image(url: str) -> bytes:
    """Скачивает изображение по URL"""
    try:
        # Если это относительная ссылка на наш API - используем прямой доступ к файлу
        if url.startswith("/api/v1/files/download/"):
            file_id = url.split("/")[-1]

            # Получаем файл напрямую из файлового процессора
            file_processor = await get_default_file_processor()
            file_record = await file_processor.get_file_record(file_id)

            if not file_record:
                raise HTTPException(status_code=404, detail=f"Файл {file_id} не найден")

            # Используем прямую ссылку на S3
            s3_url = file_record.direct_s3_url
            if not s3_url:
                raise HTTPException(
                    status_code=500, detail="Не удалось получить ссылку на файл"
                )

            url = s3_url  # Заменяем на абсолютную ссылку

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(url, headers=headers, follow_redirects=True)
            response.raise_for_status()

            # Проверяем, что это действительно изображение
            content_type = response.headers.get("content-type", "").lower()
            if not content_type.startswith("image/"):
                raise HTTPException(
                    status_code=400,
                    detail=f"URL не содержит изображение. Content-Type: {content_type}",
                )

            content = response.content

            # Дополнительная проверка - пытаемся открыть как изображение
            try:
                Image.open(io.BytesIO(content)).verify()
            except Exception:
                raise HTTPException(
                    status_code=400,
                    detail="Скачанный контент не является валидным изображением",
                )

            return content

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=400, detail=f"Не удалось скачать изображение с {url}: {str(e)}"
        )


@router.post("/try-on", response_model=TryOnResponse)
async def virtual_try_on_api(request: TryOnRequest):
    """
    Виртуальная примерка одежды и аксессуаров.

    Эмулирует работу агента:
    1. Скачивает изображения по URL
    2. Загружает их в наш S3 через FileProcessor
    3. Получает file_id из нашей системы
    4. Вызывает upload_image_for_try_on.ainvoke()
    5. Затем вызывает virtual_try_on.ainvoke()
    """
    file_processor = None

    try:
        logger.info(
            f"Начинаем виртуальную примерку: модель={request.model_image_url}, продукт={request.product_image_url}"
        )

        # Скачиваем изображения
        model_bytes = await download_image(request.model_image_url)
        product_bytes = await download_image(request.product_image_url)

        logger.info(
            f"Изображения скачаны: модель={len(model_bytes)} байт, продукт={len(product_bytes)} байт"
        )

        # Инициализируем FileProcessor для загрузки в наш S3 (как делал бы агент)
        file_processor = FileProcessor()

        # Загружаем изображение модели в наш S3 и получаем file_id (публично доступно для FASHN)
        model_record = await file_processor.process_file_from_bytes(
            data=model_bytes,
            original_name="model.jpg",
            content_type="image/jpeg",
            uploaded_by="fashn_api",
            public=True,
        )
        logger.info(
            f"Модель загружена в S3: {model_record.url}, file_id: {model_record.file_id}"
        )

        # Загружаем изображение продукта в наш S3 и получаем file_id (публично доступно для FASHN)
        product_record = await file_processor.process_file_from_bytes(
            data=product_bytes,
            original_name="product.png",
            content_type="image/png",
            uploaded_by="fashn_api",
            public=True,
        )
        logger.info(
            f"Продукт загружен в S3: {product_record.url}, file_id: {product_record.file_id}"
        )

        # Теперь работаем как агент - вызываем upload_image_for_try_on.ainvoke()
        # Но файлы уже загружены, поэтому этот шаг можно пропустить
        # Сразу вызываем virtual_try_on.ainvoke() с file_id

        # Используем правильные ключи для storage (s3:provider:file_id)
        model_storage_key = model_record.key  # s3:vkcloud:file_id
        product_storage_key = product_record.key  # s3:vkcloud:file_id

        logger.info(
            f"Вызываем virtual_try_on.ainvoke() с ключами: модель={model_storage_key}, продукт={product_storage_key}"
        )

        result_text = await virtual_try_on.ainvoke(
            {
                "model_image_file_id": model_storage_key,
                "product_image_file_id": product_storage_key,
                "model_height_cm": request.model_height_cm,
                "product_width_cm": request.product_width_cm,
                "product_height_cm": request.product_height_cm,
                "item_kind": request.item_kind,
                "placement": request.placement,
                "offset_x_pct": request.offset_x_pct,
                "offset_y_pct": request.offset_y_pct,
                "visible_top_pct": request.visible_top_pct,
                "visible_bottom_pct": request.visible_bottom_pct,
                "scale_bias": request.scale_bias,
                "variations": request.variations,
                "product_url": request.product_url,
            }
        )

        logger.info(f"Результат виртуальной примерки: {result_text}")

        # Парсим результат для извлечения URL-ов
        if request.variations == 0:
            # Обычный результат
            job_id_match = re.search(r"Job ID: ([^\n]+)", result_text)
            job_id = job_id_match.group(1) if job_id_match else None

            output_url_match = re.search(
                r"Финальное изображение: ([^\n]+)", result_text
            )
            output_url = output_url_match.group(1) if output_url_match else ""

            model_url_match = re.search(r"Изображение модели: ([^\n]+)", result_text)
            model_url = model_url_match.group(1) if model_url_match else ""

            product_url_match = re.search(
                r"Изображение продукта: ([^\n]+)", result_text
            )
            product_scaled_url = product_url_match.group(1) if product_url_match else ""

            if not output_url:
                raise HTTPException(
                    status_code=500, detail="Не удалось получить URL результата"
                )

            return TryOnResponse(
                status="ok",
                job_ids=[job_id] if job_id else [],
                output_urls=[output_url],
                model_urls=[model_url],
                product_scaled_url=product_scaled_url,
                message=f"Виртуальная примерка завершена успешно! Исходные файлы: модель={model_record.url}, продукт={product_record.url}",
            )
        else:
            # Результат с вариациями
            job_ids = re.findall(r"Job ID: ([^\n]+)", result_text)
            output_urls = re.findall(r"Финальное изображение: ([^\n]+)", result_text)
            model_urls = re.findall(r"Модель: ([^\n]+)", result_text)

            product_url_match = re.search(r"Продукт: ([^\n]+)", result_text)
            product_scaled_url = product_url_match.group(1) if product_url_match else ""

            if not output_urls:
                raise HTTPException(
                    status_code=500, detail="Не удалось получить URL результатов"
                )

            return TryOnResponse(
                status="ok",
                job_ids=job_ids,
                output_urls=output_urls,
                model_urls=model_urls,
                product_scaled_url=product_scaled_url,
                message=f"Виртуальная примерка с {request.variations} вариациями завершена! Создано {len(output_urls)} изображений",
            )

    finally:
        # Закрываем ресурсы
        if file_processor:
            await file_processor.close()


@router.get("/help")
async def get_fashn_help():
    """
    Получить справку по использованию FASHN API.
    """
    return {
        "title": "FASHN - Виртуальная примерка одежды и аксессуаров",
        "endpoints": {
            "/try-on": "Основной эндпоинт для виртуальной примерки (поддерживает вариации)",
            "/help": "Эта справка",
        },
        "parameters": {
            "model_image_url": "URL изображения модели (обязательно)",
            "product_image_url": "URL изображения продукта (обязательно)",
            "model_height_cm": "Рост модели в см (100-250)",
            "product_width_cm": "Ширина продукта в см (1-200)",
            "product_height_cm": "Высота продукта в см (0-200, 0 = сохранить пропорции)",
            "item_kind": "Тип продукта: 'bag' или 'garment'",
            "placement": "Размещение для сумок: 'left_shoulder', 'right_shoulder', 'left_hand', 'right_hand', 'center'",
            "variations": "Количество дополнительных вариаций модели (0-3)",
        },
        "examples": {
            "bag_try_on": {
                "model_image_url": "https://example.com/model.jpg",
                "product_image_url": "https://example.com/bag.png",
                "model_height_cm": 170,
                "product_width_cm": 30,
                "item_kind": "bag",
                "placement": "left_shoulder",
            },
            "garment_try_on": {
                "model_image_url": "https://example.com/model.jpg",
                "product_image_url": "https://example.com/dress.png",
                "model_height_cm": 170,
                "item_kind": "garment",
            },
            "try_on_with_variations": {
                "model_image_url": "https://example.com/model.jpg",
                "product_image_url": "https://example.com/bag.png",
                "model_height_cm": 170,
                "product_width_cm": 30,
                "item_kind": "bag",
                "variations": 2,
            },
        },
    }


@router.get("/history", response_model=List[dict])
async def get_try_on_history(limit: int = 20, offset: int = 0):
    """
    Получает историю примерок текущего пользователя
    
    Args:
        limit: Количество записей для возврата (по умолчанию 20)
        offset: Смещение для пагинации (по умолчанию 0)
    
    Returns:
        Список записей TryOnRecord для текущего пользователя
    """

    
    # Получаем пользователя из контекста
    context = get_context()
    if not context or not context.user:
        raise HTTPException(status_code=401, detail="User not authenticated")
    
    user_id = context.user.user_id
    
    try:
        storage = Storage()
        
        # Получаем все ключи примерок для пользователя
        prefix = f"try_on:{user_id}:"
        keys = await storage.list_by_prefix(prefix, limit=100)
        
        if not keys:
            return []
        
        # Сортируем ключи по времени создания (новые первыми)
        keys.sort(reverse=True)
        
        # Применяем пагинацию
        paginated_keys = keys[offset:offset + limit]
        
        # Получаем данные для каждого ключа
        try_on_records = []
        for key in paginated_keys:
            data = await storage.get(key)
            if data:
                # Парсим JSON обратно в dict
                
                try_on_data = json.loads(data) if isinstance(data, str) else data
                try_on_records.append(try_on_data)
        
        logger.info(f"Возвращаем {len(try_on_records)} записей истории для пользователя {user_id}")
        return try_on_records
        
    except Exception as e:
        logger.error(f"Ошибка получения истории примерок для пользователя {user_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get try-on history: {str(e)}")


@router.get("/history/{try_on_id}")
async def get_try_on_details(try_on_id: str):
    """
    Получает детали конкретной примерки
    
    Args:
        try_on_id: ID примерки (полный ключ: try_on:user_id:uuid)
    
    Returns:
        Детали записи TryOnRecord
    """

    
    # Получаем пользователя из контекста
    context = get_context()
    if not context or not context.user:
        raise HTTPException(status_code=401, detail="User not authenticated")
    
    user_id = context.user.user_id
    
    # Проверяем, что примерка принадлежит текущему пользователю
    if not try_on_id.startswith(f"try_on:{user_id}:"):
        raise HTTPException(status_code=403, detail="Access denied to this try-on record")
    
    try:
        storage = Storage()
        data = await storage.get(try_on_id)
        
        if not data:
            raise HTTPException(status_code=404, detail="Try-on record not found")
        
        try_on_data = json.loads(data) if isinstance(data, str) else data
        return try_on_data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка получения примерки {try_on_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get try-on details: {str(e)}")


@router.get("/history-panel")
async def get_history_panel():
    """
    Возвращает HTML панель с историей примерок для HTMX
    """
    from fastapi.responses import HTMLResponse
    from ...core.context import get_context
    from ...core.storage import Storage
    import json
    
    # Получаем пользователя из контекста
    context = get_context()
    if not context or not context.user:
        return HTMLResponse("""
            <div class="history-panel-content active">
                <div class="history-panel-header">
                    <h2 class="history-panel-title">Your Try-On History</h2>
                    <button class="history-close-btn" onclick="closeHistoryPanel()">
                        <i class="bi bi-x"></i>
                    </button>
                </div>
                <div class="history-content">
                    <p style="text-align: center; color: #6b7280; padding: 40px;">
                        Please log in to view your try-on history
                    </p>
                </div>
            </div>
        """)
    
    user_id = context.user.user_id
    
    try:
        storage = Storage()
        
        # Получаем все ключи примерок для пользователя
        prefix = f"try_on:{user_id}:"
        keys = await storage.list_by_prefix(prefix, limit=100)
        
        if not keys:
            return HTMLResponse("""
                <div class="history-panel-content active">
                    <div class="history-panel-header">
                        <h2 class="history-panel-title">Your Try-On History</h2>
                        <button class="history-close-btn" onclick="closeHistoryPanel()">
                            <i class="bi bi-x"></i>
                        </button>
                    </div>
                    <div class="history-content">
                        <div style="text-align: center; padding: 60px 20px;">
                            <i class="bi bi-clock-history" style="font-size: 48px; color: #9ca3af; margin-bottom: 16px;"></i>
                            <h3 style="color: var(--dark-gray); margin-bottom: 8px;">No try-ons yet</h3>
                            <p style="color: #6b7280;">Start creating styled images to build your history</p>
                        </div>
                    </div>
                </div>
            """)
        
        # Сортируем ключи по времени создания (новые первыми)
        keys.sort(reverse=True)
        
        # Ограничиваем до 20 последних записей для панели
        recent_keys = keys[:20]
        
        # Получаем данные для каждого ключа
        try_on_records = []
        for key in recent_keys:
            data = await storage.get(key)
            if data:
                try_on_data = json.loads(data) if isinstance(data, str) else data
                try_on_records.append(try_on_data)
        
        # Генерируем HTML для каждой примерки
        history_items_html = ""
        for record in try_on_records:
            # Форматируем дату
            try:
                from datetime import datetime
                created_date = datetime.fromisoformat(record['created_at'].replace('Z', '+00:00'))
                formatted_date = created_date.strftime('%d.%m.%Y %H:%M')
            except:
                formatted_date = "Unknown date"
            
            # Получаем первый результат для отображения
            result_url = record['result_urls'][0] if record['result_urls'] else '/static/img/empty.png'
            
            # Получаем данные о товаре если есть product_url
            product_info = None
            product_link = "Product"
            if record.get('product_url'):
                try:
                    # Вызываем функцию парсинга напрямую, без HTTP запроса
                    from urllib.parse import urlparse
                    from . import admin  # Импортируем модуль admin для доступа к функции парсинга
                    
                    # Вызываем функцию парсинга напрямую
                    product_info = await admin.parse_product_url(record['product_url'])
                    
                    # Короткая ссылка на товар
                    parsed_url = urlparse(record['product_url'])
                    product_link = parsed_url.path.split('/')[-1][:8] + "..."
                except Exception as e:
                    logger.warning(f"Не удалось получить данные товара для {record.get('product_url')}: {e}")
                    product_link = "Product"
                    product_info = None
            
            # Формируем HTML для товара
            product_section = ""
            if product_info and product_info.get('status') == 'success':
                product_image = product_info.get('image_url', '/static/img/empty.png')
                product_title = product_info.get('title', 'Product')
                dimensions = product_info.get('dimensions', {})
                
                dimensions_text = ""
                if dimensions.get('length'):
                    dimensions_text += f"L: {dimensions['length']}cm "
                if dimensions.get('width'):
                    dimensions_text += f"W: {dimensions['width']}cm "
                if dimensions.get('height'):
                    dimensions_text += f"H: {dimensions['height']}cm"
                
                product_section = f"""
                    <div class="history-product-info">
                        <a href="{record['product_url']}" target="_blank" class="history-product-image-link">
                            <img src="{product_image}" alt="Product" class="history-product-image">
                        </a>
                        <div class="history-product-details">
                            <div class="history-product-title">{product_title[:30]}...</div>
                            <div class="history-product-dimensions">{dimensions_text}</div>
                        </div>
                    </div>
                """
            
            history_items_html += f"""
                <div class="history-item">
                    <div class="history-item-date">{formatted_date}</div>
                    
                    <div class="history-original-photo" onclick="openFullscreen('{record['model_url']}')">
                        <img src="{record['model_url']}" alt="Original photo">
                    </div>
                    
                    <div class="history-connector">
                        {product_section}
                    </div>
                    
                    <div class="history-result-photo" onclick="openFullscreen('{result_url}')">
                        <img src="{result_url}" alt="Result photo">
                    </div>
                </div>
            """
        
        html_content = f"""
            <div class="history-panel-content active">
                <div class="history-panel-header">
                    <h2 class="history-panel-title">Your Try-On History</h2>
                    <button class="history-close-btn" onclick="closeHistoryPanel()">
                        <i class="bi bi-x"></i>
                    </button>
                </div>
                <div class="history-content">
                    {history_items_html}
                </div>
            </div>
        """
        
        return HTMLResponse(html_content)
        
    except Exception as e:
        logger.error(f"Ошибка получения панели истории для пользователя {user_id}: {e}")
        return HTMLResponse(f"""
            <div class="history-panel-content active">
                <div class="history-panel-header">
                    <h2 class="history-panel-title">Your Try-On History</h2>
                    <button class="history-close-btn" onclick="closeHistoryPanel()">
                        <i class="bi bi-x"></i>
                    </button>
                </div>
                <div class="history-content">
                    <p style="text-align: center; color: #ef4444; padding: 40px;">
                        Error loading history: {str(e)}
                    </p>
                </div>
            </div>
        """)
