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
                file_messages = await self.process_files(files_data, user_id)
                processed_files = file_messages

                # Если есть файлы, добавляем информацию к тексту
                if file_messages:
                    files_text = "\n\n".join(file_messages)
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
        """Отправляет сообщение в Telegram"""
        try:
            chat_id = message.metadata.get("chat_id")
            if not chat_id:
                return

            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            payload = {
                "chat_id": chat_id,
                "text": message.content,
                "parse_mode": "HTML",
            }

            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=payload)

                if response.status_code == 200:
                    logger.info(f"✅ Отправлено в Telegram чат {chat_id}")
                else:
                    logger.error(f"❌ Ошибка Telegram API: {response.status_code}")
                    logger.error(f"❌ Ответ API: {response.text}")
                    logger.error(f"❌ Payload: {payload}")

        except Exception as e:
            logger.error(f"Ошибка отправки в Telegram: {e}")

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
