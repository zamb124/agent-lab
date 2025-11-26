"""
API для работы с файлами и аудио - скачивание через платформу
"""

import logging
from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import Response
import httpx
from core.files.processors import get_default_file_processor
from apps.agents.services.core_clients.s3_client import S3ClientFactory
from core.context import get_context

logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["Файлы и медиа"],
    responses={
        404: {"description": "Файл не найден"},
        403: {"description": "Нет доступа к файлу"},
        500: {"description": "Внутренняя ошибка сервера"}
    }
)


@router.get("/download/{file_id}", summary="Скачать файл")
async def download_file(file_id: str):
    """
    Скачивание файла или аудио с проверкой прав доступа.
    
    **Поддерживаемые типы:**
    - Обычные файлы (документы, изображения)
    - Аудиофайлы (с распознанной речью)
    
    **Безопасность:**
    - Проверка прав доступа
    - Публичные файлы доступны всем
    - Приватные файлы только владельцу
    
    Args:
        file_id: ID файла в системе (получается при загрузке или из сообщения бота)
        
    Returns:
        Файл для скачивания (streaming)
    """
    try:
        # Определяем тип файла по префиксу
        if file_id.startswith("audio_"):
            # Это аудиофайл
            from core.files.processors import get_default_audio_processor
            audio_processor = await get_default_audio_processor()
            file_record = await audio_processor.get_audio_record(file_id)
            
            if not file_record:
                raise HTTPException(status_code=404, detail="Аудиофайл не найден")
        else:
            # Обычный файл
            file_processor = await get_default_file_processor()
            file_record = await file_processor.get_file_record(file_id)
            
            if not file_record:
                raise HTTPException(status_code=404, detail="Файл не найден")

        # Проверяем является ли файл публичным
        is_public_file = getattr(file_record, 'is_public', False)

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

        # Генерируем signed URL на 1 час для скачивания
        s3_client = S3ClientFactory.create_client_for_bucket(file_record.s3_bucket)
        
        signed_url = await s3_client.generate_presigned_url(
            key=file_record.s3_key,
            expiration=3600  # 1 час
        )
        
        if not signed_url:
            raise HTTPException(
                status_code=500, 
                detail=f"Не удалось создать signed URL для файла {file_id}"
            )

        logger.info(f"✅ Создан signed URL для {file_id} (срок: 1 час)")

        # Скачиваем целиком без стриминга
        timeout = httpx.Timeout(30.0, connect=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                resp = await client.get(signed_url)
            except httpx.ConnectTimeout as e:
                logger.error("Таймаут соединения к файловому хранилищу", exc_info=True)
                raise HTTPException(status_code=504, detail="Таймаут соединения с файловым хранилищем") from e
            except httpx.RequestError as e:
                logger.error("Ошибка сети при обращении к файловому хранилищу", exc_info=True)
                raise HTTPException(status_code=502, detail="Ошибка соединения с файловым хранилищем") from e

            if resp.status_code != 200:
                raise HTTPException(status_code=resp.status_code, detail=f"Не удалось скачать файл (S3: {resp.status_code})")

            data = await resp.aread()

        disposition = "inline" if file_id.startswith("audio_") else "attachment"
        headers = {
            "Content-Disposition": f'{disposition}; filename="{file_record.original_name}"',
            "Accept-Ranges": "bytes",
            "Cache-Control": "public, max-age=3600" if file_id.startswith("audio_") else "no-cache",
            "Content-Length": str(len(data)) if data is not None else "0",
        }

        return Response(content=data, media_type=file_record.content_type, headers=headers)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка скачивания файла {file_id}: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")


@router.get("/info/{file_id}", summary="Информация о файле")
async def get_file_info(file_id: str):
    """
    Получает метаданные файла без скачивания.
    
    **Возвращает:**
    - Название файла
    - Размер
    - Тип (MIME type)
    - Дата загрузки
    - Теги
    - Для аудио: распознанный текст и уверенность
    
    Полезно для отображения информации о файле перед скачиванием.

    Args:
        file_id: ID файла
        
    Returns:
        Метаданные файла
    """
    try:
        # Получаем текущего пользователя из контекста
        context = get_context()
        if not context:
            raise HTTPException(status_code=401, detail="Нет контекста пользователя")

        current_user = context.user

        # Определяем тип файла по префиксу
        if file_id.startswith("audio_"):
            # Это аудиофайл
            from core.files.processors import get_default_audio_processor
            audio_processor = await get_default_audio_processor()
            file_record = await audio_processor.get_audio_record(file_id)
            
            if not file_record:
                raise HTTPException(status_code=404, detail="Аудиофайл не найден")
        else:
            # Обычный файл
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

        # Базовая информация (одинаковая для всех типов)
        result = {
            "file_id": file_record.file_id,
            "original_name": file_record.original_name,
            "content_type": file_record.content_type,
            "file_size": file_record.file_size,
            "created_at": file_record.created_at,
            "tags": file_record.tags,
        }
        
        # Дополнительно для аудио
        if file_id.startswith("audio_"):
            result.update({
                "audio_id": file_record.audio_id,
                "duration": file_record.duration,
                "recognition_text": file_record.recognition_text,
                "recognition_confidence": file_record.recognition_confidence,
            })
        
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка получения информации о файле {file_id}: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")


# ============ АУДИО API ============

@router.post("/audio/upload", summary="Загрузить аудио")
async def upload_audio(file: UploadFile = File(...), auto_recognize: bool = True):
    """
    Загружает аудиофайл и опционально распознает речь.
    
    **Поддерживаемые форматы:**
    - MP3
    - WAV
    - OGG
    - M4A
    
    **Автоматическое распознавание:**
    Если auto_recognize=true (по умолчанию):
    - Речь распознается автоматически
    - Результат в поле recognition_text
    - Уверенность в recognition_confidence
    
    **Максимальный размер:** 50MB
    
    Args:
        file: Аудиофайл для загрузки
        auto_recognize: Автоматически распознать речь (по умолчанию true)
        
    Returns:
        audio_id, статус, распознанный текст (если auto_recognize=true)
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
        from core.files.processors import get_default_audio_processor
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


@router.post("/audio/{audio_id}/recognize", summary="Распознать речь")
async def recognize_audio(audio_id: str):
    """
    Запускает распознавание речи для уже загруженного аудио.
    
    Используйте если загрузили аудио с auto_recognize=false и теперь хотите распознать.
    
    **Результат:**
    - recognition_text - распознанный текст
    - recognition_confidence - уверенность (0-1)
    - recognition_qid - ID запроса для отладки
    
    Args:
        audio_id: ID аудиофайла
        
    Returns:
        Распознанный текст и метаданные
    """
    try:
        # Получаем текущего пользователя из контекста
        context = get_context()
        if not context:
            raise HTTPException(status_code=401, detail="Нет контекста пользователя")

        current_user = context.user

        from core.files.processors import get_default_audio_processor
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
