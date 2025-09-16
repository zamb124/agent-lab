"""
API эндпоинты для FASHN виртуальной примерки.
"""
import logging
import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

from ...core.file_processor import FileProcessor
from ...tools.fashn_tools import virtual_try_on, upload_image_for_try_on

logger = logging.getLogger(__name__)

router = APIRouter()


class TryOnRequest(BaseModel):
    """Запрос на виртуальную примерку"""
    model_image_url: str = Field(..., description="URL изображения модели")
    product_image_url: str = Field(..., description="URL изображения продукта")
    model_height_cm: float = Field(..., description="Рост модели в см", ge=100, le=250)
    product_width_cm: float = Field(default=30, description="Ширина продукта в см", ge=1, le=200)
    product_height_cm: float = Field(default=0, description="Высота продукта в см (0 = сохранить пропорции)", ge=0, le=200)
    item_kind: str = Field(default="bag", description="Тип продукта: bag или garment")
    placement: str = Field(default="left_shoulder", description="Размещение для сумок")
    offset_x_pct: float = Field(default=-6.0, description="Смещение по X в %")
    offset_y_pct: float = Field(default=0.0, description="Смещение по Y в %")
    visible_top_pct: float = Field(default=0.04, description="Верхний срез фигуры (0..1)")
    visible_bottom_pct: float = Field(default=0.98, description="Нижний срез фигуры (0..1)")
    scale_bias: float = Field(default=1.0, description="Финальный множитель размера")
    variations: int = Field(default=0, description="Количество дополнительных вариаций модели (0-3)", ge=0, le=3)


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
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(url, headers=headers, follow_redirects=True)
            response.raise_for_status()
            
            # Проверяем, что это действительно изображение
            content_type = response.headers.get('content-type', '').lower()
            if not content_type.startswith('image/'):
                raise HTTPException(
                    status_code=400, 
                    detail=f"URL не содержит изображение. Content-Type: {content_type}"
                )
            
            content = response.content
            
            # Дополнительная проверка - пытаемся открыть как изображение
            try:
                from PIL import Image
                import io
                Image.open(io.BytesIO(content)).verify()
            except Exception:
                raise HTTPException(
                    status_code=400,
                    detail="Скачанный контент не является валидным изображением"
                )
            
            return content
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Не удалось скачать изображение с {url}: {str(e)}")


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
        logger.info(f"Начинаем виртуальную примерку: модель={request.model_image_url}, продукт={request.product_image_url}")
        
        # Скачиваем изображения
        model_bytes = await download_image(request.model_image_url)
        product_bytes = await download_image(request.product_image_url)
        
        logger.info(f"Изображения скачаны: модель={len(model_bytes)} байт, продукт={len(product_bytes)} байт")
        
        # Инициализируем FileProcessor для загрузки в наш S3 (как делал бы агент)
        file_processor = FileProcessor()
        
        # Загружаем изображение модели в наш S3 и получаем file_id (публично доступно для FASHN)
        model_record = await file_processor.process_file_from_bytes(
            data=model_bytes,
            original_name="model.jpg",
            content_type="image/jpeg",
            uploaded_by="fashn_api",
            public=True
        )
        logger.info(f"Модель загружена в S3: {model_record.url}, file_id: {model_record.file_id}")
        
        # Загружаем изображение продукта в наш S3 и получаем file_id (публично доступно для FASHN)
        product_record = await file_processor.process_file_from_bytes(
            data=product_bytes,
            original_name="product.png", 
            content_type="image/png",
            uploaded_by="fashn_api",
            public=True
        )
        logger.info(f"Продукт загружен в S3: {product_record.url}, file_id: {product_record.file_id}")
        
        # Теперь работаем как агент - вызываем upload_image_for_try_on.ainvoke()
        # Но файлы уже загружены, поэтому этот шаг можно пропустить
        # Сразу вызываем virtual_try_on.ainvoke() с file_id
        
        # Используем правильные ключи для storage (s3:provider:file_id)
        model_storage_key = model_record.key  # s3:vkcloud:file_id
        product_storage_key = product_record.key  # s3:vkcloud:file_id
        
        logger.info(f"Вызываем virtual_try_on.ainvoke() с ключами: модель={model_storage_key}, продукт={product_storage_key}")
        
        result_text = await virtual_try_on.ainvoke({
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
        })
        
        logger.info(f"Результат виртуальной примерки: {result_text}")
        
        # Парсим результат для извлечения URL-ов
        import re
        
        if request.variations == 0:
            # Обычный результат
            job_id_match = re.search(r"Job ID: ([^\n]+)", result_text)
            job_id = job_id_match.group(1) if job_id_match else None
            
            output_url_match = re.search(r"Финальное изображение: ([^\n]+)", result_text)
            output_url = output_url_match.group(1) if output_url_match else ""
            
            model_url_match = re.search(r"Изображение модели: ([^\n]+)", result_text)
            model_url = model_url_match.group(1) if model_url_match else ""
            
            product_url_match = re.search(r"Изображение продукта: ([^\n]+)", result_text)
            product_scaled_url = product_url_match.group(1) if product_url_match else ""
            
            if not output_url:
                raise HTTPException(status_code=500, detail="Не удалось получить URL результата")
            
            return TryOnResponse(
                status="ok",
                job_ids=[job_id] if job_id else [],
                output_urls=[output_url],
                model_urls=[model_url],
                product_scaled_url=product_scaled_url,
                message=f"Виртуальная примерка завершена успешно! Исходные файлы: модель={model_record.url}, продукт={product_record.url}"
            )
        else:
            # Результат с вариациями
            job_ids = re.findall(r"Job ID: ([^\n]+)", result_text)
            output_urls = re.findall(r"Финальное изображение: ([^\n]+)", result_text)
            model_urls = re.findall(r"Модель: ([^\n]+)", result_text)
            
            product_url_match = re.search(r"Продукт: ([^\n]+)", result_text)
            product_scaled_url = product_url_match.group(1) if product_url_match else ""
            
            if not output_urls:
                raise HTTPException(status_code=500, detail="Не удалось получить URL результатов")
            
            return TryOnResponse(
                status="ok", 
                job_ids=job_ids,
                output_urls=output_urls,
                model_urls=model_urls,
                product_scaled_url=product_scaled_url,
                message=f"Виртуальная примерка с {request.variations} вариациями завершена! Создано {len(output_urls)} изображений"
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
            "/help": "Эта справка"
        },
        "parameters": {
            "model_image_url": "URL изображения модели (обязательно)",
            "product_image_url": "URL изображения продукта (обязательно)", 
            "model_height_cm": "Рост модели в см (100-250)",
            "product_width_cm": "Ширина продукта в см (1-200)",
            "product_height_cm": "Высота продукта в см (0-200, 0 = сохранить пропорции)",
            "item_kind": "Тип продукта: 'bag' или 'garment'",
            "placement": "Размещение для сумок: 'left_shoulder', 'right_shoulder', 'left_hand', 'right_hand', 'center'",
            "variations": "Количество дополнительных вариаций модели (0-3)"
        },
        "examples": {
            "bag_try_on": {
                "model_image_url": "https://example.com/model.jpg",
                "product_image_url": "https://example.com/bag.png",
                "model_height_cm": 170,
                "product_width_cm": 30,
                "item_kind": "bag",
                "placement": "left_shoulder"
            },
            "garment_try_on": {
                "model_image_url": "https://example.com/model.jpg",
                "product_image_url": "https://example.com/dress.png",
                "model_height_cm": 170,
                "item_kind": "garment"
            },
            "try_on_with_variations": {
                "model_image_url": "https://example.com/model.jpg",
                "product_image_url": "https://example.com/bag.png",
                "model_height_cm": 170,
                "product_width_cm": 30,
                "item_kind": "bag",
                "variations": 2
            }
        }
    }
