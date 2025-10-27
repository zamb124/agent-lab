"""
TODO: IN PROGRRESS
TODO: Add tests


Инструменты для работы с AmoCRM API

ВАЖНО: Этот модуль работает с:
1. Основным AmoCRM API v4 (сделки, контакты, задачи, пользователи)
2. Talks API (беседы) - работа с существующими беседами из мессенджеров
3. Chat API (amojo.amocrm.ru) - создание своего канала мессенджера

Для работы с Talks API (беседы):
- Используйте get_amocrm_talks() для получения списка бесед
- get_amocrm_talk_info() для деталей конкретной беседы
- close_amocrm_talk() для закрытия беседы

Для работы с Chat API (свой канал):
- Получить amojo_id аккаунта через get_amocrm_account_info(with_amojo_id=True)
- Использовать connect_amocrm_channel() для подключения канала
- Использовать scope_id и secret_key для send_amocrm_chat_message
"""

import json
import logging
from typing import Optional
from app.core.tool_decorator import tool

from app.clients.amo_crm_integration import get_amocrm_client

logger = logging.getLogger(__name__)


@tool(group="CRM")
async def get_amocrm_leads(subdomain: str, limit: int = 50, query: Optional[str] = None) -> str:
    """
    Получает список сделок из AmoCRM.

    Args:
        subdomain: Поддомен вашего аккаунта AmoCRM (например, 'mycompany')
        limit: Максимальное количество сделок (по умолчанию 50, макс. 250)
        query: Поисковый запрос для фильтрации сделок

    Returns:
        JSON со списком сделок: {"success": bool, "count": int, "leads": [...]}
    """
    logger.info(f"Получение сделок из AmoCRM (subdomain: {subdomain})")

    client = get_amocrm_client(subdomain=subdomain)

    leads = await client.get_leads(limit=limit, query=query)

    # Форматируем данные для агента
    leads_data = []
    for lead in leads:
        leads_data.append(
            {
                "id": lead.get("id"),
                "name": lead.get("name"),
                "price": lead.get("price", 0),
                "status_id": lead.get("status_id"),
                "responsible_user_id": lead.get("responsible_user_id"),
                "created_at": lead.get("created_at"),
                "updated_at": lead.get("updated_at"),
            }
        )

    return json.dumps({"success": True, "count": len(leads_data), "leads": leads_data}, ensure_ascii=False, indent=2)


@tool(group="CRM")
async def get_amocrm_lead_info(subdomain: str, lead_id: int) -> str:
    """
    Получает детальную информацию о конкретной сделке AmoCRM.

    Args:
        subdomain: Поддомен вашего аккаунта AmoCRM
        lead_id: ID сделки

    Returns:
        JSON с информацией о сделке: {"success": bool, "lead": {...}}
    """
    logger.info(f"Получение информации о сделке {lead_id}")

    client = get_amocrm_client(subdomain=subdomain)

    lead = await client.get_lead(lead_id=lead_id)

    return json.dumps(
        {
            "success": True,
            "lead": {
                "id": lead.get("id"),
                "name": lead.get("name"),
                "price": lead.get("price", 0),
                "status_id": lead.get("status_id"),
                "pipeline_id": lead.get("pipeline_id"),
                "responsible_user_id": lead.get("responsible_user_id"),
                "created_at": lead.get("created_at"),
                "updated_at": lead.get("updated_at"),
                "closed_at": lead.get("closed_at"),
                "custom_fields_values": lead.get("custom_fields_values"),
            },
        },
        ensure_ascii=False,
        indent=2,
    )


@tool(group="CRM")
async def get_amocrm_contacts(subdomain: str, limit: int = 50, query: Optional[str] = None) -> str:
    """
    Получает список контактов из AmoCRM.

    Args:
        subdomain: Поддомен вашего аккаунта AmoCRM
        limit: Максимальное количество контактов (по умолчанию 50, макс. 250)
        query: Поисковый запрос для фильтрации контактов

    Returns:
        JSON со списком контактов: {"success": bool, "count": int, "contacts": [...]}
    """
    logger.info("Получение контактов из AmoCRM")

    client = get_amocrm_client(subdomain=subdomain)

    contacts = await client.get_contacts(limit=limit, query=query)

    contacts_data = []
    for contact in contacts:
        contacts_data.append(
            {
                "id": contact.get("id"),
                "name": contact.get("name"),
                "first_name": contact.get("first_name"),
                "last_name": contact.get("last_name"),
                "responsible_user_id": contact.get("responsible_user_id"),
                "created_at": contact.get("created_at"),
                "updated_at": contact.get("updated_at"),
            }
        )

    return json.dumps({"success": True, "count": len(contacts_data), "contacts": contacts_data}, ensure_ascii=False, indent=2)


@tool(group="CRM")
async def get_amocrm_tasks(
    subdomain: str, limit: int = 50, entity_type: Optional[str] = None, entity_id: Optional[int] = None
) -> str:
    """
    Получает список задач из AmoCRM.

    Args:
        subdomain: Поддомен вашего аккаунта AmoCRM
        limit: Максимальное количество задач (по умолчанию 50, макс. 250)
        entity_type: Тип сущности для фильтра ("leads", "contacts", "companies")
        entity_id: ID сущности для фильтра

    Returns:
        JSON со списком задач: {"success": bool, "count": int, "tasks": [...]}
    """
    logger.info("Получение задач из AmoCRM")

    client = get_amocrm_client(subdomain=subdomain)

    tasks = await client.get_tasks(limit=limit, filter_entity_type=entity_type, filter_entity_id=entity_id)

    tasks_data = []
    for task in tasks:
        tasks_data.append(
            {
                "id": task.get("id"),
                "text": task.get("text"),
                "complete_till": task.get("complete_till"),
                "is_completed": task.get("is_completed", False),
                "task_type_id": task.get("task_type_id"),
                "entity_type": task.get("entity_type"),
                "entity_id": task.get("entity_id"),
                "responsible_user_id": task.get("responsible_user_id"),
                "created_at": task.get("created_at"),
                "updated_at": task.get("updated_at"),
            }
        )

    return json.dumps({"success": True, "count": len(tasks_data), "tasks": tasks_data}, ensure_ascii=False, indent=2)


@tool(group="CRM")
async def get_amocrm_account_info(subdomain: str, with_amojo_id: bool = False) -> str:
    """
    Получает информацию об аккаунте AmoCRM.

    Args:
        subdomain: Поддомен вашего аккаунта AmoCRM
        with_amojo_id: Получить amojo_id аккаунта (необходимо для Chat API)

    Returns:
        JSON с информацией об аккаунте: {"success": bool, "account": {...}}
    """
    logger.info("Получение информации об аккаунте AmoCRM")

    client = get_amocrm_client(subdomain=subdomain)

    info = await client.get_account_info(with_amojo_id=with_amojo_id)

    account_data = {
        "id": info.get("id"),
        "name": info.get("name"),
        "subdomain": info.get("subdomain"),
        "country": info.get("country"),
        "currency": info.get("currency"),
        "timezone": info.get("timezone"),
    }

    # Добавляем amojo_id если был запрошен
    if with_amojo_id and "amojo_id" in info:
        account_data["amojo_id"] = info.get("amojo_id")

    return json.dumps(
        {
            "success": True,
            "account": account_data,
        },
        ensure_ascii=False,
        indent=2,
    )


@tool(group="CRM")
async def get_amocrm_users(subdomain: str, limit: int = 50, with_amojo_id: bool = False) -> str:
    """
    Получает список пользователей аккаунта AmoCRM.

    Args:
        subdomain: Поддомен вашего аккаунта AmoCRM
        limit: Максимальное количество пользователей (по умолчанию 50, макс. 250)
        with_amojo_id: Получить amojo_id пользователей (необходимо для Chat API)

    Returns:
        JSON со списком пользователей: {"success": bool, "count": int, "users": [...]}
    """
    logger.info("Получение пользователей из AmoCRM")

    client = get_amocrm_client(subdomain=subdomain)

    users = await client.get_users(limit=limit, with_amojo_id=with_amojo_id)

    users_data = []
    for user in users:
        user_info = {
            "id": user.get("id"),
            "name": user.get("name"),
            "email": user.get("email"),
            "lang": user.get("lang"),
            "rights": user.get("rights", {}).get("group") if user.get("rights") else None,
        }

        # Добавляем amojo_id если был запрошен
        if with_amojo_id and "amojo_id" in user:
            user_info["amojo_id"] = user.get("amojo_id")

        users_data.append(user_info)

    return json.dumps({"success": True, "count": len(users_data), "users": users_data}, ensure_ascii=False, indent=2)


@tool(group="CRM")
async def get_amocrm_notes(subdomain: str, entity_type: str, entity_id: int, limit: int = 50) -> str:
    """
    Получает примечания/комментарии к сущности AmoCRM (сделка/контакт).
    Это ближайший аналог "чатов" без использования webhook'ов.

    Args:
        subdomain: Поддомен вашего аккаунта AmoCRM
        entity_type: Тип сущности ("leads", "contacts", "companies")
        entity_id: ID сущности
        limit: Максимальное количество примечаний (по умолчанию 50, макс. 250)

    Returns:
        JSON со списком примечаний: {"success": bool, "count": int, "notes": [...]}
    """
    logger.info(f"Получение примечаний для {entity_type}:{entity_id}")

    client = get_amocrm_client(subdomain=subdomain)

    notes = await client.get_notes(entity_type=entity_type, entity_id=entity_id, limit=limit)

    notes_data = []
    for note in notes:
        notes_data.append(
            {
                "id": note.get("id"),
                "note_type": note.get("note_type"),
                "text": note.get("params", {}).get("text"),
                "created_by": note.get("created_by"),
                "created_at": note.get("created_at"),
                "updated_at": note.get("updated_at"),
                "responsible_user_id": note.get("responsible_user_id"),
            }
        )

    return json.dumps(
        {"success": True, "count": len(notes_data), "entity_type": entity_type, "entity_id": entity_id, "notes": notes_data},
        ensure_ascii=False,
        indent=2,
    )


@tool(group="CRM")
async def create_amocrm_note(subdomain: str, entity_type: str, entity_id: int, text: str, note_type: str = "common") -> str:
    """
    Создает примечание/комментарий к сущности AmoCRM.
    Используется для добавления заметок к сделкам/контактам (аналог отправки сообщения).

    Args:
        subdomain: Поддомен вашего аккаунта AmoCRM
        entity_type: Тип сущности ("leads", "contacts", "companies")
        entity_id: ID сущности
        text: Текст примечания
        note_type: Тип примечания ("common" - обычное, "call_in" - входящий звонок, "call_out" - исходящий)

    Returns:
        JSON с информацией о созданном примечании: {"success": bool, "note": {...}}
    """
    logger.info(f"Создание примечания для {entity_type}:{entity_id}")

    client = get_amocrm_client(subdomain=subdomain)

    result = await client.create_note(entity_type=entity_type, entity_id=entity_id, note_type=note_type, text=text)

    # Извлекаем информацию о созданном примечании
    embedded = result.get("_embedded", {})
    notes = embedded.get("notes", [])
    created_note = notes[0] if notes else {}

    return json.dumps(
        {
            "success": True,
            "note": {
                "id": created_note.get("id"),
                "entity_type": entity_type,
                "entity_id": entity_id,
                "note_type": note_type,
                "text": text,
                "created_at": created_note.get("created_at"),
            },
        },
        ensure_ascii=False,
        indent=2,
    )


@tool(group="CRM")
async def send_amocrm_chat_message(
    scope_id: str,
    secret_key: str,
    account_id: str,
    conversation_id: str,
    user_id: str,
    user_name: str,
    text: str,
    phone: Optional[str] = None,
    email: Optional[str] = None,
) -> str:
    """
    Отправляет сообщение в чат AmoCRM через Chat API (amojo.amocrm.ru).
    Создает разговор если его еще нет.

    ВАЖНО: Перед использованием убедитесь, что канал подключен к аккаунту
    (используйте connect_amocrm_channel один раз при первой настройке).

    Args:
        scope_id: scope_id, полученный после подключения канала (НЕ channel_id!)
        secret_key: Секретный ключ интеграции
        account_id: amojo_id аккаунта AmoCRM
        conversation_id: Уникальный ID разговора (можно использовать свой)
        user_id: Уникальный ID пользователя в вашей системе
        user_name: Имя пользователя
        text: Текст сообщения
        phone: Телефон пользователя (опционально)
        email: Email пользователя (опционально)

    Returns:
        JSON с результатом отправки: {"success": bool, "conversation_id": str}
    """
    logger.info(f"Отправка сообщения в чат {conversation_id}")

    client = get_amocrm_chat_client(channel_id=scope_id, secret_key=secret_key, account_id=account_id)

    user_profile = {}
    if phone:
        user_profile["phone"] = phone
    if email:
        user_profile["email"] = email

    result = await client.send_message(
        conversation_id=conversation_id,
        user_id=user_id,
        user_name=user_name,
        text=text,
        message_type="text",
        user_profile=user_profile if user_profile else None,
    )

    return json.dumps({"success": True, "conversation_id": conversation_id, "result": result}, ensure_ascii=False, indent=2)


@tool(group="CRM")
async def update_amocrm_message_status(
    scope_id: str,
    secret_key: str,
    account_id: str,
    conversation_id: str,
    message_id: str,
    status: str,
) -> str:
    """
    Обновляет статус сообщения в чате AmoCRM.

    Args:
        scope_id: scope_id, полученный после подключения канала (НЕ channel_id!)
        secret_key: Секретный ключ интеграции
        account_id: amojo_id аккаунта AmoCRM
        conversation_id: ID разговора
        message_id: ID сообщения
        status: Статус сообщения ("delivered", "read", "error")

    Returns:
        JSON с результатом: {"success": bool}
    """
    logger.info(f"Обновление статуса сообщения {message_id} на {status}")

    client = get_amocrm_chat_client(channel_id=scope_id, secret_key=secret_key, account_id=account_id)

    result = await client.update_message_status(conversation_id=conversation_id, message_id=message_id, status=status)

    return json.dumps({"success": True, "message_id": message_id, "status": status, "result": result}, ensure_ascii=False, indent=2)


# ========== ИНСТРУМЕНТЫ ДЛЯ РАБОТЫ С БЕСЕДАМИ (TALKS) ==========


@tool(group="CRM")
async def get_amocrm_talks(
    subdomain: str,
    limit: int = 50,
    filter_contact_id: Optional[int] = None,
    filter_entity_id: Optional[int] = None,
    filter_is_in_work: Optional[bool] = None,
) -> str:
    """
    Получает список бесед из AmoCRM.

    Беседы - это переписки из подключенных мессенджеров (Telegram, WhatsApp, VK и др.)

    Args:
        subdomain: Поддомен аккаунта AmoCRM
        limit: Максимальное количество бесед (по умолчанию 50, макс. 250)
        filter_contact_id: Фильтр по ID контакта (опционально)
        filter_entity_id: Фильтр по ID сделки или покупателя (опционально)
        filter_is_in_work: Фильтр по статусу "в работе" (опционально)

    Returns:
        JSON со списком бесед: {"success": bool, "count": int, "talks": [...]}
    """
    logger.info(f"Получение бесед из AmoCRM (subdomain: {subdomain})")

    client = get_amocrm_client(subdomain=subdomain)

    talks = await client.get_talks(
        limit=limit,
        filter_contact_id=filter_contact_id,
        filter_entity_id=filter_entity_id,
        filter_is_in_work=filter_is_in_work,
    )

    # Форматируем данные для агента
    talks_data = []
    for talk in talks:
        talks_data.append({
            "id": talk.get("talk_id"),
            "chat_id": talk.get("chat_id"),
            "contact_id": talk.get("contact_id"),
            "entity_id": talk.get("entity_id"),
            "entity_type": talk.get("entity_type"),
            "origin": talk.get("origin"),  # Telegram, WhatsApp и т.д.
            "is_in_work": talk.get("is_in_work"),
            "is_read": talk.get("is_read"),
            "created_at": talk.get("created_at"),
            "updated_at": talk.get("updated_at"),
        })

    return json.dumps(
        {"success": True, "count": len(talks_data), "talks": talks_data},
        ensure_ascii=False,
        indent=2,
    )


@tool(group="CRM")
async def get_amocrm_talk_info(
    subdomain: str,
    talk_id: int,
) -> str:
    """
    Получает детальную информацию о конкретной беседе по ID.

    Args:
        subdomain: Поддомен аккаунта AmoCRM
        talk_id: ID беседы

    Returns:
        JSON с информацией о беседе: {"success": bool, "talk": {...}}
    """
    logger.info(f"Получение информации о беседе {talk_id} из AmoCRM")

    client = get_amocrm_client(subdomain=subdomain)

    talk = await client.get_talk_by_id(talk_id=talk_id)

    return json.dumps(
        {"success": True, "talk": talk},
        ensure_ascii=False,
        indent=2,
    )


@tool(group="CRM")
async def close_amocrm_talk(
    subdomain: str,
    talk_id: int,
    force_close: bool = False,
) -> str:
    """
    Закрывает беседу в AmoCRM.

    Если force_close=False, может запустить NPS-бота (если он включен).
    Если force_close=True, беседа закроется принудительно без NPS.

    Args:
        subdomain: Поддомен аккаунта AmoCRM
        talk_id: ID беседы для закрытия
        force_close: Принудительное закрытие без NPS-бота (по умолчанию False)

    Returns:
        JSON с результатом: {"success": bool, "message": str}
    """
    logger.info(f"Закрытие беседы {talk_id} (force_close={force_close})")

    client = get_amocrm_client(subdomain=subdomain)

    result = await client.close_talk(talk_id=talk_id, force_close=force_close)

    if result:
        message = f"Беседа {talk_id} успешно закрыта"
    else:
        message = f"Беседа {talk_id} уже была закрыта ранее"

    return json.dumps(
        {"success": result, "message": message},
        ensure_ascii=False,
        indent=2,
    )


# Список доступных инструментов для экспорта
AMOCRM_TOOLS = [
    # Основное API v4
    get_amocrm_leads,
    get_amocrm_lead_info,
    get_amocrm_contacts,
    get_amocrm_tasks,
    get_amocrm_account_info,
    get_amocrm_users,
    # Notes API (примечания)
    get_amocrm_notes,
    create_amocrm_note,
    # Talks API (беседы из мессенджеров)
    get_amocrm_talks,
    get_amocrm_talk_info,
    close_amocrm_talk,
    # Chat API amojo (отправка сообщений в чаты Telegram/WhatsApp через HMAC)
    send_amocrm_chat_message,  # Отправка сообщения через amojo.amocrm.ruloc    update_amocrm_message_status,
]
