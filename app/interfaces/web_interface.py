"""
Web Interface - адаптер для веб-чата.
Работает в многоинстансной архитектуре через БД уведомления.
"""

import base64
import uuid
import logging
import json
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from app.interfaces.base import BaseInterface, Message
from app.core.context import get_context

logger = logging.getLogger(__name__)


class WebInterface(BaseInterface):
    """
    Веб-интерфейс для чата в многоинстансной архитектуре.

    Принцип работы:
    1. Сообщение создает задачу в БД
    2. Воркер (любой инстанс) обрабатывает задачу
    3. Результат сохраняется как уведомление в БД
    4. WebSocket polling читает уведомления и отправляет клиенту
    """

    def __init__(self, platform_config: Dict[str, Any]):
        super().__init__(platform_config)
        self.platform_name = "web"

    def set_websocket_manager(self, websocket_manager):
        """Устанавливает WebSocket менеджер для отправки сообщений"""
        self.websocket_manager = websocket_manager

    async def handle_message(
        self, raw_data: Dict[str, Any], flow_id: str
    ) -> Optional[Message]:
        """
        Преобразует данные веб-чата в Message.

        Ожидаемый формат raw_data:
        {
            "message": "текст сообщения",
            "agent_id": "weather_agent",
            "session_id": "session_123",
            "user_id": "user_456"
        }
        """
        message_text = raw_data.get("message", "")
        agent_id = raw_data.get("agent_id")
        js_session_id = raw_data.get("session_id")  # Может быть UUID или полный session_id
        user_id = raw_data.get("user_id", "web_user")
        files_data = raw_data.get("files", [])

        # Формируем правильный session_id
        context = get_context()
        real_user_id = context.user.user_id if context else user_id
        
        # Получаем email пользователя (если доступен в контексте)
        user_email = context.user.email if context and hasattr(context.user, 'email') else None
        
        # Проверяем доступ пользователя
        is_allowed, error_message = self.check_user_access(real_user_id, user_email)
        if not is_allowed:
            logger.warning(f"🚫 Доступ запрещен для пользователя {real_user_id} ({user_email}) в flow {flow_id}")
            
            # Формируем временный session_id для ошибки
            temp_session_id = f"web:{real_user_id}:{flow_id}:{uuid.uuid4().hex[:8]}"
            
            access_denied_message = Message(
                user_id=real_user_id,
                session_id=temp_session_id,
                content=error_message,
                flow_id=flow_id,
                platform="web",
                metadata={
                    "web_chat": True,
                    "is_access_denied": True,
                },
            )
            await self.send_message(access_denied_message)
            return None
        
        # Проверяем: если session_id уже полный с префиксом web:, используем как есть
        if js_session_id and js_session_id.startswith('web:'):
            session_id = js_session_id
            logger.debug(f"✅ Используем полный session_id: {session_id}")
        elif js_session_id and (js_session_id.startswith('telegram:') or js_session_id.startswith('whatsapp:') or js_session_id.startswith('api:')):
            # Игнорируем session_id от других платформ - создаем новый для web
            logger.warning(f"⚠️ Получен session_id от другой платформы: {js_session_id[:50]}, создаем новый для web")
            session_id = f"web:{real_user_id}:{flow_id}:{uuid.uuid4().hex[:8]}"
            logger.debug(f"🔧 Создан новый session_id для web: {session_id}")
        else:
            # Формируем полный session_id: web:user_id:flow_id:uuid
            session_id = f"web:{real_user_id}:{flow_id}:{js_session_id}"
            logger.debug(f"🔧 Сформирован session_id: {session_id}")

        # Если нет ни текста, ни файлов - пропускаем
        if not message_text and not files_data:
            return None

        # Проверяем команды (только если есть текст)
        if message_text:
            is_command, command_response = await self.process_command(
                message_text, user_id, flow_id
            )
            if is_command:
                # Отправляем ответ на команду напрямую
                if command_response:
                    command_message = Message(
                        user_id=user_id,
                        session_id=session_id,  # Используем ту же сессию что и у пользователя
                        content=command_response,
                        flow_id=flow_id,
                        platform="web",
                        metadata={
                            "web_chat": True,
                            "is_command_response": True,
                            "command": message_text,  # Сохраняем саму команду
                            "agent_id": agent_id,
                        },
                    )
                    await self.send_message(command_message)
                return None  # Не создаем задачу для команд

        # Обрабатываем файлы если есть
        processed_files = []
        if files_data:
            # Разделяем аудиофайлы и обычные файлы
            audio_files = [f for f in files_data if f.get("content_type", "").startswith("audio/")]
            regular_files = [f for f in files_data if not f.get("content_type", "").startswith("audio/")]
            
            # Обрабатываем обычные файлы
            file_messages = []
            if regular_files:
                file_messages = await self.process_files(regular_files, user_id)
            
            # Обрабатываем аудиофайлы
            audio_messages = []
            if audio_files:
                audio_messages = await self.process_audio_files(audio_files, user_id)
            
            # Объединяем все сообщения
            all_messages = file_messages + audio_messages
            processed_files = all_messages

            if all_messages:
                # Добавляем информацию о файлах к тексту сообщения
                files_text = "\n\n".join(all_messages)
                if message_text:
                    message_text = f"{message_text}\n\n{files_text}"
                else:
                    message_text = files_text

        # СНАЧАЛА отправляем пользовательское сообщение в чат
        user_message = Message(
            user_id=user_id,
            session_id=session_id,
            flow_id=flow_id,
            content=message_text,
            platform="web",
            files=processed_files if processed_files else None,
            metadata={
                "agent_id": agent_id,
                "web_chat": True,
                "is_user_message": True,
                "files_count": len(files_data) if files_data else 0,
            },
        )
        await self.send_message(user_message)

        return Message(
            user_id=user_id,
            session_id=session_id,
            flow_id=flow_id,
            content=message_text,
            platform="web",
            files=processed_files if processed_files else None,
            metadata={
                "agent_id": agent_id,
                "web_chat": True,
                "files_count": len(files_data) if files_data else 0,
            },
        )

    async def send_message(self, message: Message):
        """
        Сохраняет сообщение как уведомление в БД для многоинстансной архитектуры.
        WebSocket polling на нужном инстансе подхватит и отправит клиенту.
        """
        is_user_message = message.metadata.get("is_user_message", False)

        if is_user_message:
            # Пользовательское сообщение
            notification = {
                "type": "USER_MESSAGE",
                "content": message.content,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "message_id": f"user_{datetime.now(timezone.utc).timestamp()}",
                "user_id": message.user_id,
            }
        else:
            # Сообщение от агента или команды
            is_command_response = message.metadata.get("is_command_response", False)
            command = message.metadata.get("command", "")

            if is_command_response and command == "/clear":
                # Специальное уведомление для команды очистки
                notification = {
                    "type": "CLEAR_CHAT",
                    "data": {
                        "message": message.content,
                        "session_id": message.session_id,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                }
            else:
                # Обычное сообщение от агента
                notification = {
                    "type": "AGENT_MESSAGE",
                    "data": {
                        "message_type": "text",
                        "content": message.content,
                        "agent_name": message.metadata.get("agent_id", "Agent"),
                        "session_id": message.session_id,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "message_id": f"agent_{datetime.now(timezone.utc).timestamp()}",
                        "attachments": message.metadata.get("attachments", []),
                        "buttons": message.metadata.get("buttons", []),
                        "form": message.metadata.get("form"),
                    },
                }

        # Сохраняем уведомление в БД с TTL 15 минут (используем UUID для уникальности)
        notification_key = f"web_notification:{message.session_id}:{uuid.uuid4().hex}"
        await self.storage.set(notification_key, json.dumps(notification), ttl=900)

        logger.info(
            f"📤 Уведомление сохранено: key={notification_key}, type={notification.get('type', 'unknown')}, content={message.content[:50]}..."
        )

    async def send_typing_notification(self, session_id: str, is_typing: bool):
        """Отправка уведомления о печати для web чата"""
        typing_notification = {
            "type": "AGENT_TYPING",
            "data": {
                "is_typing": is_typing,
                "agent_name": "Agent",
                "session_id": session_id,
            },
        }

        notification_key = f"web_notification:{session_id}:{uuid.uuid4().hex}"
        await self.storage.set(
            notification_key, json.dumps(typing_notification), ttl=900
        )

        status = "начал" if is_typing else "закончил"
        logger.info(f"💬 Агент {status} печатать: key={notification_key}")

    async def send_interrupt_question(self, session_id: str, question: str):
        """Сохраняет interrupt вопрос в БД"""
        interrupt_notification = {
            "type": "AGENT_INTERRUPT",
            "data": {
                "question": question,
                "session_id": session_id,
                "agent_name": "Agent",
            },
        }

        notification_key = f"web_notification:{session_id}:{uuid.uuid4().hex}"
        await self.storage.set(
            notification_key, json.dumps(interrupt_notification), ttl=900
        )
        logger.info(f"🟡 Interrupt уведомление сохранено: key={notification_key}")

    # Глобальный экземпляр для использования
    async def _process_single_file(
        self, file_data: Dict[str, Any], user_id: str, file_processor
    ):
        """Обрабатывает один файл из web чата"""
        # Декодируем base64 содержимое
        if "content" not in file_data:
            raise ValueError("Файл без содержимого в web запросе")

        file_content = base64.b64decode(file_data["content"])

        # Обрабатываем файл через процессор
        file_record = await file_processor.process_file_from_bytes(
            data=file_content,
            original_name=file_data.get("name", f"web_file_{uuid.uuid4().hex[:8]}"),
            content_type=file_data.get("content_type"),
            uploaded_by=user_id,
            metadata={
                "platform": "web",
                "web_upload": True,
                "file_size": file_data.get("size", len(file_content)),
            },
            tags=["web", "upload"],
        )

        return file_record

    async def _process_single_audio_file(
        self, audio_data: Dict[str, Any], user_id: str, audio_processor
    ):
        """Обрабатывает один аудиофайл из web чата"""
        # Декодируем base64 содержимое
        if "content" not in audio_data:
            raise ValueError("Аудиофайл без содержимого в web запросе")

        audio_content = base64.b64decode(audio_data["content"])

        # Определяем content_type
        content_type = audio_data.get("content_type", "audio/wav")
        if not content_type.startswith("audio/"):
            content_type = "audio/wav"

        # Обрабатываем аудиофайл через AudioProcessor с автоматическим распознаванием
        audio_record = await audio_processor.process_audio_from_bytes(
            data=audio_content,
            original_name=audio_data.get("name", f"web_audio_{uuid.uuid4().hex[:8]}.wav"),
            content_type=content_type,
            uploaded_by=user_id,
            auto_recognize=True,  # Автоматически распознаем речь
            metadata={
                "platform": "web",
                "web_upload": True,
                "file_size": audio_data.get("size", len(audio_content)),
            },
            tags=["web", "upload", "audio"],
        )

        return audio_record


web_interface = WebInterface({})
