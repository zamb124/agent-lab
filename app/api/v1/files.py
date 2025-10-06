"""
API для работы с файлами и аудио - скачивание через платформу
"""

import logging
from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
import httpx
from fastapi.responses import Response
from app.core.file_processor import get_default_file_processor
from app.core.audio_processor import get_default_audio_processor
from app.core.context import get_context

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/download/{file_id}")
async def download_file(file_id: str):
    """
    Скачивание файла через платформу с проверкой доступа
    """
    try:
        # Получаем информацию о файле
        file_processor = await get_default_file_processor()
        file_record = await file_processor.get_file_record(file_id)

        if not file_record:
            raise HTTPException(status_code=404, detail="Файл не найден")

        # Проверяем является ли файл публичным
        is_public_file = file_record.is_public

        if not is_public_file:
            # Для приватных файлов требуем авторизацию
            context = get_context()
            if not context:
                raise HTTPException(status_code=401, detail="Нет контекста пользователя")

            current_user = context.user

            # Проверяем права доступа
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


# ============ АУДИО API ============

@router.post("/audio/upload")
async def upload_audio(file: UploadFile = File(...), auto_recognize: bool = True):
    """
    Загрузка аудиофайла с автоматическим распознаванием речи
    """
    try:
        # Получаем текущего пользователя из контекста
        context = get_context()
        current_user = context.user if context else None

        # Проверяем что это аудиофайл
        if not file.content_type or not file.content_type.startswith('audio/'):
            raise HTTPException(status_code=400, detail="Файл должен быть аудиофайлом")

        # Читаем данные файла
        audio_data = await file.read()
        
        # Обрабатываем через AudioProcessor
        audio_processor = await get_default_audio_processor()
        audio_record = await audio_processor.process_audio_from_bytes(
            data=audio_data,
            original_name=file.filename or "audio.wav",
            content_type=file.content_type,
            uploaded_by=current_user.user_id if current_user else None,
            auto_recognize=auto_recognize,
            metadata={"web_upload": True}
        )

        return {
            "audio_id": audio_record.audio_id,
            "original_name": audio_record.original_name,
            "content_type": audio_record.content_type,
            "file_size": audio_record.file_size,
            "status": audio_record.status.value,
            "url": audio_record.url,
            "recognition_text": audio_record.recognition_text,
            "message": audio_processor.format_audio_message(audio_record)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка загрузки аудиофайла: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")


@router.get("/download/audio/{audio_id}")
async def download_audio(audio_id: str):
    """
    Скачивание аудиофайла через платформу
    """
    try:
        # Получаем текущего пользователя из контекста
        context = get_context()
        if not context:
            raise HTTPException(status_code=401, detail="Нет контекста пользователя")

        current_user = context.user

        # Получаем информацию об аудиофайле
        audio_processor = await get_default_audio_processor()
        audio_record = await audio_processor.get_audio_record(audio_id)

        if not audio_record:
            logger.error(f"Аудиофайл {audio_id} не найден в БД")
            raise HTTPException(status_code=404, detail="Аудиофайл не найден")
            
        logger.info(f"🔍 Найден аудиофайл: {audio_record.s3_key}, размер: {audio_record.file_size}")

        # Проверяем права доступа
        if audio_record.uploaded_by and audio_record.uploaded_by != current_user.user_id:
            if not audio_record.metadata.get("web_upload") and not audio_record.metadata.get("telegram_upload"):
                raise HTTPException(status_code=403, detail="Нет доступа к аудиофайлу")

        # Скачиваем файл напрямую из S3
        s3_client = await audio_processor._get_s3_client()
        audio_data = await s3_client.download_bytes(audio_record.s3_key)
        
        if not audio_data:
            logger.error(f"Не удалось скачать аудиофайл {audio_id} из S3")
            raise HTTPException(status_code=500, detail="Ошибка получения аудиофайла")
            
        logger.info(f"✅ Скачан аудиофайл для API: {len(audio_data)} байт")

        # Возвращаем аудиофайл для прямого воспроизведения в браузере
        
        return Response(
            content=audio_data,
            media_type=audio_record.content_type,
            headers={
                "Content-Disposition": f'inline; filename="{audio_record.original_name}"',
                "Accept-Ranges": "bytes",
                "Cache-Control": "public, max-age=3600",
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка скачивания аудиофайла {audio_id}: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")


@router.get("/audio/{audio_id}/info")
async def get_audio_info(audio_id: str):
    """
    Получение информации об аудиофайле
    """
    try:
        # Получаем текущего пользователя из контекста
        context = get_context()
        if not context:
            raise HTTPException(status_code=401, detail="Нет контекста пользователя")

        current_user = context.user

        audio_processor = await get_default_audio_processor()
        audio_record = await audio_processor.get_audio_record(audio_id)

        if not audio_record:
            raise HTTPException(status_code=404, detail="Аудиофайл не найден")

        # Базовая проверка доступа
        if audio_record.uploaded_by and audio_record.uploaded_by != current_user.user_id:
            if not audio_record.metadata.get("web_upload") and not audio_record.metadata.get("telegram_upload"):
                raise HTTPException(status_code=403, detail="Нет доступа к аудиофайлу")

        return {
            "audio_id": audio_record.audio_id,
            "original_name": audio_record.original_name,
            "content_type": audio_record.content_type,
            "file_size": audio_record.file_size,
            "duration": audio_record.duration,
            "status": audio_record.status.value,
            "recognition_text": audio_record.recognition_text,
            "recognition_confidence": audio_record.recognition_confidence,
            "created_at": audio_record.created_at,
            "tags": audio_record.tags,
            "url": audio_record.url,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка получения информации об аудиофайле {audio_id}: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")


@router.post("/audio/{audio_id}/recognize")
async def recognize_audio(audio_id: str):
    """
    Принудительное распознавание речи в аудиофайле
    """
    try:
        # Получаем текущего пользователя из контекста
        context = get_context()
        if not context:
            raise HTTPException(status_code=401, detail="Нет контекста пользователя")

        current_user = context.user

        audio_processor = await get_default_audio_processor()
        audio_record = await audio_processor.get_audio_record(audio_id)

        if not audio_record:
            raise HTTPException(status_code=404, detail="Аудиофайл не найден")

        # Базовая проверка доступа
        if audio_record.uploaded_by and audio_record.uploaded_by != current_user.user_id:
            if not audio_record.metadata.get("web_upload") and not audio_record.metadata.get("telegram_upload"):
                raise HTTPException(status_code=403, detail="Нет доступа к аудиофайлу")

        # Запускаем распознавание
        success = await audio_processor.recognize_audio(audio_id)
        
        if not success:
            raise HTTPException(status_code=500, detail="Не удалось распознать речь")

        # Получаем обновленную запись
        audio_record = await audio_processor.get_audio_record(audio_id)
        
        return {
            "audio_id": audio_record.audio_id,
            "status": audio_record.status.value,
            "recognition_text": audio_record.recognition_text,
            "recognition_confidence": audio_record.recognition_confidence,
            "recognition_qid": audio_record.recognition_qid,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка распознавания аудиофайла {audio_id}: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")
