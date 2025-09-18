"""
API для работы с файлами - скачивание через платформу
"""

import logging
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
import httpx

from app.core.file_processor import get_default_file_processor
from app.core.context import get_context

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/download/{file_id}")
async def download_file(file_id: str):
    """
    Скачивание файла через платформу с проверкой доступа
    """
    try:
        # Получаем текущего пользователя из контекста
        context = get_context()
        if not context:
            raise HTTPException(status_code=401, detail="Нет контекста пользователя")

        current_user = context.user

        # Получаем информацию о файле
        file_processor = await get_default_file_processor()
        file_record = await file_processor.get_file_record(file_id)

        if not file_record:
            raise HTTPException(status_code=404, detail="Файл не найден")

        # Проверяем права доступа (пока простая проверка)
        # TODO: Добавить более сложную логику проверки прав
        if file_record.uploaded_by and file_record.uploaded_by != current_user.user_id:
            # Разрешаем доступ к файлам загруженным в чате
            if not file_record.metadata.get(
                "web_upload"
            ) and not file_record.metadata.get("telegram_upload"):
                raise HTTPException(status_code=403, detail="Нет доступа к файлу")

        # Получаем прямую ссылку на S3 для стриминга
        s3_url = file_record.direct_s3_url
        if not s3_url:
            raise HTTPException(
                status_code=500, detail="Не удалось получить ссылку на файл"
            )

        # Стримим файл через нашу платформу
        async def stream_file():
            async with httpx.AsyncClient() as client:
                async with client.stream("GET", s3_url) as response:
                    if response.status_code != 200:
                        raise HTTPException(
                            status_code=500, detail="Ошибка получения файла"
                        )

                    async for chunk in response.aiter_bytes():
                        yield chunk

        # Возвращаем файл как стрим
        return StreamingResponse(
            stream_file(),
            media_type=file_record.content_type,
            headers={
                "Content-Disposition": f'attachment; filename="{file_record.original_name}"',
                "Content-Length": str(file_record.file_size),
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка скачивания файла {file_id}: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")


@router.get("/info/{file_id}")
async def get_file_info(file_id: str):
    """
    Получение информации о файле
    """
    try:
        # Получаем текущего пользователя из контекста
        context = get_context()
        if not context:
            raise HTTPException(status_code=401, detail="Нет контекста пользователя")

        current_user = context.user

        file_processor = await get_default_file_processor()
        file_record = await file_processor.get_file_record(file_id)

        if not file_record:
            raise HTTPException(status_code=404, detail="Файл не найден")

        # Базовая проверка доступа
        if file_record.uploaded_by and file_record.uploaded_by != current_user.user_id:
            if not file_record.metadata.get(
                "web_upload"
            ) and not file_record.metadata.get("telegram_upload"):
                raise HTTPException(status_code=403, detail="Нет доступа к файлу")

        return {
            "file_id": file_record.file_id,
            "original_name": file_record.original_name,
            "content_type": file_record.content_type,
            "file_size": file_record.file_size,
            "created_at": file_record.created_at,
            "tags": file_record.tags,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка получения информации о файле {file_id}: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")
