"""
WhatsApp Interface - адаптер для WhatsApp Business Cloud API.
Полная обратная совместимость с Telegram: команды, кнопки, медиа, форматирование.
"""

import logging
import re
import hashlib
import hmac
from typing import Dict, Any, Optional, List
import httpx
from apps.agents.interfaces.base import BaseInterface, Message
from apps.agents.config import get_agents_settings
settings = get_agents_settings()
from core.files.processors import get_default_audio_processor
from apps.agents.container import get_agents_container
from core.utils.domain import PRIMARY_DOMAIN

logger = logging.getLogger(__name__)


class WhatsAppInterface(BaseInterface):
    """
    WhatsApp адаптер с полной поддержкой возможностей Telegram.
    
    Поддерживаемые возможности:
    - Текстовые сообщения с форматированием (bold, italic)
    - Команды (/start, /help, /clear)
    - Интерактивные кнопки (reply buttons, list messages)
    - Медиа: изображения, видео, аудио, документы, голосовые сообщения
    - Typing indicator
    - Статусы доставки
    - Геолокация
    """

    def __init__(self, access_token: str, platform_config: Dict[str, Any]):
        super().__init__(platform_config)
        self.access_token = access_token
        self.phone_number_id = platform_config.get("phone_number_id")
        self.business_account_id = platform_config.get("business_account_id")
        self.verify_token = platform_config.get("verify_token", "")
        self.graph_api_version = platform_config.get("graph_api_version", "v18.0")
        self.graph_api_url = platform_config.get(
            "graph_api_url", "https://graph.facebook.com"
        )
        self.display_name = platform_config.get("display_name", "WhatsApp Bot")
        container = get_agents_container()
        self._storage = container.storage

    async def handle_message(
        self, raw_data: Dict[str, Any], flow_id: str
    ) -> Optional[Message]:
        """
        Преобразует WhatsApp webhook в унифицированный Message.
        
        Поддерживает все типы сообщений WhatsApp:
        - text, image, video, audio, document, voice
        - location, contacts, sticker
        - interactive (button, list replies)
        """
        if "entry" not in raw_data:
            return None

        entry = raw_data["entry"][0] if raw_data["entry"] else None
        if not entry:
            return None

        changes = entry.get("changes", [])
        if not changes:
            return None

        value = changes[0].get("value", {})
        
        # Обработка статусов доставки (не создаем Message)
        if "statuses" in value:
            await self._handle_status_update(value["statuses"])
            return None

        # Обработка входящих сообщений
        messages = value.get("messages", [])
        if not messages:
            return None

        wa_message = messages[0]
        contacts = value.get("contacts", [])
        metadata = value.get("metadata", {})

        # Извлекаем данные отправителя
        from_number = wa_message.get("from")
        message_id = wa_message.get("id")
        timestamp = wa_message.get("timestamp")
        message_type = wa_message.get("type")
        
        logger.info(f"📞 WhatsApp webhook: получен номер '{from_number}' (тип: {type(from_number).__name__})")

        # Профиль отправителя
        profile_name = "User"
        if contacts:
            profile_name = contacts[0].get("profile", {}).get("name", "User")

        user_id = f"whatsapp:{from_number}"
        
        # Проверяем доступ пользователя
        is_allowed, error_message = self.check_user_access(from_number, profile_name)
        if not is_allowed:
            logger.warning(f"🚫 Доступ запрещен для пользователя {profile_name} ({from_number}) в flow {flow_id}")
            
            # Получаем или создаем сессию для отправки сообщения об ошибке
            temp_session_id = await self.get_or_create_session(
                user_id=from_number,
                flow_id=flow_id,
                metadata={
                    "phone_number": from_number,
                    "profile_name": profile_name,
                },
            )
            
            access_denied_message = Message(
                user_id=user_id,
                session_id=temp_session_id,
                content=error_message,
                flow_id=flow_id,
                platform="whatsapp",
                metadata={
                    "phone_number": from_number,
                    "message_id": message_id,
                },
            )
            await self.send_message(access_denied_message)
            return None
        
        # Получаем или создаем сессию
        session_id = await self.get_or_create_session(
            user_id=from_number,
            flow_id=flow_id,
            metadata={
                "phone_number": from_number,
                "phone_number_id": metadata.get("phone_number_id"),
                "display_phone_number": metadata.get("display_phone_number"),
                "profile_name": profile_name,
                "whatsapp_message_id": message_id,
            },
        )

        # Извлекаем контент в зависимости от типа сообщения
        content, files_data = await self._extract_message_content(
            wa_message, message_type, from_number
        )

        # Если нет контента и файлов - пропускаем
        if not content and not files_data:
            logger.warning(f"Пустое сообщение от {from_number}, тип: {message_type}")
            return None

        # Проверяем команды (только для текстовых сообщений)
        if message_type == "text" and content.startswith("/"):
            is_command, command_response = await self.process_command(
                content, from_number, flow_id, session_id
            )
            if is_command:
                if command_response:
                    command_message = Message(
                        user_id=user_id,
                        session_id=session_id,
                        content=command_response,
                        flow_id=flow_id,
                        platform="whatsapp",
                        metadata={
                            "phone_number": from_number,
                            "message_id": message_id,
                            "reply_to": message_id,
                        },
                    )
                    await self.send_message(command_message)
                return None

        # Обрабатываем файлы если есть
        processed_files = []
        if files_data:
            audio_files = [f for f in files_data if f["type"] in ["audio", "voice"]]
            regular_files = [f for f in files_data if f["type"] not in ["audio", "voice"]]
            
            file_messages = []
            if regular_files:
                file_messages = await self.process_files(regular_files, from_number)
            
            audio_messages = []
            if audio_files:
                audio_messages = await self.process_audio_files(audio_files, from_number)
            
            all_messages = file_messages + audio_messages
            processed_files = all_messages

            if all_messages:
                files_text = "\n\n".join(all_messages)
                if content:
                    content = f"{content}\n\n{files_text}"
                else:
                    content = files_text

        return Message(
            user_id=user_id,
            session_id=session_id,
            flow_id=flow_id,
            content=content,
            platform="whatsapp",
            metadata={
                "phone_number": from_number,
                "message_id": message_id,
                "profile_name": profile_name,
                "message_type": message_type,
                "timestamp": timestamp,
            },
            files=processed_files,
        )

    async def _extract_message_content(
        self, wa_message: Dict[str, Any], message_type: str, user_id: str
    ) -> tuple[str, List[Dict[str, Any]]]:
        """Извлекает контент и медиа из WhatsApp сообщения"""
        content = ""
        files_data = []

        if message_type == "text":
            content = wa_message.get("text", {}).get("body", "")

        elif message_type == "image":
            image_data = wa_message.get("image", {})
            caption = image_data.get("caption", "")
            media_id = image_data.get("id")
            mime_type = image_data.get("mime_type", "image/jpeg")
            
            files_data.append({
                "type": "image",
                "media_id": media_id,
                "mime_type": mime_type,
                "caption": caption,
            })
            
            if caption:
                content = caption

        elif message_type == "video":
            video_data = wa_message.get("video", {})
            caption = video_data.get("caption", "")
            media_id = video_data.get("id")
            mime_type = video_data.get("mime_type", "video/mp4")
            
            files_data.append({
                "type": "video",
                "media_id": media_id,
                "mime_type": mime_type,
                "caption": caption,
            })
            
            if caption:
                content = caption

        elif message_type == "audio":
            audio_data = wa_message.get("audio", {})
            media_id = audio_data.get("id")
            mime_type = audio_data.get("mime_type", "audio/ogg; codecs=opus")
            
            files_data.append({
                "type": "audio",
                "media_id": media_id,
                "mime_type": mime_type,
            })

        elif message_type == "voice":
            voice_data = wa_message.get("voice", {})
            media_id = voice_data.get("id")
            mime_type = voice_data.get("mime_type", "audio/ogg; codecs=opus")
            
            files_data.append({
                "type": "voice",
                "media_id": media_id,
                "mime_type": mime_type,
            })

        elif message_type == "document":
            doc_data = wa_message.get("document", {})
            caption = doc_data.get("caption", "")
            filename = doc_data.get("filename", "document")
            media_id = doc_data.get("id")
            mime_type = doc_data.get("mime_type", "application/octet-stream")
            
            files_data.append({
                "type": "document",
                "media_id": media_id,
                "mime_type": mime_type,
                "filename": filename,
                "caption": caption,
            })
            
            if caption:
                content = caption

        elif message_type == "location":
            location = wa_message.get("location", {})
            latitude = location.get("latitude")
            longitude = location.get("longitude")
            name = location.get("name", "")
            address = location.get("address", "")
            
            content = f"📍 Локация: {name}\n" if name else "📍 Локация\n"
            if address:
                content += f"Адрес: {address}\n"
            content += f"Координаты: {latitude}, {longitude}"

        elif message_type == "contacts":
            contacts = wa_message.get("contacts", [])
            content = "👤 Контакты:\n"
            for contact in contacts:
                name = contact.get("name", {}).get("formatted_name", "Неизвестно")
                phones = contact.get("phones", [])
                content += f"\n{name}"
                if phones:
                    content += f": {phones[0].get('phone', '')}"

        elif message_type == "sticker":
            sticker_data = wa_message.get("sticker", {})
            media_id = sticker_data.get("id")
            content = "🎨 Стикер отправлен"

        elif message_type == "button":
            button_data = wa_message.get("button", {})
            button_text = button_data.get("text", "")
            button_payload = button_data.get("payload", "")
            content = button_payload or button_text

        elif message_type == "interactive":
            interactive = wa_message.get("interactive", {})
            interactive_type = interactive.get("type")
            
            if interactive_type == "button_reply":
                button_reply = interactive.get("button_reply", {})
                content = button_reply.get("title", "")
                
            elif interactive_type == "list_reply":
                list_reply = interactive.get("list_reply", {})
                content = list_reply.get("title", "")

        return content, files_data

    async def send_message(self, message: Message):
        """
        Отправляет сообщение в WhatsApp с полной поддержкой возможностей Telegram.
        
        Поддерживает:
        - Текст с форматированием
        - Кнопки (interactive messages)
        - Медиа (изображения, видео, аудио, документы)
        - Reply на сообщения
        """
        phone_number = message.metadata.get("phone_number")
        if not phone_number:
            raise ValueError("phone_number обязателен в metadata для отправки WhatsApp сообщения")

        # Извлекаем аудиофайлы из сообщения
        clean_text, audio_files = self.extract_outgoing_audio_from_message(message.content)
        
        # Проверяем наличие кнопок в metadata
        buttons = message.metadata.get("buttons", [])
        
        if buttons:
            # Отправляем интерактивное сообщение с кнопками
            await self._send_interactive_message(phone_number, clean_text, buttons, message.metadata)
        elif clean_text.strip():
            # Отправляем текстовое сообщение
            await self._send_text_message(phone_number, clean_text, message.metadata)
        
        # Отправляем аудиофайлы
        for audio_info in audio_files:
            await self._send_audio_message(phone_number, audio_info, message.metadata)

    async def _send_text_message(
        self, 
        phone_number: str, 
        text: str, 
        metadata: Dict[str, Any]
    ):
        """Отправляет текстовое сообщение с поддержкой форматирования"""
        
        logger.info(f"📤 WhatsApp отправка на номер: '{phone_number}' (тип: {type(phone_number).__name__})")
        
        # Конвертируем Markdown в WhatsApp форматирование
        formatted_text = self._convert_markdown_to_whatsapp(text)
        
        url = f"{self.graph_api_url}/{self.graph_api_version}/{self.phone_number_id}/messages"
        
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": phone_number,
            "type": "text",
            "text": {
                "preview_url": True,
                "body": formatted_text
            }
        }
        
        # Добавляем context для reply если есть
        reply_to_message_id = metadata.get("reply_to")
        if reply_to_message_id:
            payload["context"] = {
                "message_id": reply_to_message_id
            }
        
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            
            if response.status_code == 200:
                result = response.json()
                message_id = result.get("messages", [{}])[0].get("id")
                logger.info(f"✅ WhatsApp сообщение отправлено: {message_id} → {phone_number}")
            else:
                logger.error(f"❌ Ошибка отправки в WhatsApp: {response.status_code}")
                logger.error(f"❌ Ответ API: {response.text}")
                
                if response.status_code == 400 and phone_number.startswith("7"):
                    try:
                        error_data = response.json()
                        error_code = error_data.get("error", {}).get("code")
                        
                        if error_code == 131030:
                            logger.warning(f"⚠️ Номер не в списке, пробуем с префиксом 78: {phone_number}")
                            alternative_number = "78" + phone_number[1:]
                            payload["to"] = alternative_number
                            
                            retry_response = await client.post(url, json=payload, headers=headers)
                            
                            if retry_response.status_code == 200:
                                result = retry_response.json()
                                message_id = result.get("messages", [{}])[0].get("id")
                                logger.info(f"✅ WhatsApp сообщение отправлено (через 78): {message_id} → {alternative_number}")
                                return
                            else:
                                logger.error(f"❌ Retry с {alternative_number} тоже не удался: {retry_response.status_code}")
                    except Exception as e:
                        logger.error(f"❌ Ошибка retry логики: {e}")
                
                raise httpx.HTTPStatusError(
                    f"WhatsApp API ошибка отправки текста: {response.status_code} - {response.text[:200]}",
                    request=response.request,
                    response=response
                )

    async def _send_interactive_message(
        self,
        phone_number: str,
        text: str,
        buttons: List[Dict[str, str]],
        metadata: Dict[str, Any]
    ):
        """
        Отправляет интерактивное сообщение с кнопками.
        
        Поддерживает до 3 кнопок (reply buttons) или список (list message).
        """
        
        url = f"{self.graph_api_url}/{self.graph_api_version}/{self.phone_number_id}/messages"
        
        # WhatsApp поддерживает до 3 reply buttons
        if len(buttons) <= 3:
            # Reply buttons
            interactive_buttons = []
            for idx, button in enumerate(buttons[:3]):
                button_id = button.get("id", f"btn_{idx}")
                button_title = button.get("text", button.get("title", f"Button {idx+1}"))
                
                interactive_buttons.append({
                    "type": "reply",
                    "reply": {
                        "id": button_id,
                        "title": button_title[:20]  # Максимум 20 символов
                    }
                })
            
            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": phone_number,
                "type": "interactive",
                "interactive": {
                    "type": "button",
                    "body": {
                        "text": text[:1024]  # Максимум 1024 символа
                    },
                    "action": {
                        "buttons": interactive_buttons
                    }
                }
            }
        else:
            # List message (для более 3 кнопок)
            list_sections = [{
                "title": "Опции",
                "rows": []
            }]
            
            for idx, button in enumerate(buttons[:10]):  # Максимум 10 элементов
                button_id = button.get("id", f"btn_{idx}")
                button_title = button.get("text", button.get("title", f"Option {idx+1}"))
                button_description = button.get("description", "")
                
                list_sections[0]["rows"].append({
                    "id": button_id,
                    "title": button_title[:24],  # Максимум 24 символа
                    "description": button_description[:72] if button_description else ""  # Максимум 72
                })
            
            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": phone_number,
                "type": "interactive",
                "interactive": {
                    "type": "list",
                    "body": {
                        "text": text[:1024]
                    },
                    "action": {
                        "button": "Выбрать",
                        "sections": list_sections
                    }
                }
            }
        
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            
            if response.status_code == 200:
                result = response.json()
                message_id = result.get("messages", [{}])[0].get("id")
                logger.info(f"✅ WhatsApp интерактивное сообщение отправлено: {message_id}")
            else:
                logger.error(f"❌ Ошибка отправки интерактивного сообщения: {response.status_code}")
                logger.error(f"❌ Ответ API: {response.text}")
                raise httpx.HTTPStatusError(
                    f"WhatsApp API ошибка отправки интерактивного сообщения: {response.status_code} - {response.text[:200]}",
                    request=response.request,
                    response=response
                )

    async def _send_audio_message(
        self,
        phone_number: str,
        audio_info: Dict[str, Any],
        metadata: Dict[str, Any]
    ):
        """Отправляет аудиофайл"""
        audio_processor = await get_default_audio_processor()
        audio_record = await audio_processor.get_audio_record(audio_info["audio_id"])
        
        if not audio_record:
            raise ValueError(f"Аудиофайл {audio_info['audio_id']} не найден в системе")

        # Скачиваем аудио из S3
        s3_client = await audio_processor._get_s3_client()
        audio_data = await s3_client.download_bytes(audio_record.s3_key)
        
        if not audio_data:
            raise ValueError(f"Не удалось скачать аудиофайл {audio_record.audio_id} из S3")

        # Загружаем медиа в WhatsApp
        media_id = await self._upload_media(audio_data, audio_record.content_type)
        
        if not media_id:
            raise ValueError("Не удалось загрузить аудио в WhatsApp API")

        # Отправляем аудио
        url = f"{self.graph_api_url}/{self.graph_api_version}/{self.phone_number_id}/messages"
        
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": phone_number,
            "type": "audio",
            "audio": {
                "id": media_id
            }
        }
        
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            
            if response.status_code == 200:
                logger.info(f"🎵 WhatsApp аудио отправлено в {phone_number}")
            else:
                raise httpx.HTTPStatusError(
                    f"WhatsApp API ошибка отправки аудио: {response.status_code} - {response.text[:200]}",
                    request=response.request,
                    response=response
                )

    async def _upload_media(self, media_data: bytes, mime_type: str) -> Optional[str]:
        """Загружает медиафайл в WhatsApp и возвращает media_id"""
        url = f"{self.graph_api_url}/{self.graph_api_version}/{self.phone_number_id}/media"
        
        headers = {
            "Authorization": f"Bearer {self.access_token}",
        }
        
        files = {
            "file": ("media", media_data, mime_type),
            "messaging_product": (None, "whatsapp"),
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, headers=headers, files=files)
            
            if response.status_code == 200:
                result = response.json()
                media_id = result.get("id")
                if not media_id:
                    raise ValueError("WhatsApp API не вернул media_id после загрузки")
                logger.info(f"✅ Медиа загружено в WhatsApp: {media_id}")
                return media_id
            else:
                raise httpx.HTTPStatusError(
                    f"WhatsApp API ошибка загрузки медиа: {response.status_code} - {response.text[:200]}",
                    request=response.request,
                    response=response
                )

    async def send_typing_notification(self, session_id: str, is_typing: bool):
        """
        Отправка индикатора "печатает" в WhatsApp.
        WhatsApp использует mark_message_as_read для похожего эффекта.
        """
        parts = session_id.split(":")
        if len(parts) < 2 or parts[0] != "whatsapp":
            logger.warning(f"Неправильный формат session_id для WhatsApp: {session_id}")
            return
        
        phone_number = parts[1]

        if is_typing:
            # В WhatsApp нет прямого typing indicator, но можно использовать read receipt
            # Это косвенно показывает что бот активен
            logger.info(f"💬 WhatsApp typing indicator (симуляция) для {phone_number}")

    async def _process_single_file(
        self, file_data: Dict[str, Any], user_id: str, file_processor
    ):
        """Обрабатывает один файл из WhatsApp"""
        media_id = file_data.get("media_id")
        if not media_id:
            raise ValueError("media_id обязателен в file_data для обработки файла WhatsApp")

        # Получаем URL медиа от WhatsApp
        media_url = await self._get_media_url(media_id)
        if not media_url:
            raise ValueError(f"Не удалось получить URL медиа {media_id} от WhatsApp API")

        # Обрабатываем файл через процессор
        filename = file_data.get("filename", f"whatsapp_{file_data['type']}_{media_id}")
        
        file_record = await file_processor.process_file_from_url(
            file_url=media_url,
            original_name=filename,
            uploaded_by=user_id,
            metadata={
                "whatsapp_media_id": media_id,
                "whatsapp_message_type": file_data["type"],
                "platform": "whatsapp",
                "caption": file_data.get("caption", ""),
            },
            tags=["whatsapp", file_data["type"]],
        )

        return file_record

    async def _process_single_audio_file(
        self, audio_data: Dict[str, Any], user_id: str, audio_processor
    ):
        """Обрабатывает один аудиофайл из WhatsApp"""
        media_id = audio_data.get("media_id")
        if not media_id:
            raise ValueError("media_id обязателен в audio_data для обработки аудио WhatsApp")

        # Получаем URL аудио от WhatsApp
        audio_url = await self._get_media_url(media_id)
        if not audio_url:
            raise ValueError(f"Не удалось получить URL аудио {media_id} от WhatsApp API")

        # Определяем тип и имя файла
        audio_type = audio_data.get("type", "audio")
        content_type = audio_data.get("mime_type", "audio/ogg; codecs=opus")
        file_name = f"whatsapp_{audio_type}_{media_id[:8]}.ogg"

        # Обрабатываем аудио через AudioProcessor с распознаванием
        audio_record = await audio_processor.process_audio_from_url(
            audio_url=audio_url,
            original_name=file_name,
            content_type=content_type,
            uploaded_by=user_id,
            auto_recognize=True,
            metadata={
                "whatsapp_media_id": media_id,
                "whatsapp_message_type": audio_type,
                "platform": "whatsapp",
            },
            tags=["whatsapp", audio_type],
        )

        return audio_record

    async def _get_media_url(self, media_id: str) -> Optional[str]:
        """Получает URL для скачивания медиа от WhatsApp"""
        url = f"{self.graph_api_url}/{self.graph_api_version}/{media_id}"
        headers = {
            "Authorization": f"Bearer {self.access_token}"
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=headers)
            
            if response.status_code != 200:
                raise httpx.HTTPStatusError(
                    f"WhatsApp API вернул ошибку при получении медиа URL: {response.status_code} - {response.text[:200]}",
                    request=response.request,
                    response=response
                )

            data = response.json()
            media_url = data.get("url")
            
            if not media_url:
                raise ValueError(f"WhatsApp API не вернул URL для медиа {media_id}")
            
            return media_url

    async def _handle_status_update(self, statuses: List[Dict[str, Any]]):
        """Обрабатывает обновления статусов сообщений (sent, delivered, read, failed)"""
        for status in statuses:
            message_id = status.get("id")
            status_value = status.get("status")
            recipient_id = status.get("recipient_id")
            
            logger.info(f"📬 WhatsApp статус: {message_id} → {status_value} ({recipient_id})")
            
            # Здесь можно добавить логику сохранения статусов в БД
            if status_value == "failed":
                errors = status.get("errors", [])
                for error in errors:
                    logger.error(f"❌ WhatsApp ошибка: {error.get('code')} - {error.get('title')}")

    def _convert_markdown_to_whatsapp(self, text: str) -> str:
        """
        Конвертирует Markdown в WhatsApp форматирование.
        
        WhatsApp поддерживает:
        - *bold* для жирного
        - _italic_ для курсива
        - ~strikethrough~ для зачеркнутого
        - ```monospace``` для моноширинного
        """
        # Заменяем **bold** на *bold*
        text = re.sub(r'\*\*(.*?)\*\*', r'*\1*', text)
        
        # Заменяем __italic__ на _italic_
        text = re.sub(r'__(.*?)__', r'_\1_', text)
        
        # Уже есть поддержка ~strikethrough~
        
        # ```code``` уже поддерживается
        
        return text

    @staticmethod
    async def get_access_token_for_flow(
        flow_id: str, platform_config: Dict[str, Any]
    ) -> Optional[str]:
        """
        Получает access token для flow из конфигурации.
        Поддерживает ссылки на переменные (@var:key).
        """
        token_value = platform_config.get("access_token")
        
        if not token_value:
            raise ValueError(f"No access_token configured for flow {flow_id}")
        
        variables_service = get_agents_container().variables_service
        resolved_token = await variables_service.resolve(token_value)
        logger.info(f"✅ WhatsApp токен резолвнут для flow {flow_id}")
        return resolved_token

    @staticmethod
    async def verify_webhook_token(verify_token: str, expected_token: str) -> bool:
        """Проверяет verify token для webhook"""
        return verify_token == expected_token

    @staticmethod
    async def verify_webhook_signature(
        payload: bytes, signature: str, app_secret: str
    ) -> bool:
        """
        Проверяет подпись webhook от WhatsApp (опционально).
        Использует HMAC SHA256.
        """
        expected_signature = hmac.new(
            app_secret.encode(),
            payload,
            hashlib.sha256
        ).hexdigest()
        
        # Signature приходит в формате "sha256=..."
        if signature.startswith("sha256="):
            signature = signature[7:]
        
        return hmac.compare_digest(signature, expected_signature)

    @classmethod
    async def register(
        cls,
        flow_id: str,
        username: str,
        platform_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Регистрирует WhatsApp для flow:
        1. Резолвит access_token
        2. Проверяет phone_number_id
        3. Устанавливает webhook (для production)
        4. Возвращает информацию о регистрации
        """
        # Получаем access token
        access_token = await cls.get_access_token_for_flow(flow_id, platform_config)
        if not access_token:
            raise ValueError(f"Access token not found for {flow_id}")
        
        phone_number_id = platform_config.get("phone_number_id")
        if not phone_number_id:
            raise ValueError("phone_number_id not found in platform_config")
        
        # Проверяем токен через API
        graph_api_url = platform_config.get("graph_api_url", "https://graph.facebook.com")
        graph_api_version = platform_config.get("graph_api_version", "v18.0")
        
        url = f"{graph_api_url}/{graph_api_version}/{phone_number_id}"
        headers = {"Authorization": f"Bearer {access_token}"}
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers=headers)
            
            if response.status_code != 200:
                raise httpx.HTTPStatusError(
                    f"Невалидный phone_number_id или access_token: {response.status_code} - {response.text[:200]}",
                    request=response.request,
                    response=response
                )
            
            phone_data = response.json()
            display_phone_number = phone_data.get("display_phone_number", "Unknown")
            logger.info(f"📱 WhatsApp номер: {display_phone_number}")
        
        from core.context import get_context
        context = get_context()
        if not context or not context.active_company:
            raise ValueError("No active company in context")
        
        flow_key = f"company:{context.active_company.company_id}:flow:{flow_id}"
        
        # В production устанавливаем webhook
        if settings.server.env != "local":
            # Webhook URL для WhatsApp
            webhook_url = f"https://{PRIMARY_DOMAIN}/api/v1/webhook/whatsapp/{flow_key}"
            
            # Здесь можно добавить автоматическую установку webhook через API
            # Но обычно это делается вручную в Meta for Developers
            
            logger.info(f"📍 WhatsApp webhook URL: {webhook_url}")
            logger.info("⚠️  Настройте webhook вручную в Meta for Developers")
            
            return {
                "success": True,
                "platform": "whatsapp",
                "mode": "webhook",
                "phone_number": display_phone_number,
                "webhook_url": webhook_url,
                "flow_key": flow_key,
                "note": "Configure webhook manually in Meta for Developers"
            }
        else:
            # Local development - используем ngrok или подобное
            logger.info("🔧 Local режим: используйте ngrok для webhook")
            
            return {
                "success": True,
                "platform": "whatsapp",
                "mode": "local",
                "phone_number": display_phone_number,
                "flow_key": flow_key,
                "note": "Use ngrok or similar for local webhook testing"
            }

    async def setup_commands(self) -> bool:
        """
        WhatsApp не поддерживает установку команд через API.
        Команды обрабатываются на уровне BaseInterface.process_command().
        """
        logger.info("📋 WhatsApp команды обрабатываются автоматически")
        return True

