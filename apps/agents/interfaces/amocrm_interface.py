"""
AmoCRM Interface - адаптер для обработки webhook'ов от AmoCRM.
Создается на лету при получении webhook.
"""

import logging
from typing import Dict, Any, Optional, List
import json

from langchain_core.messages import HumanMessage, AIMessage
from apps.agents.interfaces.base import BaseInterface, Message
from apps.agents.clients.amo_crm_integration import get_amocrm_client
from apps.agents.config import get_agents_settings
settings = get_agents_settings()
from apps.agents.services.state_manager import get_state_manager
from apps.agents.container import get_agents_container
from apps.agents.services.tracing.decorators import trace_span
from apps.agents.models.trace_models import SpanType

logger = logging.getLogger(__name__)


class AmoCRMInterface(BaseInterface):
    """
    Простой AmoCRM адаптер.
    Создается на лету для каждого webhook запроса.
    """

    def __init__(self, scope_id: str, subdomain: str):
        platform_config = {"subdomain": subdomain, "scope_id": scope_id}
        super().__init__(platform_config)
        self.scope_id = scope_id
        self.subdomain = subdomain
        container = get_agents_container()
        self._storage = container.storage

    @trace_span(
        name="amocrm_interface.handle_message",
        span_type=SpanType.OTHER,
        metadata={"component": "amocrm_interface", "operation": "handle_message"}
    )
    async def handle_message(
        self, raw_data: Dict[str, Any], flow_id: str
    ) -> Optional[Message]:
        """
        Преобразует AmoCRM webhook в Message

        raw_data - это dict с ключами типа:
        - message[add][0][chat_id]
        - message[add][0][text]
        - message[add][0][author][name]
        - etc.
        """
        message_type = raw_data.get("message[add][0][type]")
        author_type = raw_data.get("message[add][0][author][type]")

        if message_type != "incoming":
            logger.info(f"Пропускаем: не входящее сообщение от клиента (type={message_type}, author={author_type})")
            return None

        chat_id = raw_data.get("message[add][0][chat_id]", "")
        message_id = raw_data.get("message[add][0][id]", "")
        text = raw_data.get("message[add][0][text]", "")
        author_id = raw_data.get("message[add][0][author][id]", "")
        author_name = raw_data.get("message[add][0][author][name]", "Клиент")
        talk_id = raw_data.get("message[add][0][talk_id]", "")
        contact_id = raw_data.get("message[add][0][contact_id]", "")
        element_id = raw_data.get("message[add][0][element_id]", "")
        entity_id = raw_data.get("message[add][0][entity_id]", "")
        entity_type = raw_data.get("message[add][0][entity_type]", "")
        origin = raw_data.get("message[add][0][origin]", "")

        if not chat_id or not text:
            logger.info("Пропускаем: нет chat_id или текста")
            return None

        access_token = getattr(settings, 'amocrm', None) and settings.amocrm.access_token
        if not access_token:
            raise ValueError("AMOCRM_ACCESS_TOKEN не настроен в settings - невозможно работать с AmoCRM")

        source_id = None

        client = get_amocrm_client(subdomain=self.subdomain, access_token=access_token)
        chat_history = await client.get_chat_history(chat_id=chat_id)
        logger.info(f"🔍 Получена история чата: {len(chat_history)} сообщений")

        user_id = f"amocrm:{chat_id}"

        session_id = await self.get_or_create_session(
            user_id=user_id,
            flow_id=flow_id,
            metadata={
                "chat_id": chat_id,
                "scope_id": self.scope_id,
                "subdomain": self.subdomain,
                "author_name": author_name,
                "contact_id": contact_id,
                "talk_id": talk_id,
                "element_id": element_id,
                "entity_id": entity_id,
                "entity_type": entity_type,
                "origin": origin,
                "source_id": source_id,
            },
        )

        logger.info(
            f"💬 Входящее сообщение от {author_name} "
            f"(chat_id={chat_id}, session={session_id})"
        )

        # Импортируем историю чата в checkpointer
        if chat_history:
            await self._add_chat_history_to_checkpointer(session_id, chat_history, chat_id)

        return Message(
            user_id=user_id,
            session_id=session_id,
            flow_id=flow_id,
            content=text,
            platform="amocrm",
            metadata={
                "chat_id": chat_id,
                "message_id": message_id,
                "talk_id": talk_id,
                "contact_id": contact_id,
                "author_id": author_id,
                "author_name": author_name,
                "scope_id": self.scope_id,
                "subdomain": self.subdomain,
                "element_id": element_id,
                "entity_id": entity_id,
                "entity_type": entity_type,
                "origin": origin,
                "source_id": source_id,
            },
        )

    @trace_span(
        name="amocrm_interface.send_message",
        span_type=SpanType.OTHER,
        metadata={"component": "amocrm_interface", "operation": "send_message"}
    )
    async def send_message(self, message: Message):
        """Отправка сообщения в AmoCRM через Internal API"""
        chat_id = message.metadata.get("chat_id")
        scope_id = message.metadata.get("scope_id") or self.scope_id

        if not chat_id:
            logger.error("❌ Не указан chat_id в metadata сообщения")
            return

        access_token = getattr(settings, 'amocrm', None) and settings.amocrm.access_token
        if not access_token:
            logger.error("❌ AMOCRM_ACCESS_TOKEN не настроен в settings")
            return

        client = get_amocrm_client(subdomain=self.subdomain, access_token=access_token)

        entity_id = message.metadata.get("entity_id")
        entity_type = message.metadata.get("entity_type")
        crm_entity_type = 2 if entity_type == "lead" else 12

        crm_entity_id = int(entity_id) if entity_id else None

        contact_id = message.metadata.get("contact_id")
        crm_contact_id = int(contact_id) if contact_id else None

        talk_id = message.metadata.get("talk_id")
        crm_dialog_id = int(talk_id) if talk_id else None

        await client.send_message_internal(
            chat_id=chat_id,
            text=message.content,
            scope_id=scope_id,
            crm_entity_id=crm_entity_id,
            crm_entity_type=crm_entity_type,
            crm_contact_id=crm_contact_id,
            crm_dialog_id=crm_dialog_id,
            recipient_id=message.metadata.get("author_id"),
            persona_name="AI Assistant",
            persona_avatar="https://images.amocrm.ru/frontend/images/interface/avatars/7.jpeg",
        )

        logger.info(
            f"✅ Сообщение отправлено в AmoCRM чат {chat_id}: {message.content[:100]}"
        )

    def _import_chat_history(self, chat_history: List[Dict[str, Any]], chat_id: str) -> List[Dict[str, Any]]:
        """
        Импортирует всю историю сообщений из чата и возвращает в формате JSON задачи.
        Этот метод оставлен для обратной совместимости, но теперь используется checkpointer.
        """
        messages = []
        for message_data in chat_history:
            external_id = message_data.get("id")
            if not external_id:
                continue

            # Определяем тип сообщения
            author_type = message_data.get("author", {}).get("type", "")
            if author_type == "employee":
                message_type = "ai"
            else:
                message_type = "human"

            import uuid
            internal_id = str(uuid.uuid4())

            message = {
                "id": internal_id,
                "external_id": external_id,
                "name": None,
                "type": message_type,
                "content": message_data.get("text", ""),
                "example": False,
                "additional_kwargs": {},
                "response_metadata": {}
            }

            messages.append(message)

        logger.info(f"📚 Импортирована история чата {chat_id}: {len(messages)} сообщений")
        return messages

    @trace_span(
        name="amocrm_interface._add_chat_history_to_checkpointer",
        span_type=SpanType.OTHER,
        metadata={"component": "amocrm_interface", "operation": "import_chat_history"}
    )
    async def _add_chat_history_to_checkpointer(self, session_id: str, chat_history: List[Dict[str, Any]], chat_id: str):
        """
        Добавляет историю чата в state_manager через session_id.

        Args:
            session_id: ID сессии (используется как thread_id для checkpointer)
            chat_history: История сообщений из AmoCRM
            chat_id: ID чата для логирования
        """
        try:
            state_manager = await get_state_manager()
            
            # Получаем текущее состояние
            current_state = await state_manager.get_or_create_session(session_id)

            # Создаем langchain сообщения из истории чата
            langchain_messages = []
            for message_data in chat_history:
                external_id = message_data.get("id")
                if not external_id:
                    continue

                author_type = message_data.get("author", {}).get("type", "")
                text = message_data.get("text", "")
                author_name = message_data.get("author", {}).get("name", "Неизвестный")

                if not text:
                    continue

                # Определяем тип сообщения
                if author_type == "employee":
                    # Сообщение от сотрудника - считаем как AI
                    langchain_message = AIMessage(
                        content=text,
                        additional_kwargs={
                            "external_id": external_id,
                            "author_name": author_name,
                            "chat_id": chat_id,
                            "imported_from_amocrm": True
                        }
                    )
                else:
                    # Сообщение от клиента - считаем как Human
                    langchain_message = HumanMessage(
                        content=text,
                        additional_kwargs={
                            "external_id": external_id,
                            "author_name": author_name,
                            "chat_id": chat_id,
                            "imported_from_amocrm": True
                        }
                    )

                langchain_messages.append(langchain_message)

            if not langchain_messages:
                logger.info(f"📭 Нет сообщений для импорта в state_manager для чата {chat_id}")
                return

            # Добавляем сообщения к существующим
            existing_messages = current_state.get("messages", [])
            current_state["messages"] = existing_messages + langchain_messages

            # Сохраняем в state_manager
            await state_manager.save_session(current_state)

            logger.info(f"✅ Импортировано {len(langchain_messages)} сообщений в state_manager для сессии {session_id}")

        except Exception as e:
            logger.error(f"❌ Ошибка импорта истории чата в state_manager: {e}", exc_info=True)



    @trace_span(
        name="amocrm_interface.send_typing_notification",
        span_type=SpanType.OTHER,
        metadata={"component": "amocrm_interface", "operation": "send_typing_notification"}
    )
    async def send_typing_notification(self, session_id: str, is_typing: bool):
        """Отправка уведомления о печати в AmoCRM"""

        # Получаем метаданные сессии
        session = await self.get_session(session_id)
        if not session:
            logger.warning(f"❌ Сессия {session_id} не найдена")
            return

        chat_id = session.metadata.get("chat_id")
        talk_id = session.metadata.get("talk_id")

        if not chat_id:
            logger.warning(f"❌ chat_id не найден в метаданных сессии {session_id}")
            return

        if not talk_id:
            logger.warning(f"❌ talk_id не найден в метаданных сессии {session_id}")
            return

        # Получаем клиент AmoCRM
        access_token = getattr(settings, 'amocrm', None) and settings.amocrm.access_token
        if not access_token:
            logger.error("❌ AMOCRM_ACCESS_TOKEN не настроен в settings")
            return

        client = get_amocrm_client(subdomain=self.subdomain, access_token=access_token)

        if is_typing:
            # Запускаем индикатор "печатает" с автоматической отменой через 5 секунд
            await client.start_typing_indicator(
                chat_id=chat_id,
                crm_dialog_id=int(talk_id),
                max_duration=5.0
            )
            logger.info(f"🔵 Запущен индикатор 'печатает' в чат {chat_id} (сессия {session_id})")
        else:
            # Останавливаем индикатор "печатает"
            await client.stop_typing_indicator(chat_id)
            logger.info(f"🔴 Остановлен индикатор 'печатает' в чат {chat_id} (сессия {session_id})")




    @staticmethod
    @trace_span(
        name="amocrm_interface.get_credentials_for_flow",
        span_type=SpanType.OTHER,
        metadata={"component": "amocrm_interface", "operation": "get_credentials"}
    )
    async def get_credentials_for_flow(
        flow_id: str, platform_config: Dict[str, Any]
    ) -> Optional[Dict[str, str]]:
        """
        Получает учетные данные AmoCRM для flow из БД

        Возвращает dict с ключами:
        - scope_id
        - secret_key
        - account_id
        - bot_amojo_id
        """
        subdomain = platform_config.get("subdomain")
        if not subdomain:
            logger.error(f"Не указан subdomain в конфигурации flow {flow_id}")
            return None

        credentials_key = f"credentials:amocrm:{subdomain}"
        container = get_agents_container()
        _storage = container.storage._storage
        credentials_json = await _storage.get(credentials_key, force_global=True)

        if credentials_json:
            credentials = json.loads(credentials_json)
            logger.info(f"✅ Найдены учетные данные AmoCRM для {subdomain}")
            return credentials
        else:
            logger.error(f"❌ Не найдены учетные данные в БД: {credentials_key}")
            return None
