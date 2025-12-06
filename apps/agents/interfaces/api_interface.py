"""
API Interface - адаптер для REST API взаимодействия с флоу.
Обрабатывает HTTP запросы и преобразует их в унифицированные Message.
"""

import logging
import base64
import uuid
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone

from .base import BaseInterface, Message

logger = logging.getLogger(__name__)


class APIInterface(BaseInterface):
    """
    API интерфейс для REST взаимодействия с флоу.
    Поддерживает сессии, историю диалогов и файлы.
    """

    def __init__(self, platform_config: Dict[str, Any]):
        super().__init__(platform_config)
        self.platform_name = "api"

    async def handle_message(
        self, raw_data: Dict[str, Any], flow_id: str
    ) -> Optional[Message]:
        """
        Преобразует API запрос в Message.

        Ожидаемый формат raw_data:
        {
            "message": "текст сообщения",
            "role": "user",  # user, assistant, system
            "session_id": "optional_session_id",
            "user_id": "user_123",
            "files": [
                {
                    "name": "file.pdf",
                    "content": "base64_content",
                    "content_type": "application/pdf"
                }
            ],
            "history": [  # Опциональная история диалога
                {
                    "role": "user",
                    "message": "предыдущее сообщение",
                    "timestamp": "2025-09-12T10:00:00Z"
                }
            ]
        }
        """
        # Извлекаем основные поля
        message_text = raw_data.get("message", "")
        role = raw_data.get("role", "user")
        user_id = raw_data.get("user_id", "anonymous")
        provided_session_id = raw_data.get("session_id")

        # Если нет сообщения, пропускаем
        if not message_text:
            logger.warning("API запрос без сообщения")
            return None

        # Получаем или создаем сессию
        if provided_session_id:
            # Используем предоставленную сессию
            session_id = provided_session_id
            # Обновляем активность сессии если она существует
            await self._update_session_activity(session_id)
        else:
            # Создаем новую сессию
            session_id = await self.get_or_create_session(
                user_id=user_id, flow_id=flow_id, metadata={"api_request": True}
            )

        # Обрабатываем файлы если есть
        files_data = raw_data.get("files", [])
        audio_data = raw_data.get("audio", [])
        processed_files = []

        if files_data or audio_data:
            # Обрабатываем обычные файлы
            file_messages = []
            if files_data:
                file_messages = await self.process_files(files_data, user_id)
            
            # Обрабатываем аудиофайлы
            audio_messages = []
            if audio_data:
                audio_messages = await self.process_audio_files(audio_data, user_id)
            
            # Объединяем все сообщения
            all_messages = file_messages + audio_messages
            processed_files = all_messages

            # Добавляем информацию о файлах к сообщению
            if all_messages:
                files_text = "\n\n".join(all_messages)
                message_text = f"{message_text}\n\n{files_text}"

        # Обрабатываем историю диалога если есть
        history = raw_data.get("history", [])
        if history:
            # Добавляем историю к метаданным для агента
            history_text = self._format_history_for_agent(history)
            if history_text:
                message_text = f"{history_text}\n\n{message_text}"

        return Message(
            user_id=user_id,
            session_id=session_id,
            flow_id=flow_id,
            content=message_text,
            platform="api",
            metadata={
                "role": role,
                "api_request": True,
                "has_history": bool(history),
                "files_count": len(files_data),
            },
            files=processed_files,
        )

    async def send_message(self, message: Message):
        """
        API интерфейс не отправляет сообщения напрямую.
        Результаты получаются через polling задач.
        """
        logger.info(f"API сообщение готово для polling: {message.session_id}")

    async def send_typing_notification(self, session_id: str, is_typing: bool):
        """
        API интерфейс не поддерживает typing уведомления.
        Клиенты получают результаты через polling.
        """
        # Ничего не делаем для API
        pass

    async def _process_single_file(
        self, file_data: Dict[str, Any], user_id: str, file_processor
    ):
        """Обрабатывает один файл из API запроса"""
        # Декодируем base64 содержимое
        if "content" not in file_data:
            raise ValueError("Файл без содержимого в API запросе")

        file_content = base64.b64decode(file_data["content"])

        # Обрабатываем файл через процессор
        file_record = await file_processor.process_file_from_bytes(
            data=file_content,
            original_name=file_data.get("name", f"api_file_{uuid.uuid4().hex[:8]}"),
            content_type=file_data.get("content_type"),
            uploaded_by=user_id,
            metadata={"platform": "api", "api_upload": True},
            tags=["api", "upload"],
        )

        return file_record

    async def _process_single_audio_file(
        self, audio_data: Dict[str, Any], user_id: str, audio_processor
    ):
        """Обрабатывает один аудиофайл из API запроса"""
        # Декодируем base64 содержимое
        if "content" not in audio_data:
            raise ValueError("Аудиофайл без содержимого в API запросе")

        audio_content = base64.b64decode(audio_data["content"])

        # Определяем content_type
        content_type = audio_data.get("content_type", "audio/wav")
        if not content_type.startswith("audio/"):
            content_type = "audio/wav"

        # Обрабатываем аудиофайл через AudioProcessor с автоматическим распознаванием
        audio_record = await audio_processor.process_audio_from_bytes(
            data=audio_content,
            original_name=audio_data.get("name", f"api_audio_{uuid.uuid4().hex[:8]}.wav"),
            content_type=content_type,
            uploaded_by=user_id,
            auto_recognize=True,  # Автоматически распознаем речь
            metadata={"platform": "api", "api_upload": True},
            tags=["api", "upload", "audio"],
        )

        return audio_record

    def _format_history_for_agent(self, history: List[Dict[str, Any]]) -> str:
        """
        Форматирует историю диалога для агента.

        Args:
            history: Список сообщений истории

        Returns:
            Отформатированная история
        """
        if not history:
            return ""

        formatted_messages = []
        for msg in history:
            role = msg.get("role", "user")
            content = msg.get("message", "")

            if role == "user":
                formatted_messages.append(f"👤 Пользователь: {content}")
            elif role == "assistant":
                formatted_messages.append(f"🤖 Ассистент: {content}")
            elif role == "system":
                formatted_messages.append(f"⚙️ Система: {content}")
            else:
                formatted_messages.append(f"{role}: {content}")

        history_text = "\n".join(formatted_messages)
        return f"[ИСТОРИЯ ДИАЛОГА]\n{history_text}\n[/ИСТОРИЯ ДИАЛОГА]"

    async def _update_session_activity(self, session_id: str):
        """Обновляет время активности сессии"""
        session = await self.session_repository.get(session_id)
        
        if session:
            session.last_activity = datetime.now(timezone.utc)
            await self.session_repository.set(session)
            logger.debug(f"Обновлена активность сессии: {session_id}")


def get_api_interface() -> APIInterface:
    """Получает APIInterface (создается при первом обращении)"""
    return APIInterface({})
