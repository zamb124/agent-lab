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
from ..core.models import FileRecord, FileStatus

logger = logging.getLogger(__name__)


class APIInterface(BaseInterface):
    """
    API интерфейс для REST взаимодействия с флоу.
    Поддерживает сессии, историю диалогов и файлы.
    """
    
    def __init__(self, platform_config: Dict[str, Any]):
        super().__init__(platform_config)
        self.platform_name = "api"
    
    async def handle_message(self, raw_data: Dict[str, Any], flow_id: str) -> Optional[Message]:
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
                user_id=user_id,
                flow_id=flow_id,
                metadata={"api_request": True}
            )
        
        # Обрабатываем файлы если есть
        files_data = raw_data.get("files", [])
        processed_files = []
        
        if files_data:
            file_messages = await self.process_files(files_data, user_id)
            processed_files = file_messages
            
            # Добавляем информацию о файлах к сообщению
            if file_messages:
                files_text = "\n\n".join(file_messages)
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
                "files_count": len(files_data)
            },
            files=processed_files
        )
    
    async def send_message(self, message: Message):
        """
        API интерфейс не отправляет сообщения напрямую.
        Результаты получаются через polling задач.
        """
        logger.info(f"API сообщение готово для polling: {message.session_id}")
    
    async def _process_single_file(self, file_data: Dict[str, Any], user_id: str, file_processor):
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
            metadata={
                "platform": "api",
                "api_upload": True
            },
            tags=["api", "upload"]
        )
        
        return file_record
    
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
            timestamp = msg.get("timestamp", "")
            
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
        try:
            # Попытаемся найти и обновить сессию
            # Формат session_id может быть разным, попробуем несколько вариантов
            session_keys = [
                f"session:api:{session_id}",
                session_id  # Если передали полный ключ
            ]
            
            for session_key in session_keys:
                session_data = await self.storage.get(session_key)
                if session_data:
                    import json
                    session_info = json.loads(session_data)
                    session_info["last_activity"] = datetime.now(timezone.utc).isoformat()
                    await self.storage.set(session_key, json.dumps(session_info))
                    logger.info(f"🔄 Обновлена активность сессии: {session_key}")
                    return
            
            logger.warning(f"Сессия {session_id} не найдена для обновления активности")
            
        except Exception as e:
            logger.error(f"Ошибка обновления активности сессии {session_id}: {e}")


# Глобальный экземпляр для использования в API
api_interface = APIInterface({})
