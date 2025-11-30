"""
Web Interface - адаптер для веб-чата.
Работает в многоинстансной архитектуре через БД уведомления.
"""

import asyncio
import base64
import uuid
import logging
import json
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from apps.agents.interfaces.base import BaseInterface, Message
from core.context import get_context
from apps.agents.services.tracing.decorators import trace_span
from apps.agents.models.trace_models import SpanType
from apps.agents.container import get_agents_container

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
        container = get_agents_container()
        self._storage = container.storage
        self.platform_name = "web"

    def set_websocket_manager(self, websocket_manager):
        """Устанавливает WebSocket менеджер для отправки сообщений"""
        self.websocket_manager = websocket_manager

    def _build_web_session_id(
        self, 
        provided_session_id: Optional[str], 
        user_id: str, 
        flow_id: str
    ) -> str:
        """Формирует session_id для web платформы.
        
        Логика:
        1. Если provided_session_id в формате "web:{user}:{flow}:{uuid}" 
           и user совпадает - используем его
        2. Иначе создаем новый session_id
        """
        # Проверяем валидный web session_id от того же пользователя
        if provided_session_id and provided_session_id.startswith("web:"):
            parts = provided_session_id.split(":")
            # Формат: web:user_id:flow_id:uuid (минимум 4 части)
            if len(parts) >= 4 and parts[1] == user_id:
                return provided_session_id
        
        # Создаем новый session_id
        return f"web:{user_id}:{flow_id}:{uuid.uuid4().hex[:8]}"

    @trace_span(
        name="web_interface.handle_message",
        span_type=SpanType.OTHER,
        metadata={"component": "web_interface", "operation": "handle_message"}
    )
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
            logger.warning(f"Доступ запрещен для пользователя {real_user_id} ({user_email}) в flow {flow_id}")

            temp_session_id = self._build_web_session_id(None, real_user_id, flow_id)

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

        # Формируем session_id через единую функцию
        session_id = self._build_web_session_id(js_session_id, real_user_id, flow_id)

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

    @trace_span(
        name="web_interface.send_reasoning",
        span_type=SpanType.OTHER,
        metadata={"component": "web_interface", "operation": "send_reasoning"}
    )
    async def send_reasoning(self, session_id: str, reasoning_text: str):
        """
        Отправляет reasoning как отдельное уведомление в web chat.
        Reasoning отображается как специальное сообщение с индикатором "думает".

        Args:
            session_id: ID сессии
            reasoning_text: Текст reasoning от LLM
        """
        if not reasoning_text or not reasoning_text.strip():
            return

        # Извлекаем user_id из session_id (формат: web:user_id:flow:uuid)
        parts = session_id.split(":")
        user_id = parts[1] if len(parts) > 1 else "unknown"

        # Создаем уведомление для reasoning
        notification = {
            "type": "AGENT_REASONING",
            "session_id": session_id,
            "data": {
                "content": reasoning_text.strip(),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "message_id": f"reasoning_{datetime.now(timezone.utc).timestamp()}",
            },
        }

        notification_key = f"web_notification:web:{user_id}:{uuid.uuid4().hex}"
        await self._storage.set(notification_key, json.dumps(notification), ttl=900, force_global=True)

        logger.debug(f"💭 Reasoning отправлен в web chat для session {session_id}: {reasoning_text[:50]}...")

        await asyncio.sleep(0.3)

    @trace_span(
        name="web_interface.send_message",
        span_type=SpanType.OTHER,
        metadata={"component": "web_interface", "operation": "send_message"}
    )
    async def send_message(self, message: Message):
        """
        Сохраняет сообщение как уведомление в БД для многоинстансной архитектуры.
        WebSocket polling на нужном инстансе подхватит и отправит клиенту.
        """
        is_user_message = message.metadata.get("is_user_message", False)

        if is_user_message:
            notification = {
                "type": "USER_MESSAGE",
                "session_id": message.session_id,
                "content": message.content,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "message_id": f"user_{datetime.now(timezone.utc).timestamp()}",
                "user_id": message.user_id,
            }
        else:
            is_command_response = message.metadata.get("is_command_response", False)
            command = message.metadata.get("command", "")

            if is_command_response and command == "/clear":
                notification = {
                    "type": "CLEAR_CHAT",
                    "session_id": message.session_id,
                    "data": {
                        "message": message.content,
                        "session_id": message.session_id,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                }
            else:
                notification = {
                    "type": "AGENT_MESSAGE",
                    "session_id": message.session_id,
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

        notification_key = f"web_notification:web:{message.user_id}:{uuid.uuid4().hex}"
        await self._storage.set(notification_key, json.dumps(notification), ttl=900, force_global=True)

        logger.info(
            f"📤 Уведомление сохранено: key={notification_key}, type={notification.get('type', 'unknown')}, content={message.content[:50]}..."
        )

    @trace_span(
        name="web_interface.send_typing_notification",
        span_type=SpanType.OTHER,
        metadata={"component": "web_interface", "operation": "send_typing_notification"}
    )
    async def send_typing_notification(self, session_id: str, is_typing: bool):
        """Отправка уведомления о печати для web чата"""
        parts = session_id.split(':')
        user_id = parts[1] if len(parts) >= 2 else "unknown"

        typing_notification = {
            "type": "AGENT_TYPING",
            "session_id": session_id,
            "data": {
                "is_typing": is_typing,
                "agent_name": "Agent",
                "session_id": session_id,
            },
        }

        notification_key = f"web_notification:web:{user_id}:{uuid.uuid4().hex}"
        await self._storage.set(notification_key, json.dumps(typing_notification), ttl=900, force_global=True)

        status = "начал" if is_typing else "закончил"
        logger.info(f"💬 Агент {status} печатать: key={notification_key}")

    @trace_span(
        name="web_interface.send_interrupt_question",
        span_type=SpanType.OTHER,
        metadata={"component": "web_interface", "operation": "send_interrupt_question"}
    )
    async def send_interrupt_question(self, session_id: str, question: str):
        """Сохраняет interrupt вопрос в БД"""
        parts = session_id.split(':')
        user_id = parts[1] if len(parts) >= 2 else "unknown"

        interrupt_notification = {
            "type": "AGENT_INTERRUPT",
            "session_id": session_id,
            "data": {
                "question": question,
                "session_id": session_id,
                "agent_name": "Agent",
            },
        }

        notification_key = f"web_notification:web:{user_id}:{uuid.uuid4().hex}"
        await self._storage.set(notification_key, json.dumps(interrupt_notification), ttl=900, force_global=True)
        logger.info(f"🟡 Interrupt уведомление сохранено: key={notification_key}")

    @trace_span(
        name="web_interface._process_single_file",
        span_type=SpanType.OTHER,
        metadata={"component": "web_interface", "operation": "process_file"}
    )
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

    @trace_span(
        name="web_interface._process_single_audio_file",
        span_type=SpanType.OTHER,
        metadata={"component": "web_interface", "operation": "process_audio"}
    )
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


_web_interface = None


def get_web_interface() -> WebInterface:
    """Получает глобальный экземпляр WebInterface"""
    global _web_interface
    if _web_interface is None:
        _web_interface = WebInterface({})
    return _web_interface
