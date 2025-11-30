"""
Telegram Interface - простой адаптер для Telegram Bot API.
Создается на лету при получении webhook.
"""

import logging
import asyncio
import re
from typing import Dict, Any, Optional, List
from datetime import datetime
import httpx
import json
from apps.agents.interfaces.base import BaseInterface, Message
from apps.agents.config import get_agents_settings
settings = get_agents_settings()
from core.files.processors import get_default_audio_processor
from apps.agents.container import get_agents_container

logger = logging.getLogger(__name__)


class TelegramInterface(BaseInterface):
    """
    Простой Telegram адаптер.
    Создается на лету для каждого запроса.
    """

    def __init__(self, bot_token: str, platform_config: Dict[str, Any]):
        super().__init__(platform_config)
        self.bot_token = bot_token
        self.username = platform_config.get("username", "unknown_bot")
        self._typing_tasks: Dict[str, asyncio.Task] = {}
        container = get_agents_container()
        self._storage = container.storage

    async def handle_message(
        self, raw_data: Dict[str, Any], flow_id: str
    ) -> Optional[Message]:
        """Преобразует Telegram Update в Message
        
        Возвращает None только для валидных случаев:
        - Нет message в update (callback_query и т.д.)
        - Нет текста и файлов
        - Обработана команда
        - Доступ запрещен (после отправки сообщения)
        - Медиа-группа (обрабатывается отдельно)
        """
        # Callback query, edited message и т.д. - не обрабатываем
        if "message" not in raw_data:
            return None

        tg_message = raw_data["message"]
        
        # Валидация обязательных полей
        if "from" not in tg_message:
            raise ValueError(f"Telegram update без поля 'from': {raw_data.get('update_id')}")
        if "chat" not in tg_message:
            raise ValueError(f"Telegram update без поля 'chat': {raw_data.get('update_id')}")
        
        user_id = str(tg_message["from"]["id"])
        chat_id = str(tg_message["chat"]["id"])
        username = tg_message["from"].get("username")
        text = tg_message.get("text", "") or tg_message.get("caption", "")
        
        # Проверяем доступ пользователя
        is_allowed, error_message = self.check_user_access(user_id, username)
        if not is_allowed:
            logger.warning(f"Доступ запрещен для пользователя {username or user_id} в flow {flow_id}")
            access_denied_message = Message(
                user_id=user_id,
                session_id="access_denied",
                content=error_message,
                flow_id=flow_id,
                platform="telegram",
                metadata={"chat_id": chat_id},
            )
            await self.send_message(access_denied_message)
            return None

        # Обрабатываем файлы если есть
        files_data = await self._extract_files_from_message(tg_message)

        # Медиа-группа обрабатывается отдельно
        media_group_id = tg_message.get("media_group_id")
        logger.debug(f"media_group_id={media_group_id}, files_count={len(files_data) if files_data else 0}")
        
        if media_group_id and files_data:
            logger.info(f"Обнаружена медиа-группа {media_group_id}, перенаправляем в группировку")
            return await self._handle_media_group(
                media_group_id, tg_message, user_id, chat_id, text, files_data, flow_id
            )

        # Пустое сообщение - игнорируем
        if not text and not files_data:
            return None

        # Команды обрабатываются напрямую
        is_command, command_response = await self.process_command(
            text, chat_id, flow_id
        )
        if is_command:
            if command_response:
                command_message = Message(
                    user_id=user_id,
                    session_id="command_response",
                    content=command_response,
                    flow_id=flow_id,
                    platform="telegram",
                    metadata={"chat_id": chat_id},
                )
                await self.send_message(command_message)
            return None

        # Получаем или создаем сессию
        session_id = await self.get_or_create_session(
            user_id=chat_id,
            flow_id=flow_id,
            metadata={"chat_id": chat_id, "bot_username": self.username},
        )

        # Обрабатываем файлы
        processed_files = []
        if files_data:
            audio_files = [f for f in files_data if f["type"] in ["audio", "voice"]]
            regular_files = [f for f in files_data if f["type"] not in ["audio", "voice"]]
            
            file_messages = []
            if regular_files:
                file_messages = await self.process_files(regular_files, user_id)
            
            audio_messages = []
            if audio_files:
                audio_messages = await self.process_audio_files(audio_files, user_id)
            
            all_messages = file_messages + audio_messages
            processed_files = all_messages

            if all_messages:
                files_text = "\n\n".join(all_messages)
                text = f"{text}\n\n{files_text}" if text else files_text

        return Message(
            user_id=user_id,
            session_id=session_id,
            flow_id=flow_id,
            content=text,
            platform="telegram",
            metadata={
                "chat_id": chat_id,
                "message_id": tg_message["message_id"],
                "bot_username": self.username,
            },
            files=processed_files,
        )

    async def send_message(self, message: Message):
        """Отправляет сообщение в Telegram с поддержкой аудиофайлов"""
        chat_id = message.metadata.get("chat_id")
        if not chat_id:
            raise ValueError(
            f"Не указан chat_id в metadata сообщения. "
            f"session_id={message.session_id}, user_id={message.user_id}"
        )

        clean_text, audio_files = self.extract_outgoing_audio_from_message(message.content)
        logger.debug(f"Отправка в Telegram chat_id={chat_id}: text={len(clean_text)}chars, audio={len(audio_files)}")

        if clean_text.strip():
            await self._send_text_message(chat_id, clean_text)

        for audio_info in audio_files:
            await self._send_audio_message(chat_id, audio_info)

    async def _send_text_message(self, chat_id: str, text: str):
        """Отправляет текстовое сообщение с автоматическим разбиением длинных сообщений"""
        # Обрабатываем ссылки на файлы
        text = self._beautify_file_links(text)
        
        # Конвертируем Markdown в HTML
        html_text = self._convert_markdown_to_html(text)
        
        # Разбиваем на части если превышает лимит Telegram (4096 символов)
        message_parts = self._split_message(html_text, max_length=4096)
        
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        
        for i, part in enumerate(message_parts):
            payload = {
                "chat_id": chat_id,
                "text": part,
                "parse_mode": "HTML",
            }

            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=payload)

                if response.status_code == 200:
                    if len(message_parts) > 1:
                        logger.info(f"✅ Отправлена часть {i+1}/{len(message_parts)} в Telegram чат {chat_id}")
                    else:
                        logger.info(f"✅ Отправлено текстовое сообщение в Telegram чат {chat_id}")
                else:
                    logger.error(f"❌ Ошибка отправки текста в Telegram: {response.status_code}")
                    logger.error(f"❌ Ответ API: {response.text}")
            
            # Небольшая задержка между частями чтобы сохранить порядок
            if i < len(message_parts) - 1:
                await asyncio.sleep(0.3)

    async def _send_audio_message(self, chat_id: str, audio_info: Dict[str, Any]):
        """Отправляет аудиофайл как voice message"""
        try:
            # Получаем аудиофайл из системы
            
            
            audio_processor = await get_default_audio_processor()
            audio_record = await audio_processor.get_audio_record(audio_info["audio_id"])
            
            if not audio_record:
                logger.error(f"Аудиофайл {audio_info['audio_id']} не найден для отправки")
                return

            # Получаем данные аудиофайла из S3
            logger.info(f"🔍 Скачиваем аудиофайл: {audio_record.s3_key} (размер в БД: {audio_record.file_size})")
            s3_client = await audio_processor._get_s3_client()
            audio_data = await s3_client.download_bytes(audio_record.s3_key)
            logger.info(f"🔍 Скачано байт: {len(audio_data) if audio_data else 0}")
            
            if not audio_data:
                logger.error(f"Не удалось скачать аудиофайл {audio_record.audio_id} из S3")
                return

            # Отправляем как аудиофайл через Telegram Bot API (sendAudio вместо sendVoice)
            url = f"https://api.telegram.org/bot{self.bot_token}/sendAudio"
            
            files = {
                "audio": (audio_record.original_name, audio_data, audio_record.content_type)
            }
            data = {"chat_id": chat_id}

            async with httpx.AsyncClient() as client:
                response = await client.post(url, data=data, files=files)

                if response.status_code == 200:
                    logger.info(f"🎵 Отправлен аудиофайл в Telegram чат {chat_id}")
                elif "VOICE_MESSAGES_FORBIDDEN" in response.text:
                    # Fallback: пробуем отправить как документ
                    logger.info("🔄 Voice сообщения запрещены, отправляем как документ")
                    await self._send_audio_as_document(chat_id, audio_record, audio_data)
                else:
                    logger.error(f"❌ Ошибка отправки аудио в Telegram: {response.status_code}")
                    logger.error(f"❌ Ответ API: {response.text}")

        except Exception as e:
            logger.error(f"❌ Ошибка отправки аудиофайла в Telegram: {e}")

    async def _send_audio_as_document(self, chat_id: str, audio_record, audio_data: bytes):
        """Отправляет аудиофайл как документ (fallback)"""
        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/sendDocument"
            
            files = {
                "document": (audio_record.original_name, audio_data, audio_record.content_type)
            }
            data = {
                "chat_id": chat_id,
                "caption": "🎵 Аудиосообщение"
            }

            async with httpx.AsyncClient() as client:
                response = await client.post(url, data=data, files=files)

                if response.status_code == 200:
                    logger.info(f"📎 Отправлен аудиофайл как документ в Telegram чат {chat_id}")
                elif "VOICE_MESSAGES_FORBIDDEN" in response.text:
                    # Последний fallback: отправляем ссылку на аудио
                    logger.info("🔄 Аудио полностью запрещено, отправляем ссылку")
                    await self._send_audio_link(chat_id, audio_record)
                else:
                    logger.error(f"❌ Ошибка отправки аудио как документа: {response.status_code}")
                    logger.error(f"❌ Ответ API: {response.text}")

        except Exception as e:
            logger.error(f"❌ Ошибка отправки аудио как документа: {e}")

    async def _send_audio_link(self, chat_id: str, audio_record):
        """Отправляет ссылку на аудио (с кнопкой в prod или текстом в dev)"""
        try:
            # Получаем конфигурацию
            
            
            domain = settings.server.domain
            protocol = "https" if settings.server.env == "production" else "http"
            port = f":{settings.server.port}" if settings.server.port != 80 and settings.server.port != 443 else ""
            
            full_url = f"{protocol}://{domain}{port}/api/v1/files/download/audio/{audio_record.audio_id}"
            
            if settings.server.env == "production":
                # Production: отправляем с inline кнопкой
                url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
                payload = {
                    "chat_id": chat_id,
                    "text": "🎵 Аудиосообщение готово!",
                    "reply_markup": {
                        "inline_keyboard": [[
                            {
                                "text": "🎵 Слушать",
                                "url": full_url
                            }
                        ]]
                    }
                }
                
                async with httpx.AsyncClient() as client:
                    response = await client.post(url, json=payload)
                    
                    if response.status_code == 200:
                        logger.info(f"🎵 Отправлена кнопка аудио в Telegram чат {chat_id}")
                    else:
                        logger.error(f"❌ Ошибка отправки кнопки: {response.status_code}")
            else:
                # Development: ссылка для прямого прослушивания
                fallback_text = f"🎵 Аудиосообщение готово!\n🎧 Слушать: {full_url}"
                await self._send_text_message(chat_id, fallback_text)
                
        except Exception as e:
            logger.error(f"❌ Ошибка отправки ссылки на аудио: {e}")

    async def send_reasoning(self, session_id: str, reasoning_text: str):
        """
        Telegram-специфичная отправка reasoning.
        Использует expandable blockquote для компактности.
        """
        if not reasoning_text or not reasoning_text.strip():
            return
        
        # Извлекаем chat_id из session_id (формат: telegram:chat_id:flow:uuid)
        parts = session_id.split(":")
        chat_id = parts[1] if len(parts) > 1 else None
        
        if not chat_id:
            logger.warning(f"Не удалось извлечь chat_id из session_id: {session_id}")
            return
        
        # Форматируем reasoning как expandable blockquote (скрываемый блок)
        # Ограничиваем длину reasoning для читаемости
        max_length = 500
        if len(reasoning_text) > max_length:
            # Разбиваем на абзацы
            paragraphs = reasoning_text.split("\n\n")
            for paragraph in paragraphs:
                if paragraph.strip():
                    truncated = paragraph[:max_length]
                    formatted = f"<blockquote expandable>💭 <b>Размышление:</b>\n{truncated}</blockquote>"
                    await self._send_reasoning_message(chat_id, formatted)
                    await asyncio.sleep(0.3)
        else:
            formatted = f"<blockquote expandable>💭 <b>Размышление:</b>\n{reasoning_text}</blockquote>"
            await self._send_reasoning_message(chat_id, formatted)
        
        logger.debug(f"💭 Reasoning отправлен в Telegram для session {session_id}")

    async def _send_reasoning_message(self, chat_id: str, formatted_text: str):
        """Отправляет reasoning сообщение в Telegram"""
        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            payload = {
                "chat_id": chat_id,
                "text": formatted_text,
                "parse_mode": "HTML",
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=payload)
                
                if response.status_code != 200:
                    logger.error(
                        f"Ошибка отправки reasoning в Telegram: {response.status_code} - {response.text}"
                    )
        except Exception as e:
            logger.error(f"Исключение при отправке reasoning: {e}", exc_info=True)

    async def send_typing_notification(self, session_id: str, is_typing: bool):
        """Отправка уведомления о печати в Telegram"""
        try:
            # Извлекаем chat_id из session_id: telegram:{user_id}:{flow_id}:{unique_id}
            parts = session_id.split(":")
            if len(parts) < 2 or parts[0] != "telegram":
                logger.warning(f"Неправильный формат session_id для Telegram: {session_id}")
                return
            
            chat_id = parts[1]  # user_id = chat_id в Telegram

            if is_typing:
                # Отправляем "typing" action
                url = f"https://api.telegram.org/bot{self.bot_token}/sendChatAction"
                payload = {"chat_id": chat_id, "action": "typing"}

                async with httpx.AsyncClient() as client:
                    response = await client.post(url, json=payload)

                    if response.status_code == 200:
                        logger.info(f"💬 Отправлено typing в Telegram чат {chat_id}")
                    else:
                        logger.error(
                            f"❌ Ошибка отправки typing в Telegram: {response.status_code}"
                        )
            # Для is_typing=False ничего не делаем, так как typing автоматически исчезает

        except Exception as e:
            logger.error(f"Ошибка отправки typing уведомления в Telegram: {e}")
    
    async def start_typing_indicator(self, session_id: str):
        """Запускает фоновую корутину для поддержания индикатора 'печатает...'"""
        if session_id in self._typing_tasks:
            logger.debug(f"Typing индикатор для {session_id} уже запущен")
            return
        
        task = asyncio.create_task(self._typing_loop(session_id))
        self._typing_tasks[session_id] = task
        logger.info(f"🔄 Запущена фоновая корутина typing для {session_id}")
    
    async def stop_typing_indicator(self, session_id: str):
        """Останавливает фоновую корутину typing индикатора"""
        task = self._typing_tasks.pop(session_id, None)
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            logger.info(f"⏹️ Остановлена корутина typing для {session_id}")
    
    async def _typing_loop(self, session_id: str):
        """Фоновая корутина для периодической отправки typing индикатора"""
        try:
            parts = session_id.split(":")
            if len(parts) < 2 or parts[0] != "telegram":
                return
            
            chat_id = parts[1]
            url = f"https://api.telegram.org/bot{self.bot_token}/sendChatAction"
            payload = {"chat_id": chat_id, "action": "typing"}
            
            while True:
                try:
                    async with httpx.AsyncClient(timeout=3.0) as client:
                        await client.post(url, json=payload)
                    logger.debug(f"⌛ Отправлен периодический typing для чата {chat_id}")
                except Exception as e:
                    logger.warning(f"Ошибка отправки typing: {e}")
                
                await asyncio.sleep(4.0)
        
        except asyncio.CancelledError:
            logger.debug(f"Корутина typing для {session_id} отменена")
            raise

    async def setup_commands(self) -> bool:
        """Устанавливает команды для Telegram бота"""
        commands = [
            {"command": "start", "description": "Начать новый диалог"},
            {"command": "help", "description": "Показать справку"},
            {"command": "clear", "description": "Очистить контекст диалога"},
        ]

        url = f"https://api.telegram.org/bot{self.bot_token}/setMyCommands"
        payload = {"commands": commands}

        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload)

            if response.status_code == 200:
                logger.info("✅ Команды Telegram бота установлены")
                return True
            else:
                logger.error(f"❌ Ошибка установки команд: {response.text}")
                return False

    @staticmethod
    async def set_webhook(bot_token: str, webhook_url: str):
        """Устанавливает webhook для Telegram бота"""
        try:
            url = f"https://api.telegram.org/bot{bot_token}/setWebhook"
            payload = {"url": webhook_url}

            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=payload)

                if response.status_code == 200:
                    logger.info(f"✅ Webhook установлен: {webhook_url}")
                    return True
                else:
                    logger.error(f"❌ Ошибка установки webhook: {response.text}")
                    return False

        except Exception as e:
            logger.error(f"Ошибка установки webhook: {e}")
            return False

    async def _extract_files_from_message(
        self, tg_message: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Извлекает информацию о файлах из Telegram сообщения"""
        files_data = []

        # Поддерживаемые типы файлов в Telegram
        file_types = [
            "document",
            "photo",
            "video",
            "audio",
            "voice",
            "video_note",
            "animation",
            "sticker",
        ]

        for file_type in file_types:
            if file_type in tg_message:
                file_info = tg_message[file_type]

                # Для photo берем самое большое разрешение
                if file_type == "photo":
                    file_info = max(file_info, key=lambda x: x.get("file_size", 0))

                files_data.append(
                    {
                        "type": file_type,
                        "file_id": file_info.get("file_id"),
                        "file_name": file_info.get(
                            "file_name",
                            f"{file_type}_{file_info.get('file_id', 'unknown')}",
                        ),
                        "file_size": file_info.get("file_size", 0),
                        "mime_type": file_info.get("mime_type"),
                        "raw_data": file_info,
                    }
                )

        return files_data

    async def _process_single_file(
        self, file_data: Dict[str, Any], user_id: str, file_processor
    ):
        """Обрабатывает один файл из Telegram"""
        try:
            # Получаем URL файла от Telegram
            file_url = await self._get_telegram_file_url(file_data["file_id"])
            if not file_url:
                logger.error(f"Не удалось получить URL файла {file_data['file_id']}")
                return None

            # Обрабатываем файл через процессор
            file_record = await file_processor.process_file_from_url(
                file_url=file_url,
                original_name=file_data["file_name"],
                uploaded_by=user_id,
                metadata={
                    "telegram_file_id": file_data["file_id"],
                    "telegram_file_type": file_data["type"],
                    "platform": "telegram",
                },
                tags=["telegram", file_data["type"]],
            )

            return file_record

        except Exception as e:
            logger.error(
                f"Ошибка обработки Telegram файла {file_data.get('file_id')}: {e}"
            )
            return None

    async def _get_telegram_file_url(self, file_id: str) -> Optional[str]:
        """Получает URL файла от Telegram Bot API"""
        try:
            # Получаем информацию о файле
            url = f"https://api.telegram.org/bot{self.bot_token}/getFile"
            params = {"file_id": file_id}

            async with httpx.AsyncClient() as client:
                response = await client.get(url, params=params)

                if response.status_code != 200:
                    logger.error(
                        f"Ошибка получения файла от Telegram: {response.status_code}"
                    )
                    return None

                data = response.json()

                if not data.get("ok"):
                    logger.error(f"Telegram API вернул ошибку: {data}")
                    return None

                file_path = data["result"]["file_path"]
                file_url = (
                    f"https://api.telegram.org/file/bot{self.bot_token}/{file_path}"
                )

                return file_url

        except Exception as e:
            logger.error(f"Ошибка получения URL файла {file_id}: {e}")
            return None


    async def _process_single_audio_file(
        self, audio_data: Dict[str, Any], user_id: str, audio_processor
    ):
        """Обрабатывает один аудиофайл из Telegram"""
        try:
            # Получаем URL аудиофайла от Telegram
            audio_url = await self._get_telegram_file_url(audio_data["file_id"])
            if not audio_url:
                logger.error(f"Не удалось получить URL аудиофайла {audio_data['file_id']}")
                return None

            # Определяем имя файла и content_type
            file_name = audio_data["file_name"]
            content_type = audio_data.get("mime_type", "audio/ogg")
            
            # Для voice сообщений Telegram всегда использует OGG Opus
            if audio_data["type"] == "voice":
                # Cloud Voice API требует именно такой формат для OGG Opus
                content_type = "audio/ogg; codecs=opus"
                if not file_name.endswith('.ogg'):
                    file_name = f"voice_message_{audio_data['file_id'][:8]}.ogg"
            elif audio_data["type"] == "audio":
                # Для обычных аудиофайлов используем mime_type от Telegram или WAV по умолчанию
                if not content_type or content_type == "audio/ogg":
                    content_type = "audio/ogg; codecs=opus"

            # Обрабатываем аудиофайл через AudioProcessor с автоматическим распознаванием
            audio_record = await audio_processor.process_audio_from_url(
                audio_url=audio_url,
                original_name=file_name,
                content_type=content_type,  # Передаем правильный content_type
                uploaded_by=user_id,
                auto_recognize=True,  # Автоматически распознаем речь
                metadata={
                    "telegram_file_id": audio_data["file_id"],
                    "telegram_file_type": audio_data["type"],
                    "platform": "telegram",
                    "telegram_upload": True,
                    "duration": audio_data.get("duration"),  # Длительность от Telegram
                },
                tags=["telegram", audio_data["type"], "voice" if audio_data["type"] == "voice" else "audio"],
            )

            return audio_record

        except Exception as e:
            logger.error(
                f"Ошибка обработки Telegram аудиофайла {audio_data.get('file_id')}: {e}"
            )
            return None

    @staticmethod
    async def get_bot_token_for_flow(
        flow_id: str, platform_config: Dict[str, Any]
    ) -> Optional[str]:
        """
        Получает токен бота для flow из БД.
        Поддерживает:
        - Хардкод: {"token": "123:ABC..."}
        - Ссылка: {"token": "@var:telegram_bot_token"}
        """
        token_value = platform_config.get("token")
        
        if not token_value:
            raise ValueError(f"No token configured for flow {flow_id}")
        
        
        container = get_agents_container()
        variables_service = container.variables_service
        resolved_token = await variables_service.resolve(token_value)
        logger.info(f"✅ Токен резолвнут для flow {flow_id}")
        return resolved_token

    @staticmethod
    async def get_bot_info(bot_token: str) -> Optional[Dict]:
        """Получает информацию о боте через getMe API"""
        url = f"https://api.telegram.org/bot{bot_token}/getMe"
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
            
            if response.status_code != 200:
                logger.error(f"❌ getMe API error: {response.status_code}")
                return None
            
            data = response.json()
            if not data.get("ok"):
                logger.error(f"❌ getMe API returned not ok: {data}")
                return None
            
            return data["result"]

    @classmethod
    async def register(
        cls,
        flow_id: str,
        username: str,
        platform_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Регистрирует Telegram бота:
        1. Резолвит username (если @var:key)
        2. Проверяет токен через getMe
        3. Обновляет username в config
        4. Local: перезагружает polling
        5. Production: устанавливает webhook
        6. Устанавливает команды бота
        """
        from apps.agents.config import get_agents_settings
        settings = get_agents_settings()
        
        container = get_agents_container()
        variables_service = container.variables_service
        resolved_username = await variables_service.resolve(username)
        
        # Получаем токен через get_bot_token_for_flow (поддерживает @var:)
        token = await cls.get_bot_token_for_flow(flow_id, platform_config)
        if not token:
            raise ValueError(f"Token not found for {resolved_username}")
        
        # Проверяем токен через getMe API
        bot_info = await cls.get_bot_info(token)
        if not bot_info:
            raise ValueError("Invalid token or bot not accessible")
        
        actual_username = bot_info.get("username")
        bot_name = bot_info.get("first_name", "Bot")
        
        logger.info(f"🤖 Telegram bot: @{actual_username} ({bot_name})")
        
        # Обновляем username в platform_config если отличается
        if actual_username != username:
            logger.warning(f"⚠️ Username изменен: {username} → {actual_username}")
            platform_config["username"] = actual_username
            
            # Используем репозиторий из BaseInterface (создаем временный экземпляр для доступа к атрибуту)
            temp_interface = cls(token, platform_config)
            flow_config = await temp_interface.flow_repository.get(flow_id)
            if flow_config and flow_config.platforms.get("telegram"):
                # Обновляем только username, не трогая остальные поля (token и т.д.)
                flow_config.platforms["telegram"]["username"] = actual_username
                await temp_interface.flow_repository.set(flow_config)
                logger.info("✅ Username обновлен в FlowConfig")
        
        interface = cls(token, platform_config)
        await interface.setup_commands()
        
        from core.context import get_context
        context = get_context()
        if not context or not context.active_company:
            raise ValueError("No active company in context")
        
        flow_key = f"company:{context.active_company.company_id}:flow:{flow_id}"
        
        # Настраиваем webhook или polling
        if settings.server.env == "local":
            from apps.agents.services.business.telegram_poller import telegram_poller
            await telegram_poller.reload()
            
            return {
                "success": True,
                "platform": "telegram",
                "mode": "polling",
                "username": actual_username,
                "bot_name": bot_name,
                "flow_key": flow_key
            }
        else:
            webhook_url = f"https://{settings.server.domain}/api/v1/webhook/telegram/{flow_key}"
            webhook_success = await cls.set_webhook(token, webhook_url)
            
            if not webhook_success:
                raise RuntimeError(f"Failed to set webhook for {actual_username}")
            
            return {
                "success": True,
                "platform": "telegram",
                "mode": "webhook",
                "username": actual_username,
                "bot_name": bot_name,
                "webhook_url": webhook_url,
                "flow_key": flow_key
            }

    async def _handle_media_group(
        self, media_group_id: str, tg_message: Dict[str, Any], 
        user_id: str, chat_id: str, text: str, files_data: List[Dict], flow_id: str
    ) -> Optional[Message]:
        """Обрабатывает группу медиафайлов с задержкой для накопления"""
        
        media_group_key = f"media_group:{media_group_id}"
        
        # Получаем существующую группу или создаем новую
        existing_group_data = await self._storage.get(media_group_key)
        if existing_group_data:
            group_data = json.loads(existing_group_data)
        else:
            group_data = {
                "messages": [],
                "user_id": user_id,
                "chat_id": chat_id,
                "flow_id": flow_id,
                "created_at": datetime.now().isoformat()
            }
        
        # Добавляем текущее сообщение
        group_data["messages"].append({
            "tg_message": tg_message,
            "text": text,
            "files_data": files_data,
            "added_at": datetime.now().isoformat()
        })
        
        # Сохраняем в Storage с TTL 10 секунд
        await self._storage.set(media_group_key, json.dumps(group_data), ttl=10)
        
        logger.info(f"🔄 Добавлено сообщение в медиа-группу {media_group_id}, всего: {len(group_data['messages'])}")
        
        # Запускаем асинхронную обработку с задержкой
        asyncio.create_task(self._process_media_group_after_delay(media_group_id))
        
        # Возвращаем None - сообщение будет обработано позже
        return None
    
    async def _process_media_group_after_delay(self, media_group_id: str):
        """Обрабатывает накопленную медиа-группу после задержки"""
        await asyncio.sleep(2.0)  # Ждем 2 секунды
        
        media_group_key = f"media_group:{media_group_id}"
        processing_key = f"media_group_processing:{media_group_id}"
        
        # Проверяем что группа еще не обрабатывается
        already_processing = await self._storage.get(processing_key)
        if already_processing:
            logger.info(f"⏭️ Медиа-группа {media_group_id} уже обрабатывается, пропускаем")
            return
            
        # Устанавливаем флаг обработки
        await self._storage.set(processing_key, json.dumps({"status": "processing", "timestamp": datetime.now().isoformat()}), ttl=30)
        
        # Получаем группу из Storage
        group_data_json = await self._storage.get(media_group_key)
        if not group_data_json:
            logger.warning(f"⚠️ Медиа-группа {media_group_id} не найдена в Storage")
            await self._storage.delete(processing_key)
            return
            
        group_data = json.loads(group_data_json)
        messages = group_data["messages"]
        user_id = group_data["user_id"]
        chat_id = group_data["chat_id"]
        flow_id = group_data["flow_id"]
        
        # Удаляем группу из Storage
        await self._storage.delete(media_group_key)
        await self._storage.delete(processing_key)
        
        logger.info(f"📸 Обрабатываем медиа-группу {media_group_id} с {len(messages)} файлами")
        
        # Объединяем все файлы и текст
        all_files_data = []
        all_text_parts = []
        
        for i, msg_data in enumerate(messages):
            logger.info(f"🔍 Сообщение {i+1}: text='{msg_data.get('text', '')}', files={len(msg_data.get('files_data', []))}")
            if msg_data["files_data"]:
                all_files_data.extend(msg_data["files_data"])
            if msg_data["text"]:
                all_text_parts.append(msg_data["text"])
        
        logger.info(f"🔍 Итого: текстов={len(all_text_parts)}, файлов={len(all_files_data)}")
        logger.info(f"🔍 Тексты: {all_text_parts}")
        
        # Получаем сессию
        session_id = await self.get_or_create_session(
            user_id=chat_id,
            flow_id=flow_id,
            metadata={"chat_id": chat_id, "bot_username": self.username},
        )
        
        # Обрабатываем все файлы
        processed_files = []
        if all_files_data:
            file_messages = await self.process_files(all_files_data, user_id)
            processed_files = file_messages
            
        # Формируем итоговый текст
        combined_text = " ".join(all_text_parts) if all_text_parts else ""
        if processed_files:
            files_text = "\n\n".join(processed_files)
            if combined_text:
                combined_text = f"{combined_text}\n\n{files_text}"
            else:
                combined_text = files_text
        
        # Создаем объединенное сообщение
        combined_message = Message(
            user_id=user_id,
            session_id=session_id,
            flow_id=flow_id,
            content=combined_text,
            platform="telegram",
            metadata={
                "chat_id": chat_id,
                "message_id": messages[0]["tg_message"]["message_id"],  # ID первого сообщения
                "bot_username": self.username,
                "media_group_id": media_group_id,
                "files_count": len(all_files_data)
            },
            files=processed_files,
        )
        
        # Создаем задачу через BaseInterface
        task_id = await self.create_task(combined_message, flow_id)
        if task_id:
            logger.info(f"📋 Создана задача {task_id} для медиа-группы {media_group_id} с {len(all_files_data)} файлами")
        else:
            logger.warning(f"⏳ Задача не создана для медиа-группы {media_group_id}")
        
        return combined_message

    def _split_message(self, text: str, max_length: int = 4096) -> List[str]:
        """
        Разбивает длинное сообщение на части по max_length символов.
        Старается разбивать по логичным границам: абзацы, предложения.
        """
        if len(text) <= max_length:
            return [text]
        
        parts = []
        current_part = ""
        
        # Разбиваем по абзацам
        paragraphs = text.split('\n\n')
        
        for paragraph in paragraphs:
            # Если параграф сам по себе длиннее max_length
            if len(paragraph) > max_length:
                # Разбиваем по предложениям
                sentences = paragraph.split('. ')
                for sentence in sentences:
                    sentence_with_dot = sentence if sentence.endswith('.') else sentence + '.'
                    
                    # Если даже предложение слишком длинное - режем по символам
                    if len(sentence_with_dot) > max_length:
                        for i in range(0, len(sentence_with_dot), max_length - 10):
                            chunk = sentence_with_dot[i:i + max_length - 10]
                            if current_part:
                                parts.append(current_part)
                                current_part = ""
                            parts.append(chunk)
                    else:
                        if len(current_part) + len(sentence_with_dot) + 1 <= max_length:
                            current_part += sentence_with_dot + ' '
                        else:
                            if current_part:
                                parts.append(current_part.strip())
                            current_part = sentence_with_dot + ' '
            else:
                # Добавляем параграф к текущей части
                if len(current_part) + len(paragraph) + 2 <= max_length:
                    current_part += paragraph + '\n\n'
                else:
                    if current_part:
                        parts.append(current_part.strip())
                    current_part = paragraph + '\n\n'
        
        # Добавляем остаток
        if current_part:
            parts.append(current_part.strip())
        
        return parts if parts else [text[:max_length]]
    
    def _beautify_file_links(self, text: str) -> str:
        """
        Преобразует голые ссылки на файлы в красивый формат.
        
        Например:
        https://example.com/files/document.pdf?params -> 📎 [document.pdf](url)
        """
        import urllib.parse
        from pathlib import Path
        
        # Паттерн для поиска URL с расширениями файлов
        # Ищем URL которые заканчиваются на .doc, .docx, .pdf, .txt, .xls, .xlsx и т.д.
        file_extensions = r'\.(pdf|docx?|xlsx?|txt|zip|rar|png|jpe?g|gif|mp4|mp3|wav)'
        
        # Находим все URL с файлами, которые идут отдельной строкой или после пробела
        def replace_file_url(match):
            full_match = match.group(0)
            url = match.group(1)
            
            # Извлекаем имя файла из URL
            parsed = urllib.parse.urlparse(url)
            path = urllib.parse.unquote(parsed.path)
            filename = Path(path).name
            
            # Если не смогли извлечь имя - используем оригинальный URL
            if not filename:
                return full_match
            
            # Возвращаем красиво отформатированную ссылку
            return f"📎 [{filename}]({url})"
        
        # Ищем URL которые:
        # 1. Начинаются с новой строки или пробела
        # 2. Содержат https?://
        # 3. Заканчиваются расширением файла (с возможными query параметрами)
        pattern = rf'(?:^|\s)(https?://[^\s<>]+{file_extensions}[^\s<>]*?)(?:\s|$)'
        
        text = re.sub(pattern, replace_file_url, text, flags=re.MULTILINE | re.IGNORECASE)
        
        return text
    
    def _convert_markdown_to_html(self, text: str) -> str:
        """Конвертирует простой Markdown в HTML для Telegram"""
        
        # Шаг 1: Защищаем ВСЕ URL (и в ссылках [](url), и голые http://...)
        protected_items = []
        
        # Сохраняем Markdown ссылки [текст](url)
        def save_markdown_link(match):
            protected_items.append(('markdown_link', match.group(0)))
            return f"§§§ITEM{len(protected_items)-1}§§§"
        
        text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', save_markdown_link, text)
        
        # Сохраняем голые URL (http://, https://)
        # Захватываем до пробела, скобки или *, включая _ внутри URL
        def save_url(match):
            protected_items.append(('url', match.group(0)))
            return f"§§§ITEM{len(protected_items)-1}§§§"
        
        text = re.sub(r'https?://[^\s<>"\)\*]+', save_url, text)
        
        # Шаг 2: Обрабатываем форматирование (теперь URL защищены)
        # Заменяем **жирный** на <b>жирный</b>
        text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
        
        # Заменяем *курсив* на <i>курсив</i> (только одиночные звездочки)
        text = re.sub(r'(?<!\*)\*(?!\*)([^*]+)\*(?!\*)', r'<i>\1</i>', text)
        
        # Заменяем _подчеркнутый_ на <u>подчеркнутый</u>
        text = re.sub(r'_(.*?)_', r'<u>\1</u>', text)
        
        # Шаг 3: Восстанавливаем защищенные элементы
        for i, (item_type, item_value) in enumerate(protected_items):
            if item_type == 'markdown_link':
                # Конвертируем [текст](url) в <a href="url">текст</a>
                html = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', item_value)
                text = text.replace(f"§§§ITEM{i}§§§", html)
            elif item_type == 'url':
                # Голый URL оборачиваем в ссылку
                text = text.replace(f"§§§ITEM{i}§§§", f'<a href="{item_value}">{item_value}</a>')
        
        return text
