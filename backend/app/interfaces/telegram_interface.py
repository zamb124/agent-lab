"""
Telegram Interface - простой адаптер для Telegram Bot API.
Создается на лету при получении webhook.
"""

import logging
from typing import Dict, Any, Optional, List
import httpx
import json
from app.interfaces.base import BaseInterface, Message
from app.core.storage import Storage
from app.core.config import settings
from app.core.audio_processor import get_default_audio_processor
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
            text = tg_message.get("text", "")

            # Обрабатываем файлы если есть
            files_data = await self._extract_files_from_message(tg_message)

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
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
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
        """Получает токен бота для flow из БД"""
        username = platform_config.get("username", f"bot_{flow_id}")

        # Ищем токен в БД: token:telegram:username
        storage = Storage()
        token_key = f"token:telegram:{username}"

        token_json = await storage.get(token_key, force_global=True)

        if token_json:
            token = json.loads(token_json)
            logger.info(f"✅ Найден токен для {username} в БД")
            return token
        else:
            logger.error(f"❌ Не найден токен в БД: {token_key}")
            return None
