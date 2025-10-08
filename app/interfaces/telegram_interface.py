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
from app.interfaces.base import BaseInterface, Message
from app.core.storage import Storage
from app.core.config import settings
from app.core.audio_processor import get_default_audio_processor
from app.services.variables_service import get_variables_service
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

    async def handle_message(
        self, raw_data: Dict[str, Any], flow_id: str
    ) -> Optional[Message]:
        """Преобразует Telegram Update в Message"""
        try:
            if "message" not in raw_data:
                return None

            tg_message = raw_data["message"]
            user_id = str(tg_message["from"]["id"])
            chat_id = str(tg_message["chat"]["id"])
            text = tg_message.get("text", "") or tg_message.get("caption", "")

            # Обрабатываем файлы если есть
            files_data = await self._extract_files_from_message(tg_message)

            # Проверяем на media_group_id для группировки фотографий
            media_group_id = tg_message.get("media_group_id")
            logger.info(f"🔍 DEBUG: media_group_id={media_group_id}, files_data={len(files_data) if files_data else 0}")
            
            if media_group_id and files_data:
                # Это часть группы медиафайлов - накапливаем
                logger.info(f"🎯 Обнаружена медиа-группа {media_group_id}, перенаправляем в группировку")
                return await self._handle_media_group(
                    media_group_id, tg_message, user_id, chat_id, text, files_data, flow_id
                )

            # Если нет текста и нет файлов - пропускаем
            if not text and not files_data:
                return None

            # Проверяем команды
            is_command, command_response = await self.process_command(
                text, chat_id, flow_id
            )
            if is_command:
                # Отправляем ответ на команду напрямую
                if command_response:
                    command_message = Message(
                        user_id=user_id,
                        session_id="command_response",  # Специальная сессия для команд
                        content=command_response,
                        flow_id=flow_id,  # ИСПРАВЛЕНИЕ: добавляем flow_id
                        platform="telegram",
                        metadata={"chat_id": chat_id},
                    )
                    await self.send_message(command_message)
                return None  # Не создаем задачу для команд

            # Для обычных сообщений получаем или создаем сессию
            # Используем weather_flow как дефолтный flow (можно сделать настраиваемым)
            session_id = await self.get_or_create_session(
                user_id=chat_id,
                flow_id=flow_id,
                metadata={"chat_id": chat_id, "bot_username": self.username},
            )

            # Обрабатываем файлы и добавляем их в сообщение
            processed_files = []
            if files_data:
                # Разделяем аудиофайлы и обычные файлы
                audio_files = [f for f in files_data if f["type"] in ["audio", "voice"]]
                regular_files = [f for f in files_data if f["type"] not in ["audio", "voice"]]
                
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

                # Если есть файлы, добавляем информацию к тексту
                if all_messages:
                    files_text = "\n\n".join(all_messages)
                    if text:
                        text = f"{text}\n\n{files_text}"
                    else:
                        text = files_text

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

        except Exception as e:
            logger.error(f"Ошибка парсинга Telegram update: {e}")
            return None

    async def send_message(self, message: Message):
        """Отправляет сообщение в Telegram с поддержкой аудиофайлов"""
        try:
            chat_id = message.metadata.get("chat_id")
            if not chat_id:
                return

            # Извлекаем аудиофайлы из сообщения
            logger.info(f"🔍 Получено сообщение для отправки: {repr(message.content)}")
            clean_text, audio_files = self.extract_outgoing_audio_from_message(message.content)
            logger.info(f"🔍 Найдено аудиофайлов: {len(audio_files)}")
            logger.info(f"🔍 Чистый текст: {repr(clean_text)}")

            # Отправляем текстовое сообщение если есть
            if clean_text.strip():
                await self._send_text_message(chat_id, clean_text)

            # Отправляем аудиофайлы как voice messages
            for audio_info in audio_files:
                await self._send_audio_message(chat_id, audio_info)

        except Exception as e:
            logger.error(f"Ошибка отправки в Telegram: {e}")

    async def _send_text_message(self, chat_id: str, text: str):
        """Отправляет текстовое сообщение"""
        # Конвертируем Markdown в HTML
        html_text = self._convert_markdown_to_html(text)
        
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": html_text,
            "parse_mode": "HTML",
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload)

            if response.status_code == 200:
                logger.info(f"✅ Отправлено текстовое сообщение в Telegram чат {chat_id}")
            else:
                logger.error(f"❌ Ошибка отправки текста в Telegram: {response.status_code}")
                logger.error(f"❌ Ответ API: {response.text}")

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
        
        from app.services.variables_service import get_variables_service
        
        variables_service = get_variables_service()
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
        from app.core.config import settings
        from app.services.variables_service import get_variables_service
        
        # Резолвим username если это ссылка
        variables_service = get_variables_service()
        resolved_username = await variables_service.resolve(username)
        
        storage = Storage()
        
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
            
            flow_config = await storage.get_flow_config(flow_id)
            if flow_config:
                flow_config.platforms["telegram"]["username"] = actual_username
                await storage.set_flow_config(flow_config)
                logger.info(f"✅ Username обновлен в FlowConfig")
        
        # Устанавливаем команды
        interface = cls(token, platform_config)
        await interface.setup_commands()
        
        # Получаем полный ключ flow (company:ssd:flow:...)
        all_keys = await storage.list_by_prefix("", limit=1000, force_global=True)
        flow_key = None
        for key in all_keys:
            if f":flow:{flow_id}" in key:
                flow_key = key
                break
        
        if not flow_key:
            raise ValueError(f"Flow key not found for {flow_id}")
        
        # Настраиваем webhook или polling
        if settings.server.env == "local":
            from app.services.telegram_poller import telegram_poller
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
        
        storage = Storage()
        media_group_key = f"media_group:{media_group_id}"
        
        # Получаем существующую группу или создаем новую
        existing_group_data = await storage.get(media_group_key)
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
        await storage.set(media_group_key, json.dumps(group_data), ttl=10)
        
        logger.info(f"🔄 Добавлено сообщение в медиа-группу {media_group_id}, всего: {len(group_data['messages'])}")
        
        # Запускаем асинхронную обработку с задержкой
        asyncio.create_task(self._process_media_group_after_delay(media_group_id))
        
        # Возвращаем None - сообщение будет обработано позже
        return None
    
    async def _process_media_group_after_delay(self, media_group_id: str):
        """Обрабатывает накопленную медиа-группу после задержки"""
        await asyncio.sleep(2.0)  # Ждем 2 секунды
        
        storage = Storage()
        media_group_key = f"media_group:{media_group_id}"
        processing_key = f"media_group_processing:{media_group_id}"
        
        # Проверяем что группа еще не обрабатывается
        already_processing = await storage.get(processing_key)
        if already_processing:
            logger.info(f"⏭️ Медиа-группа {media_group_id} уже обрабатывается, пропускаем")
            return
            
        # Устанавливаем флаг обработки
        await storage.set(processing_key, json.dumps({"status": "processing", "timestamp": datetime.now().isoformat()}), ttl=30)
        
        # Получаем группу из Storage
        group_data_json = await storage.get(media_group_key)
        if not group_data_json:
            logger.warning(f"⚠️ Медиа-группа {media_group_id} не найдена в Storage")
            await storage.delete(processing_key)
            return
            
        group_data = json.loads(group_data_json)
        messages = group_data["messages"]
        user_id = group_data["user_id"]
        chat_id = group_data["chat_id"]
        flow_id = group_data["flow_id"]
        
        # Удаляем группу из Storage
        await storage.delete(media_group_key)
        await storage.delete(processing_key)
        
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

    def _convert_markdown_to_html(self, text: str) -> str:
        """Конвертирует простой Markdown в HTML для Telegram"""
        # Заменяем [текст](url) на <a href="url">текст</a>
        text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', text)
        
        # Заменяем **жирный** на <b>жирный</b>
        text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
        
        # Заменяем *курсив* на <i>курсив</i> (только одиночные звездочки)
        text = re.sub(r'(?<!\*)\*(?!\*)([^*]+)\*(?!\*)', r'<i>\1</i>', text)
        
        # Заменяем _подчеркнутый_ на <u>подчеркнутый</u>
        text = re.sub(r'_(.*?)_', r'<u>\1</u>', text)
        
        return text
