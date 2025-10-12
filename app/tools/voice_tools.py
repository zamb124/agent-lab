"""
Инструменты для работы с Cloud Voice API и аудиофайлами.
Распознавание речи, синтез речи и работа с загруженными аудиофайлами.
"""

import logging
import uuid
from pathlib import Path
from langchain_core.tools import tool

from ..core.core_clients import get_default_cloud_voice_client
from ..core.audio_processor import get_default_audio_processor

logger = logging.getLogger(__name__)


@tool
async def recognize_speech_from_file(
    file_path: str, 
    content_type: str = "audio/wave"
) -> str:
    """
    Распознает речь из аудиофайла.
    
    Args:
        file_path: Путь к аудиофайлу
        content_type: MIME тип аудио (audio/wave или audio/ogg)
        
    Returns:
        Распознанный текст
    """
    try:
        client = await get_default_cloud_voice_client()
        if not client:
            return "❌ Cloud Voice не настроен"
            
        result = await client.recognize_audio_file_from_path(file_path, content_type)
        text = client.get_best_recognition_text(result)
        
        if text:
            logger.info(f"✅ Распознана речь из {file_path}: {text[:50]}...")
            return f"Распознанный текст: {text}"
        else:
            return "❌ Не удалось распознать речь в аудиофайле"
            
    except FileNotFoundError:
        return f"❌ Аудиофайл не найден: {file_path}"
    except Exception as e:
        logger.error(f"❌ Ошибка распознавания речи: {e}")
        return f"❌ Ошибка распознавания речи: {str(e)}"


@tool
async def recognize_speech_from_bytes(
    audio_data_hex: str, 
    content_type: str = "audio/wave"
) -> str:
    """
    Распознает речь из аудиоданных в hex формате.
    
    Args:
        audio_data_hex: Аудиоданные в hex формате
        content_type: MIME тип аудио
        
    Returns:
        Распознанный текст
    """
    try:
        # Конвертируем hex в bytes
        audio_data = bytes.fromhex(audio_data_hex)
        
        client = await get_default_cloud_voice_client()
        if not client:
            return "❌ Cloud Voice не настроен"
            
        result = await client.recognize_audio_file(audio_data, content_type)
        text = client.get_best_recognition_text(result)
        
        if text:
            logger.info(f"✅ Распознана речь из данных: {text[:50]}...")
            return f"Распознанный текст: {text}"
        else:
            return "❌ Не удалось распознать речь в аудиоданных"
            
    except ValueError as e:
        return f"❌ Неверный hex формат: {str(e)}"
    except Exception as e:
        logger.error(f"❌ Ошибка распознавания речи: {e}")
        return f"❌ Ошибка распознавания речи: {str(e)}"


@tool
async def synthesize_speech(
    text: str,
    model_name: str = "katherine",
    encoder: str = "opus",
    tempo: float = 1.0
) -> str:
    """
    Синтезирует речь из текста и сохраняет в системе.
    
    Args:
        text: Текст для синтеза
        model_name: Модель голоса (katherine, maria, pavel)
        encoder: Тип энкодера (pcm, mp3, opus)
        tempo: Скорость речи (0.75 - 1.75)
        
    Returns:
        Форматированное сообщение с информацией об аудио и ссылкой для скачивания
    """
    try:
        client = await get_default_cloud_voice_client()
        if not client:
            return "❌ Cloud Voice не настроен"
            
        # Синтезируем речь
        audio_data = await client.synthesize_speech(text, model_name, encoder, tempo)
        
        if not audio_data:
            return "❌ Не удалось синтезировать речь"
        
        # Определяем content_type на основе encoder
        content_type_map = {
            "mp3": "audio/mpeg",
            "opus": "audio/ogg; codecs=opus", 
            "pcm": "audio/wav"
        }
        content_type = content_type_map.get(encoder, "audio/mpeg")
        
        # Определяем расширение файла
        extension_map = {
            "mp3": "mp3",
            "opus": "ogg",
            "pcm": "wav"
        }
        extension = extension_map.get(encoder, "mp3")
        
        # Сохраняем через AudioProcessor
        audio_processor = await get_default_audio_processor()
        audio_record = await audio_processor.process_audio_from_bytes(
            data=audio_data,
            original_name=f"synthesized_speech_{uuid.uuid4().hex[:8]}.{extension}",
            content_type=content_type,
            auto_recognize=False,  # Не нужно распознавать синтезированную речь
            metadata={
                "synthesized": True,
                "text_length": len(text),  # Длина текста вместо самого текста
                "voice_model": model_name,
                "encoder": encoder,
                "tempo": str(tempo),
            },
            tags=["synthesized", "speech", model_name]
        )
        
        # Возвращаем форматированное сообщение через audio_processor
        return audio_processor.format_audio_message(audio_record)
            
    except ValueError as e:
        return f"❌ Неверные параметры: {str(e)}"
    except Exception as e:
        logger.error(f"❌ Ошибка синтеза речи: {e}")
        return f"❌ Ошибка синтеза речи: {str(e)}"


@tool
async def synthesize_speech_to_file(
    text: str,
    output_path: str,
    model_name: str = "katherine", 
    encoder: str = "mp3",
    tempo: float = 1.0
) -> str:
    """
    Синтезирует речь и сохраняет в файл.
    
    Args:
        text: Текст для синтеза
        output_path: Путь для сохранения аудиофайла
        model_name: Модель голоса
        encoder: Тип энкодера
        tempo: Скорость речи
        
    Returns:
        Результат операции
    """
    try:
        client = await get_default_cloud_voice_client()
        if not client:
            return "❌ Cloud Voice не настроен"
            
        audio_data = await client.synthesize_speech(text, model_name, encoder, tempo)
        
        # Сохраняем в файл
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, "wb") as f:
            f.write(audio_data)
            
        logger.info(f"✅ Речь синтезирована и сохранена в {output_path}")
        return f"✅ Речь синтезирована и сохранена в {output_path} ({len(audio_data)} байт, модель: {model_name})"
        
    except ValueError as e:
        return f"❌ Неверные параметры: {str(e)}"
    except Exception as e:
        logger.error(f"❌ Ошибка синтеза речи: {e}")
        return f"❌ Ошибка синтеза речи: {str(e)}"


@tool
async def create_speech_recognition_stream() -> str:
    """
    Создает задачу для потокового распознавания речи.
    
    Returns:
        task_id и task_token для потокового распознавания
    """
    try:
        client = await get_default_cloud_voice_client()
        if not client:
            return "❌ Cloud Voice не настроен"
            
        task_info = await client.create_stream_task()
        
        logger.info(f"✅ Создана задача потокового распознавания: {task_info['task_id']}")
        return f"✅ Задача создана:\nTask ID: {task_info['task_id']}\nTask Token: {task_info['task_token']}"
        
    except Exception as e:
        logger.error(f"❌ Ошибка создания задачи потокового распознавания: {e}")
        return f"❌ Ошибка создания задачи: {str(e)}"


@tool
async def add_audio_chunk_to_stream(
    task_id: str,
    task_token: str,
    chunk_num: int,
    chunk_data_hex: str,
    content_type: str = "audio/wave"
) -> str:
    """
    Добавляет аудио чанк к потоковому распознаванию.
    
    Args:
        task_id: ID задачи
        task_token: Токен задачи
        chunk_num: Номер чанка (начиная с 1)
        chunk_data_hex: Данные чанка в hex формате
        content_type: MIME тип аудио
        
    Returns:
        Промежуточный результат распознавания
    """
    try:
        # Конвертируем hex в bytes
        chunk_data = bytes.fromhex(chunk_data_hex)
        
        client = await get_default_cloud_voice_client()
        if not client:
            return "❌ Cloud Voice не настроен"
            
        result = await client.add_audio_chunk(task_id, task_token, chunk_num, chunk_data, content_type)
        text = client.get_best_recognition_text(result)
        
        logger.info(f"✅ Чанк {chunk_num} обработан для задачи {task_id}")
        return f"✅ Чанк {chunk_num} обработан.\nТекущий результат: {text}"
        
    except ValueError as e:
        return f"❌ Неверный hex формат: {str(e)}"
    except Exception as e:
        logger.error(f"❌ Ошибка обработки чанка: {e}")
        return f"❌ Ошибка обработки чанка: {str(e)}"


@tool
async def get_stream_recognition_result(task_id: str, task_token: str) -> str:
    """
    Получает финальный результат потокового распознавания.
    
    Args:
        task_id: ID задачи
        task_token: Токен задачи
        
    Returns:
        Финальный результат распознавания
    """
    try:
        client = await get_default_cloud_voice_client()
        if not client:
            return "❌ Cloud Voice не настроен"
            
        result = await client.get_stream_result(task_id, task_token)
        text = client.get_best_recognition_text(result)
        status = result.get("result", {}).get("status", "unknown")
        
        logger.info(f"✅ Получен финальный результат для задачи {task_id}")
        return f"✅ Финальный результат (статус: {status}):\n{text}"
        
    except Exception as e:
        logger.error(f"❌ Ошибка получения результата: {e}")
        return f"❌ Ошибка получения результата: {str(e)}"


@tool
async def get_audio_transcript(audio_id: str) -> str:
    """
    Получает распознанный текст из загруженного аудиофайла по ID.
    
    Args:
        audio_id: ID аудиофайла в системе
        
    Returns:
        Распознанный текст или информация о статусе
    """
    try:
        audio_processor = await get_default_audio_processor()
        audio_record = await audio_processor.get_audio_record(audio_id)
        
        if not audio_record:
            return f"❌ Аудиофайл с ID {audio_id} не найден"
            
        if audio_record.recognition_text:
            confidence_info = ""
            if audio_record.recognition_confidence:
                confidence_info = f" (уверенность: {audio_record.recognition_confidence:.2f})"
            return f"✅ Распознанный текст: \"{audio_record.recognition_text}\"{confidence_info}"
        elif audio_record.status.value == "processing":
            return "⏳ Распознавание речи в процессе..."
        elif audio_record.status.value == "error":
            return "❌ Ошибка распознавания речи"
        else:
            return "❌ Речь еще не распознана"
            
    except Exception as e:
        logger.error(f"❌ Ошибка получения транскрипта: {e}")
        return f"❌ Ошибка получения транскрипта: {str(e)}"


@tool
async def recognize_uploaded_audio(audio_id: str) -> str:
    """
    Запускает распознавание речи для загруженного аудиофайла.
    
    Args:
        audio_id: ID аудиофайла в системе
        
    Returns:
        Результат операции распознавания
    """
    try:
        audio_processor = await get_default_audio_processor()
        success = await audio_processor.recognize_audio(audio_id)
        
        if success:
            # Получаем обновленную запись
            audio_record = await audio_processor.get_audio_record(audio_id)
            if audio_record and audio_record.recognition_text:
                return f"✅ Распознавание завершено: \"{audio_record.recognition_text}\""
            else:
                return "✅ Распознавание завершено, но текст не получен"
        else:
            return f"❌ Не удалось распознать речь в аудиофайле {audio_id}"
            
    except Exception as e:
        logger.error(f"❌ Ошибка распознавания аудио: {e}")
        return f"❌ Ошибка распознавания аудио: {str(e)}"


@tool
async def get_audio_info(audio_id: str) -> str:
    """
    Получает подробную информацию об аудиофайле.
    
    Args:
        audio_id: ID аудиофайла в системе
        
    Returns:
        Подробная информация об аудиофайле
    """
    try:
        audio_processor = await get_default_audio_processor()
        audio_record = await audio_processor.get_audio_record(audio_id)
        
        if not audio_record:
            return f"❌ Аудиофайл с ID {audio_id} не найден"
            
        return audio_processor.format_audio_message(audio_record)
        
    except Exception as e:
        logger.error(f"❌ Ошибка получения информации об аудио: {e}")
        return f"❌ Ошибка получения информации об аудио: {str(e)}"


@tool
async def download_audio_file(audio_id: str, output_path: str) -> str:
    """
    Скачивает аудиофайл из системы в указанное место.
    
    Args:
        audio_id: ID аудиофайла в системе
        output_path: Путь для сохранения файла
        
    Returns:
        Результат операции скачивания
    """
    try:
        audio_processor = await get_default_audio_processor()
        audio_record = await audio_processor.get_audio_record(audio_id)
        
        if not audio_record:
            return f"❌ Аудиофайл с ID {audio_id} не найден"
            
        # Получаем S3 клиент и скачиваем файл
        s3_client = await audio_processor._get_s3_client()
        success = await s3_client.download_file(audio_record.s3_key, output_path)
        
        if success:
            return f"✅ Аудиофайл скачан: {output_path}"
        else:
            return f"❌ Не удалось скачать аудиофайл {audio_id}"
            
    except Exception as e:
        logger.error(f"❌ Ошибка скачивания аудиофайла: {e}")
        return f"❌ Ошибка скачивания аудиофайла: {str(e)}"


@tool
async def upload_audio_file(file_path: str, auto_recognize: bool = True) -> str:
    """
    Загружает аудиофайл в систему из локального пути.
    
    Args:
        file_path: Путь к аудиофайлу
        auto_recognize: Автоматически распознавать речь
        
    Returns:
        Информация о загруженном аудиофайле
    """
    try:
        file_path = Path(file_path)
        if not file_path.exists():
            return f"❌ Аудиофайл не найден: {file_path}"
            
        # Читаем файл
        with open(file_path, "rb") as f:
            audio_data = f.read()
            
        # Определяем MIME тип
        import mimetypes
        content_type, _ = mimetypes.guess_type(str(file_path))
        if not content_type or not content_type.startswith('audio/'):
            content_type = "audio/wave"
            
        # Обрабатываем через AudioProcessor
        audio_processor = await get_default_audio_processor()
        audio_record = await audio_processor.process_audio_from_bytes(
            data=audio_data,
            original_name=file_path.name,
            content_type=content_type,
            auto_recognize=auto_recognize
        )
        
        return audio_processor.format_audio_message(audio_record)
        
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки аудиофайла: {e}")
        return f"❌ Ошибка загрузки аудиофайла: {str(e)}"


# Список доступных инструментов для экспорта
VOICE_TOOLS = [
    # Только синтез речи для агентов
    synthesize_speech,
    synthesize_speech_to_file,
]
