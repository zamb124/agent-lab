"""
Webhook эндпоинты для AmoCRM интеграции.

Обрабатывает входящие сообщения от клиентов и автоматически отвечает от имени бота.
"""

import logging
from datetime import datetime
from typing import Any, Dict, Optional
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel

from app.clients.amo_crm_integration import get_amocrm_client
from app.core.config import settings
from app.core.storage import Storage
from app.interfaces.amocrm_interface import AmoCRMInterface

router = APIRouter()
logger = logging.getLogger(__name__)


def fix_encoding(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Исправляет проблемы с кодировкой в данных webhook.

    AmoCRM иногда отправляет UTF-8 данные, которые FastAPI декодирует как Latin-1.
    Эта функция перекодирует строки обратно в UTF-8.

    Example:
        >>> broken = 'Ð¯ Ñ\\x80Ð¾Ð´Ð¸Ð»Ñ\\x8cÑ\\x81Ñ\\x8f'
        >>> fixed = fix_encoding({'text': broken})
        >>> fixed['text']
        'Я родился'
    """
    fixed_data = {}
    for key, value in data.items():
        if isinstance(value, str):
            try:
                fixed_value = value.encode('latin-1').decode('utf-8')
                if fixed_value != value:
                    logger.debug(f"Исправлена кодировка для {key}: {value[:50]} -> {fixed_value[:50]}")
                fixed_data[key] = fixed_value
            except (UnicodeDecodeError, UnicodeEncodeError):
                fixed_data[key] = value
        else:
            fixed_data[key] = value
    return fixed_data


class WebhookMessage(BaseModel):
    """Модель входящего сообщения из вебхука"""
    chat_id: str
    message_id: str
    contact_id: str
    text: Optional[str] = None
    author_id: str
    author_name: str
    author_type: str
    talk_id: str
    origin: str


@router.post("/message")
async def handle_message_webhook(request: Request):
    """
    Обработчик вебхука для входящих сообщений от AmoCRM (хук сообщения v2)

    Получает сообщение от клиента и автоматически отвечает от имени бота.
    Проверяет, не отвечал ли менеджер недавно, чтобы не мешать живому общению.

    Args:
        request: Объект запроса FastAPI с данными вебхука

    Returns:
        Статус обработки
    """
    try:
        form_data = await request.form()
        payload = fix_encoding(dict(form_data))

        logger.info("📩 Получен вебхук от AmoCRM")
        logger.info(f"Payload: {payload}")

        scope_id = payload.get("account[id]")
        if not scope_id:
            logger.error("❌ Не указан scope_id (account[id]) в вебхуке")
            return {"status": "error", "reason": "missing_scope_id"}

        logger.info(f"📋 scope_id={scope_id}")

        if not _is_incoming_message(payload):
            logger.info("ℹ️  Пропускаем: не входящее сообщение от клиента")
            return {"status": "ignored", "reason": "not_incoming_message"}

        message_data = _extract_message_data(payload)
        if not message_data:
            logger.warning("⚠️  Не удалось извлечь данные сообщения из вебхука")
            return {"status": "error", "reason": "invalid_payload"}

        logger.info(
            f"💬 Входящее сообщение от {message_data.author_name} "
            f"(chat_id={message_data.chat_id}, text={message_data.text})"
        )

        subdomain = payload.get("account[subdomain]")
        if not subdomain:
            logger.error("❌ Не указан subdomain в вебхуке")
            return {"status": "error", "reason": "missing_subdomain"}

        should_reply, reason = await _should_bot_reply(
            subdomain=subdomain,
            talk_id=message_data.talk_id,
            author_type=message_data.author_type
        )

        if not should_reply:
            logger.info(f"🚫 Бот не отвечает: {reason}")
            return {"status": "skipped", "reason": reason}

        await _send_bot_reply(
            message_data=message_data
        )

        logger.info(f"✅ Ответ успешно отправлен в чат {message_data.chat_id}")

        return {"status": "success", "message": "Reply sent"}

    except Exception as e:
        logger.error(f"❌ Ошибка обработки вебхука: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Webhook processing error: {str(e)}")


def _is_incoming_message(payload: Dict[str, Any]) -> bool:
    """Проверяет, является ли сообщение входящим от клиента"""
    message_type = payload.get("message[add][0][type]")
    author_type = payload.get("message[add][0][author][type]")

    return message_type == "incoming" and author_type == "external"


def _extract_message_data(payload: Dict[str, Any]) -> Optional[WebhookMessage]:
    """Извлекает данные сообщения из вебхука"""
    try:
        return WebhookMessage(
            chat_id=payload.get("message[add][0][chat_id]", ""),
            message_id=payload.get("message[add][0][id]", ""),
            contact_id=payload.get("message[add][0][contact_id]", ""),
            text=payload.get("message[add][0][text]"),
            author_id=payload.get("message[add][0][author][id]", ""),
            author_name=payload.get("message[add][0][author][name]", ""),
            author_type=payload.get("message[add][0][author][type]", ""),
            talk_id=payload.get("message[add][0][talk_id]", ""),
            origin=payload.get("message[add][0][origin]", "")
        )
    except Exception as e:
        logger.error(f"Ошибка извлечения данных сообщения: {e}")
        return None


async def _should_bot_reply(
    subdomain: str,
    talk_id: str,
    author_type: str
) -> tuple[bool, str]:
    """
    Проверяет, должен ли бот отвечать на сообщение

    Бот НЕ отвечает если:
    - Последнее сообщение от менеджера (чтобы не мешать живому общению)
    - Сообщение не от внешнего клиента

    Returns:
        (should_reply, reason)
    """
    if author_type != "external":
        return False, "message_from_manager"

    try:
        access_token = settings.amocrm.access_token
        if not access_token:
            logger.warning("⚠️  AMOCRM_ACCESS_TOKEN не настроен")
            return True, "no_token_check"

        client = get_amocrm_client(subdomain=subdomain, access_token=access_token)

        talk = await client.get_talk_by_id(int(talk_id))
        if not talk:
            return True, "talk_not_found"

        last_message = talk.get("last_message", {})
        last_message_author_type = last_message.get("author", {}).get("type")

        if last_message_author_type == "employee":
            logger.info("👨‍💼 Последнее сообщение от менеджера - бот не вмешивается")
            return False, "manager_already_replied"

        return True, "ok"

    except Exception as e:
        logger.warning(f"⚠️  Ошибка проверки беседы: {e}")
        return True, "check_failed"



def _generate_bot_response(client_message: str) -> str:
    """Генерирует ответ бота на сообщение клиента"""

    message_lower = client_message.lower()

    if "привет" in message_lower or "здравствуй" in message_lower:
        return f"Здравствуйте! 👋 Чем могу помочь? (Время: {datetime.now().strftime('%H:%M')})"

    if "помощь" in message_lower or "помоги" in message_lower:
        return "Я бот-помощник. Менеджер скоро ответит на ваше сообщение! ⏰"

    if "спасибо" in message_lower:
        return "Пожалуйста! Рад помочь 😊"

    return f"Получил ваше сообщение: '{client_message}'. Менеджер скоро ответит! 📨"


@router.post("/message/{scope_id}")
async def handle_message_webhook_with_scope(
    scope_id: str,
    request: Request
):
    """
    Обработчик вебхука для входящих сообщений с динамическим scope_id

    URL: https://agents-lab.ru/api/amocrm/message/{scope_id}

    Полный сценарий обработки:
    1. Проверяет, что сообщение входящее от клиента
    2. Проверяет, не отвечал ли менеджер
    3. Автоматически прикрепляет контакт к чату (если не привязан)
    4. Отправляет статус "печатает"
    5. Отправляет автоматический ответ от бота

    Args:
        scope_id: Уникальный идентификатор канала (channel_id_account_id)
        request: Объект запроса FastAPI с данными вебхука

    Returns:
        Статус обработки

    Example:
        POST https://agents-lab.ru/api/amocrm/message/64704b15-..._205ceec9-...
    """
    try:
        form_data = await request.form()
        payload = fix_encoding(dict(form_data))

        logger.info("📩 Получен вебхук от AmoCRM")
        logger.info(f"Scope ID: {scope_id}")
        logger.info(f"Payload keys: {list(payload.keys())}")

        if not _is_incoming_message(payload):
            logger.info("ℹ️  Пропускаем: не входящее сообщение от клиента")
            return {"status": "ignored", "reason": "not_incoming_message"}

        message_data = _extract_message_data(payload)
        if not message_data:
            logger.warning("⚠️  Не удалось извлечь данные сообщения из вебхука")
            return {"status": "error", "reason": "invalid_payload"}

        logger.info(
            f"💬 Входящее сообщение от {message_data.author_name} "
            f"(chat_id={message_data.chat_id}, text={message_data.text})"
        )

        subdomain = payload.get("account[subdomain]")
        if not subdomain:
            logger.error("❌ Не указан subdomain в вебхуке")
            return {"status": "error", "reason": "missing_subdomain"}

        should_reply, reason = await _should_bot_reply(
            subdomain=subdomain,
            talk_id=message_data.talk_id,
            author_type=message_data.author_type
        )

        if not should_reply:
            logger.info(f"🚫 Бот не отвечает: {reason}")
            return {"status": "skipped", "reason": reason}

        await _process_message_with_contact_attachment(
            message_data=message_data,
            scope_id=scope_id,
            subdomain=subdomain
        )

        logger.info(f"✅ Сообщение обработано в чате {message_data.chat_id}")

        return {"status": "success", "message": "Message processed"}

    except Exception as e:
        logger.error(f"❌ Ошибка обработки вебхука: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Webhook processing error: {str(e)}"
        )


# async def _process_message_with_contact_attachment(
#     message_data: WebhookMessage,
#     scope_id: str,
#     subdomain: str
# ):
#     """
#     Полная обработка сообщения с прикреплением контакта

#     1. Проверяет, привязан ли контакт
#     2. Если нет - ищет или создает контакт и привязывает к чату
#     3. Отправляет статус "печатает"
#     4. Отправляет ответ от бота
#     """
#     access_token = settings.amocrm.access_token
#     secret_key = settings.amocrm.secret_key
#     account_id = settings.amocrm.account_id
#     bot_amojo_id = settings.amocrm.bot_amojo_id

#     if not all([secret_key, account_id, bot_amojo_id]):
#         logger.error("❌ Не настроены учетные данные AmoCRM")
#         raise ValueError("AmoCRM credentials not configured")

#     crm_client = get_amocrm_client(subdomain=subdomain, access_token=access_token)
#     chat_client = get_amocrm_chat_client(
#         scope_id=scope_id,
#         secret_key=secret_key,
#         account_id=account_id
#     )

#     try:
#         if not message_data.contact_id:
#             logger.info("🔗 Контакт не привязан, прикрепляем...")

#             contact = await crm_client.find_or_create_contact(
#                 name=message_data.author_name,
#                 phone=None
#             )

#             await crm_client.attach_contact_to_talk(
#                 chat_id=message_data.chat_id,
#                 contact_id=contact["id"]
#             )

#             logger.info(f"✅ Контакт {contact['id']} привязан к чату {message_data.chat_id}")

#         logger.info("⌨️  Отправка статуса 'печатает'...")
#         await chat_client.send_typing_status(
#             chat_id=message_data.chat_id,
#             sender_ref_id=bot_amojo_id
#         )

#         import asyncio
#         await asyncio.sleep(1)

#         response_text = _generate_bot_response(message_data.text or "")

#         await chat_client.send_message(
#             chat_id=message_data.chat_id,
#             text=response_text,
#             sender_ref_id=bot_amojo_id,
#             sender_name="Бот-Помощник",
#             reply_to_message_id=message_data.message_id,
#             silent=False
#         )

#         logger.info("✅ Ответ отправлен")

#     finally:
#         await crm_client.close()
#         await chat_client.close()


@router.post("/webhook/{scope_id}/{flow_id}")
async def amocrm_webhook_with_flow(
    scope_id: str,
    flow_id: str,
    request: Request
):
    """
    Универсальный webhook для AmoCRM с запуском flow через TaskProcessor

    URL: https://agents-lab.ru/api/amocrm/webhook/{scope_id}/{flow_id}

    Аналог telegram_webhook - создает AmoCRMInterface на лету и запускает ИИ-агента.

    Args:
        scope_id: Идентификатор канала AmoCRM (channel_id_account_id)
        flow_id: ID флоу для обработки
        request: Объект запроса с данными вебхука

    Returns:
        Статус обработки

    Example:
        POST https://agents-lab.ru/api/amocrm/webhook/64704b15-..._205ceec9-.../smart_flow
    """
    try:
        form_data = await request.form()
        payload = fix_encoding(dict(form_data))

        logger.info(f"📩 Webhook AmoCRM для flow {flow_id}")
        logger.info(f"Scope ID: {scope_id}")

        storage = Storage()
        flow_config = await storage.get_flow_config(flow_id)

        if not flow_config:
            logger.error(f"Flow {flow_id} не найден в БД")
            raise HTTPException(status_code=404, detail=f"Flow {flow_id} not found")

        if 'amocrm' not in  flow_config.platforms:
            logger.error(f"Flow {flow_id} не поддерживает AmoCRM")
            raise HTTPException(
                status_code=400, detail=f"Flow {flow_id} does not support AmoCRM"
            )
        amocrm_config = flow_config.platforms["amocrm"]

        subdomain = payload.get("account[subdomain]") or amocrm_config.get("subdomain")
        if not subdomain:
            logger.error("❌ Не указан subdomain в вебхуке и в конфигурации flow")
            raise HTTPException(
                status_code=400, detail="Missing subdomain in webhook payload and flow config"
            )

        amocrm_interface = AmoCRMInterface(scope_id, subdomain)

        message = await amocrm_interface.handle_message(payload, flow_id)
        if not message:
            logger.info("Сообщение не требует обработки (команда или системное)")
            return {"ok": True}

        task_id = await amocrm_interface.create_task(message, flow_id)

        if task_id:
            logger.info(
                f"📋 Создана задача {task_id} для flow {flow_id} от пользователя {message.user_id}"
            )
        else:
            logger.info(f"⏳ Задача не создана - сессия занята для {message.user_id}")

        return {"ok": True}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка AmoCRM webhook для flow {flow_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))