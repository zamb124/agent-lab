"""
Процессор для обработки аудиофайлов из разных источников.
Сохраняет аудио в S3, создает записи в БД и автоматически распознает речь.
"""

import json
import re
import logging
import hashlib
import mimetypes
import uuid
from typing import Optional, Dict, Any, List
from pathlib import Path
import httpx

from .core_clients.s3_client import S3ClientFactory, get_default_s3_client
from .core_clients.cloud_voice_client import get_default_cloud_voice_client
from app.models import AudioRecord, FileStatus
from .config import settings
from app.core.container import get_container

logger = logging.getLogger(__name__)


class AudioProcessor:
    """
    Процессор для обработки аудиофайлов.
    Загружает аудио в S3, сохраняет метаданные в БД и распознает речь.
    """

    def __init__(self, bucket_name: Optional[str] = None):
        """
        Инициализация процессора.

        Args:
            bucket_name: Имя S3 бакета (если не указан, используется дефолтный)
        """
        self.bucket_name = bucket_name
        self.storage = get_container().storage
        self._s3_client = None
        self._voice_client = None

    async def _get_s3_client(self):
        """Получает S3 клиент"""
        if self._s3_client is None:
            if self.bucket_name:
                self._s3_client = S3ClientFactory.create_client_for_bucket(
                    self.bucket_name
                )
            else:
                self._s3_client = await get_default_s3_client()

            if not self._s3_client:
                raise ValueError("S3 клиент не настроен")

        return self._s3_client

    async def _get_voice_client(self):
        """Получает Cloud Voice клиент"""
        if self._voice_client is None:
            self._voice_client = await get_default_cloud_voice_client()
        return self._voice_client

    async def close(self):
        """Закрывает клиенты"""
        if self._s3_client:
            await self._s3_client.close()
            self._s3_client = None
        if self._voice_client:
            await self._voice_client.close()
            self._voice_client = None

    async def process_audio_from_bytes(
        self,
        data: bytes,
        original_name: str,
        content_type: str = "audio/wave",
        uploaded_by: Optional[str] = None,
        auto_recognize: bool = True,
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
        public: bool = True,
    ) -> AudioRecord:
        """
        Обрабатывает аудиофайл из данных в памяти.

        Args:
            data: Данные аудиофайла
            original_name: Оригинальное имя файла
            content_type: MIME тип аудио
            uploaded_by: ID пользователя
            auto_recognize: Автоматически распознавать речь
            metadata: Дополнительные метаданные
            tags: Теги аудиофайла
            public: Сделать файл публично доступным

        Returns:
            Запись об аудиофайле
        """
        logger.info(f"🎵 Начинаем обработку аудио: {original_name}, размер={len(data)} байт, content_type={content_type}, auto_recognize={auto_recognize}")
        
        # Генерируем уникальный ID аудиофайла
        audio_id = f"audio_{uuid.uuid4().hex[:12]}"

        # Определяем MIME тип если не указан
        if not content_type:
            content_type, _ = mimetypes.guess_type(original_name)
            if not content_type or not content_type.startswith('audio/'):
                content_type = "audio/wave"
        
        logger.info(f"🎵 Исходный content_type: {content_type}")
        
        # WebM не поддерживается Cloud Voice, отключаем распознавание
        if content_type.startswith('audio/webm'):
            logger.warning("⚠️ WebM формат не поддерживается Cloud Voice, распознавание отключено")
            logger.info("💡 Для распознавания речи используйте OGG/Opus или WAV форматы")
            auto_recognize = False
        
        logger.info(f"🎵 Финальный content_type: {content_type}")

        # Вычисляем MD5 хеш
        checksum = hashlib.md5(data).hexdigest()

        # Генерируем S3 ключ
        folder_uuid = str(uuid.uuid4())
        s3_key = f"audio/{folder_uuid}/{original_name}"

        # Получаем S3 клиент
        s3_client = await self._get_s3_client()

        # Создаем запись в БД (статус UPLOADING)
        audio_record = AudioRecord(
            file_id=audio_id,
            provider=s3_client.provider_name,
            original_name=original_name,
            s3_key=s3_key,
            s3_bucket=s3_client.bucket_name,
            s3_endpoint=s3_client.endpoint_url,
            content_type=content_type,
            file_size=len(data),
            checksum=checksum,
            status=FileStatus.UPLOADING,
            uploaded_by=uploaded_by,
            metadata=metadata or {},
            tags=tags or [],
        )

        # Сохраняем запись в БД
        await self.storage.set(audio_record.key, audio_record.model_dump_json())
        logger.info(f"📝 Создана запись об аудио в БД: {audio_record.key}")

        # Подготавливаем метаданные для S3
        s3_metadata = {
            "audio_id": audio_id,
            "original_name": original_name,
            "uploaded_by": uploaded_by or "unknown",
            "content_type": content_type,
        }

        # Добавляем пользовательские метаданные
        if metadata:
            for k, v in metadata.items():
                s3_metadata[k] = str(v)

        # Загружаем аудиофайл в S3
        await s3_client.upload_bytes(
            data=data,
            key=s3_key,
            content_type=content_type,
            metadata=s3_metadata,
            acl="public-read" if public else None,
        )

        # Обновляем статус на UPLOADED
        audio_record.status = FileStatus.UPLOADED
        logger.info(f"✅ Аудиофайл загружен в S3: {s3_key}")

        # Сохраняем обновленный статус
        await self.storage.set(audio_record.key, audio_record.model_dump_json())

        # Автоматическое распознавание речи
        if auto_recognize:
            await self._recognize_audio_async(audio_record, data)

        return audio_record

    async def process_audio_from_url(
        self,
        audio_url: str,
        original_name: Optional[str] = None,
        content_type: Optional[str] = None,
        uploaded_by: Optional[str] = None,
        auto_recognize: bool = True,
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
        public: bool = True,
    ) -> AudioRecord:
        """
        Обрабатывает аудиофайл по URL (например, из Telegram).

        Args:
            audio_url: URL аудиофайла для скачивания
            original_name: Оригинальное имя файла
            content_type: MIME тип аудио
            uploaded_by: ID пользователя
            auto_recognize: Автоматически распознавать речь
            metadata: Дополнительные метаданные
            tags: Теги аудиофайла

        Returns:
            Запись об аудиофайле
        """
        # Скачиваем аудиофайл по URL
        async with httpx.AsyncClient() as client:
            response = await client.get(audio_url)

            if response.status_code != 200:
                raise ValueError(
                    f"Не удалось скачать аудиофайл по URL: {response.status_code}"
                )

            data = response.content

            # Определяем имя файла если не указано
            if not original_name:
                original_name = Path(audio_url).name
                if not original_name or "." not in original_name:
                    original_name = f"audio_{uuid.uuid4().hex[:8]}.ogg"

            # Используем переданный content_type или определяем автоматически
            if not content_type:
                # Определяем content_type из ответа или по расширению
                content_type = response.headers.get("content-type")
                if not content_type or not content_type.startswith('audio/'):
                    # Пытаемся определить по расширению
                    content_type, _ = mimetypes.guess_type(original_name)
                    if not content_type:
                        content_type = "audio/ogg"

            return await self.process_audio_from_bytes(
                data=data,
                original_name=original_name,
                content_type=content_type,
                uploaded_by=uploaded_by,
                auto_recognize=auto_recognize,
                metadata=metadata,
                tags=tags,
                public=public,
            )

    async def _recognize_audio_async(self, audio_record: AudioRecord, audio_data: bytes):
        """
        Асинхронно распознает речь в аудиофайле.

        Args:
            audio_record: Запись об аудиофайле
            audio_data: Данные аудиофайла
        """
        logger.info(f"🎤 Начинаем распознавание для {audio_record.audio_id}")
        try:
            # Обновляем статус на UPLOADED
            audio_record.status = FileStatus.UPLOADED
            await self.storage.set(audio_record.key, audio_record.model_dump_json())
            
            voice_client = await self._get_voice_client()
            if not voice_client:
                logger.warning(f"Cloud Voice не настроен, пропускаем распознавание для {audio_record.audio_id}")
                return

            # Cloud Voice поддерживает только: audio/wave и audio/ogg; codecs=opus
            content_type_for_api = audio_record.content_type
            
            # Нормализуем content_type для Cloud Voice
            if content_type_for_api.startswith('audio/wav'):
                content_type_for_api = 'audio/wave'
            elif content_type_for_api.startswith('audio/ogg'):
                # Для OGG обязательно нужен параметр codecs=opus
                if 'codecs=opus' not in content_type_for_api:
                    content_type_for_api = 'audio/ogg; codecs=opus'
            else:
                # Неподдерживаемый формат
                logger.warning(f"⚠️ Формат {audio_record.content_type} не поддерживается Cloud Voice для распознавания.")
                logger.info("💡 Поддерживаемые форматы: audio/wave, audio/ogg; codecs=opus")
                return

            # Логируем что отправляем
            logger.info(f"🎵 Отправляем в Cloud Voice: content_type='{content_type_for_api}', размер={len(audio_data)} байт")
            
            # Проверяем первые байты файла для диагностики
            header = audio_data[:20] if len(audio_data) >= 20 else audio_data
            logger.info(f"🔍 Первые байты файла: {header.hex()}")
            logger.info(f"🔍 Первые символы: {header[:4]}")

            # Распознаем речь
            result = await voice_client.recognize_audio_file(audio_data, content_type_for_api)
            
            # Извлекаем лучший результат
            recognition_text = voice_client.get_best_recognition_text(result)
            
            # Получаем уверенность и QID
            confidence = None
            qid = result.get("qid")
            
            # Для файлового распознавания уверенность в первом результате
            result_data = result.get("result", {})
            texts = result_data.get("texts", [])
            if texts:
                confidence = texts[0].get("confidence")

            # Обновляем запись с результатами
            audio_record.recognition_text = recognition_text
            audio_record.recognition_confidence = confidence
            audio_record.recognition_qid = qid
            audio_record.status = FileStatus.UPLOADED

            await self.storage.set(audio_record.key, audio_record.model_dump_json())
            
            logger.info(f"✅ Речь успешно распознана для {audio_record.audio_id}")
            logger.info(f"📝 Распознанный текст: '{recognition_text}'")
            logger.info(f"🎯 Уверенность: {confidence}")

        except Exception as e:
            logger.error(f"❌ Ошибка распознавания речи для {audio_record.audio_id}: {e}")
            
            # Обновляем статус на FAILED
            audio_record.status = FileStatus.FAILED
            audio_record.metadata["recognition_error"] = str(e)
            await self.storage.set(audio_record.key, audio_record.model_dump_json())

    async def recognize_audio(self, audio_id: str) -> bool:
        """
        Распознает речь в уже загруженном аудиофайле.
        
        Args:
            audio_id: ID аудиофайла
            
        Returns:
            True если распознавание успешно
        """
        # Получаем запись об аудиофайле
        audio_record = await self.get_audio_record(audio_id)
        if not audio_record:
            logger.error(f"Аудиофайл {audio_id} не найден в БД")
            return False

        try:
            # Скачиваем аудиофайл из S3
            s3_client = await self._get_s3_client()
            audio_data = await s3_client.download_bytes(audio_record.s3_key)
            
            if not audio_data:
                logger.error(f"Не удалось скачать аудиофайл {audio_id} из S3")
                return False

            # Распознаем речь
            await self._recognize_audio_async(audio_record, audio_data)
            return audio_record.status == FileStatus.UPLOADED

        except Exception as e:
            logger.error(f"❌ Ошибка принудительного распознавания {audio_id}: {e}")
            return False

    async def get_audio_record(
        self, audio_id: str, provider: Optional[str] = None
    ) -> Optional[AudioRecord]:
        """
        Получает запись об аудиофайле из БД.

        Args:
            audio_id: ID аудиофайла
            provider: Провайдер (если не указан, ищем по всем)

        Returns:
            Запись об аудиофайле или None
        """
        if provider:
            # Поиск по конкретному провайдеру
            key = f"audio:{provider}:{audio_id}"
            data = await self.storage.get(key)

            if data:
                return AudioRecord(**json.loads(data))
        else:
            # Поиск по всем провайдерам
            for bucket_name, bucket_config in settings.s3.buckets.items():
                if bucket_config.enabled:
                    key = f"audio:{bucket_config.provider}:{audio_id}"
                    data = await self.storage.get(key)

                    if data:
                        return AudioRecord(**json.loads(data))

        return None

    async def delete_audio(self, audio_id: str, provider: Optional[str] = None) -> bool:
        """
        Удаляет аудиофайл из S3 и обновляет запись в БД.

        Args:
            audio_id: ID аудиофайла
            provider: Провайдер (если не указан, ищем по всем)

        Returns:
            True если удаление успешно
        """
        # Получаем запись об аудиофайле
        audio_record = await self.get_audio_record(audio_id, provider)
        if not audio_record:
            logger.warning(f"Аудиофайл {audio_id} не найден в БД")
            return False

        try:
            # Создаем S3 клиент для этого файла
            s3_client = S3ClientFactory.create_client_for_bucket(audio_record.s3_bucket)

            # Удаляем из S3
            delete_success = await s3_client.delete_object(audio_record.s3_key)

            if delete_success:
                # Обновляем статус в БД
                audio_record.status = FileStatus.DELETED
                await self.storage.set(audio_record.key, audio_record.model_dump_json())
                logger.info(f"✅ Аудиофайл удален: {audio_id}")
                return True
            else:
                logger.error(f"❌ Не удалось удалить аудиофайл из S3: {audio_id}")
                return False

        except Exception as e:
            logger.error(f"❌ Ошибка удаления аудиофайла {audio_id}: {e}")
            return False
        finally:
            if "s3_client" in locals():
                await s3_client.close()

    def format_audio_message(self, audio_record: AudioRecord) -> str:
        """
        Форматирует сообщение об аудиофайле для агента.

        Args:
            audio_record: Запись об аудиофайле

        Returns:
            Отформатированное сообщение
        """
        size_kb = audio_record.file_size / 1024
        size_str = (
            f"{size_kb:.1f} KB" if size_kb >= 1 else f"{audio_record.file_size} байт"
        )

        # Формат такой же как у file_processor
        message = f"🎵 Аудио: {audio_record.original_name} (ID: {audio_record.audio_id}, [Скачать]({audio_record.url}), Тип: {audio_record.content_type}, Размер: {size_str}"
        
        # Добавляем длительность если есть
        if audio_record.duration:
            message += f", Длительность: {audio_record.duration:.1f} сек"
        
        message += ")"

        # Добавляем распознанный текст если есть
        if audio_record.recognition_text:
            confidence_info = ""
            if audio_record.recognition_confidence:
                confidence_info = f" (уверенность: {audio_record.recognition_confidence:.2f})"
            
            message += f"\n📝 Распознанный текст: \"{audio_record.recognition_text}\"{confidence_info}"
        elif audio_record.status == FileStatus.UPLOADING:
            message += "\n⏳ Загрузка..."
        elif audio_record.status == FileStatus.FAILED:
            error_detail = audio_record.metadata.get("recognition_error", "Неизвестная ошибка")
            message += f"\n❌ Ошибка распознавания: {error_detail}"
        elif not audio_record.recognition_text and audio_record.content_type.startswith('audio/webm'):
            message += "\n⚠️ Формат WebM не поддерживается для распознавания речи"
        
        return message

    @staticmethod
    def extract_audio_info_from_message(message: str) -> List[Dict[str, Any]]:
        """
        Извлекает информацию об аудиофайлах из сообщения агента.

        Args:
            message: Сообщение которое может содержать аудио

        Returns:
            Список словарей с информацией об аудиофайлах
        """
        audios = []
        
        # Паттерн для полного формата: [AUDIO]...ID: audio_id...[/AUDIO]
        full_pattern = r"\[AUDIO\].*?ID:\s*([a-zA-Z0-9_]+).*?\[/AUDIO\]"
        
        # Паттерн для упрощенного формата: [AUDIO]audio_id[/AUDIO]
        simple_pattern = r"\[AUDIO\]([a-zA-Z0-9_]+)\[/AUDIO\]"
        
        # Сначала ищем полный формат
        for match in re.finditer(full_pattern, message, re.DOTALL):
            audio_id = match.group(1).strip()
            audio_info = {
                "name": f"audio_{audio_id[:8]}.ogg",
                "audio_id": audio_id,
                "url": f"/api/v1/files/download/audio/{audio_id}",
                "content_type": "audio/ogg; codecs=opus",
                "size": "unknown",
            }
            audios.append(audio_info)
        
        # Если не нашли полный формат, ищем упрощенный
        if not audios:
            for match in re.finditer(simple_pattern, message):
                audio_id = match.group(1).strip()
                audio_info = {
                    "name": f"audio_{audio_id[:8]}.ogg",
                    "audio_id": audio_id,
                    "url": f"/api/v1/files/download/audio/{audio_id}",
                    "content_type": "audio/ogg; codecs=opus",
                    "size": "unknown",
                }
                audios.append(audio_info)

        return audios


# Глобальный экземпляр процессора
_default_audio_processor: Optional[AudioProcessor] = None


async def get_default_audio_processor() -> AudioProcessor:
    """Получает дефолтный аудио процессор"""
    global _default_audio_processor

    if _default_audio_processor is None:
        _default_audio_processor = AudioProcessor()

    return _default_audio_processor


async def close_default_audio_processor():
    """Закрывает дефолтный аудио процессор"""
    global _default_audio_processor

    if _default_audio_processor:
        await _default_audio_processor.close()
        _default_audio_processor = None
