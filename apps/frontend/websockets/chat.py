"""
WebSocket для чата с агентами.

ACK протокол:
- Каждое сообщение имеет message_id
- Клиент отправляет ACK после получения
- Уведомление удаляется из БД только после ACK
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import json
import logging
import asyncio
import uuid
from typing import Dict, Set
from core.context import get_context, set_context, clear_context
from core.models.context_models import Context
from apps.agents.container import get_agents_container
from apps.frontend.container import get_frontend_container
from apps.frontend.core.websocket_manager import websocket_manager

logger = logging.getLogger(__name__)

router = APIRouter()

# Трекинг неподтвержденных сообщений: {session_id: {message_id: notification_key}}
_pending_acks: Dict[str, Dict[str, str]] = {}


async def _poll_notifications(session_id: str, context: Context):
    """Polling уведомлений из БД для конкретной сессии

    Args:
        session_id: ID сессии для polling
        context: Контекст пользователя (передается явно, т.к. asyncio.create_task теряет contextvars)
    """

    set_context(context)

    frontend_container = get_frontend_container()
    _storage = frontend_container.storage
    processed_notifications = set()

    logger.info(f"🔄 Начинаем polling уведомлений для сессии {session_id}")
    iteration = 0
    consecutive_errors = 0
    max_consecutive_errors = 5

    user_id = context.user.user_id
    company_id = context.active_company.company_id if context.active_company else "НЕТ"
    logger.info(f"✅ Контекст установлен: user_id={user_id}, company={company_id}")

    while session_id in websocket_manager.connections["chat"]:
            try:
                iteration += 1
                notification_pattern = f"web_notification:web:{user_id}:"

                if iteration == 1 or iteration % 10 == 0:
                    connection_status = session_id in websocket_manager.connections["chat"]
                    logger.info(f"🔍 [Итерация {iteration}] Polling активен: connection={connection_status}, pattern={notification_pattern}")

                keys = await _storage.list_by_prefix(notification_pattern, limit=1000, force_global=True)

                if keys:
                    logger.info(f"📬 [Итерация {iteration}] Найдено {len(keys)} уведомлений для user_id={user_id}")
                    logger.debug(f"📬 Ключи уведомлений: {keys[:5]}")

                    for key in keys:
                        if key not in processed_notifications:
                            notification_data = await _storage.get(key)
                            if notification_data:
                                try:
                                    notification = json.loads(notification_data)
                                    notification_type = notification.get('type', 'unknown')
                                    notification_session = notification.get('session_id', 'unknown')

                                    # Проверяем соединение
                                    if session_id not in websocket_manager.connections["chat"]:
                                        logger.warning(f"WebSocket сессия {session_id} отключена, пропускаем уведомление")
                                        continue
                                    
                                    # Добавляем message_id для ACK протокола
                                    message_id = f"msg_{uuid.uuid4().hex[:12]}"
                                    notification["message_id"] = message_id
                                    
                                    # Регистрируем ожидание ACK
                                    if session_id not in _pending_acks:
                                        _pending_acks[session_id] = {}
                                    _pending_acks[session_id][message_id] = key
                                    
                                    await websocket_manager.send_to_session(session_id, notification, "chat")
                                    logger.info(
                                        f"Уведомление отправлено: ws_session={session_id}, "
                                        f"type={notification_type}, message_id={message_id}"
                                    )
                                    processed_notifications.add(key)

                                    # Удаляем из БД сразу (ACK для логирования, не блокирует)
                                    await _storage.delete(key)
                                except json.JSONDecodeError as e:
                                    logger.error(f"Ошибка парсинга уведомления {key}: {e}")
                                    await _storage.delete(key)
                                except Exception as e:
                                    logger.error(f"Ошибка обработки уведомления {key}: {e}", exc_info=True)

                if len(processed_notifications) > 300:
                    logger.info(f"🧹 Очистка кэша обработанных уведомлений: {len(processed_notifications)} -> 0")
                    processed_notifications.clear()

                consecutive_errors = 0

            except Exception as e:
                consecutive_errors += 1
                logger.error(
                    f"❌ Ошибка в polling для {session_id} [Итерация {iteration}, ошибка #{consecutive_errors}]: {e}",
                    exc_info=True
                )

                if consecutive_errors >= max_consecutive_errors:
                    logger.error(
                        f"🛑 Критическая ошибка: {consecutive_errors} последовательных ошибок в polling для {session_id}. "
                        f"Останавливаем polling."
                    )
                    break

            await asyncio.sleep(2)

    connection_still_exists = session_id in websocket_manager.connections["chat"]
    logger.info(
        f"🔄 Polling завершен для сессии {session_id}. "
        f"Connection exists: {connection_still_exists}, iterations: {iteration}"
    )
    clear_context()


@router.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    """WebSocket endpoint для чата"""
    
    from core.utils.tokens import get_token_service

    chat_session_id = None  # Инициализируем переменную

    try:
        # Получаем токен из query параметров (для embed чата)
        embed_token = websocket.query_params.get("token")
        
        logger.info(f"🔍 WebSocket подключение: token в query={'есть' if embed_token else 'нет'}, cookies={list(websocket.cookies.keys())}")
        
        # Принимаем WebSocket соединение
        await websocket.accept()
        
        # Получаем session_id из cookies (для обычного чата)
        auth_session_id = websocket.cookies.get("session_id")
        
        # Если нет cookie, пытаемся получить токен из query параметров
        is_embed_chat = False
        if not auth_session_id and embed_token:
            logger.info("🔑 Используем токен для встроенного чата")
            is_embed_chat = True
            token_service = get_token_service()
            token_data = token_service.validate_token(embed_token)
            
            if not token_data:
                logger.error("❌ Невалидный токен для embed чата")
                await websocket.close(code=4001, reason="Invalid embed token")
                return
            
            frontend_container = get_frontend_container()
            company_repo = frontend_container.company_repository
            active_company = await company_repo.get(token_data.company_id)
            if not active_company:
                logger.error(f"Компания {token_data.company_id} не найдена")
                await websocket.close(code=4003, reason=f"Company {token_data.company_id} not found")
                return
            
            # Получаем пользователя через приватный метод _get_user
            auth_service = frontend_container.auth_service
            # Используем _get_user напрямую, так как это внутренний метод AuthService
            user = await auth_service._get_user(token_data.user_id)
            
            if not user:
                logger.error(f"❌ Пользователь {token_data.user_id} не найден")
                await websocket.close(code=4001, reason="User not found")
                return
            
            # Используем session_id из токена
            auth_session_id = token_data.session_id
            
        elif not auth_session_id:
            # Нет авторизации - закрываем соединение
            logger.error("❌ Нет авторизации - нет session и токена")
            await websocket.close(code=4001, reason="Unauthorized - no session or token")
            return
        else:
            # Получаем пользователя по сессии (обычный чат)
            frontend_container = get_frontend_container()
            auth_service = frontend_container.auth_service
            user = await auth_service.get_user_by_session(auth_session_id)

        if not user:
            # Невалидная сессия - закрываем соединение
            logger.error(f"❌ Невалидная сессия: {auth_session_id}")
            await websocket.close(code=4001, reason="Invalid session")
            return

        # Получаем активную компанию пользователя
        frontend_container = get_frontend_container()
        company_repo = frontend_container.company_repository

        if is_embed_chat:
            # Для embed чата используем компанию из токена (уже получена выше)
            logger.info(f"✅ Embed чат: используем компанию из токена {active_company.company_id}")
        else:
            # Для обычного чата используем активную компанию пользователя
            if not user.active_company_id:
                logger.error(f"❌ У пользователя {user.user_id} нет активной компании")
                await websocket.close(code=4003, reason="User has no active company")
                return

            active_company = await company_repo.get(user.active_company_id)
            if not active_company:
                logger.error(f"Компания {user.active_company_id} не найдена")
                await websocket.close(code=4003, reason=f"Company {user.active_company_id} not found")
                return

        user_companies = []
        for company_id in user.companies.keys():
            company = await company_repo.get(company_id)
            if company:
                user_companies.append(company)

        # Создаем контекст с правильной компанией
        context = Context(
            user=user,
            session_id=auth_session_id,
            platform="web",
            active_company=active_company,
            user_companies=user_companies,
            metadata={"websocket": True, "authenticated": True},
        )
        set_context(context)

        # Используем auth_session_id как session_id для чата
        chat_session_id = auth_session_id
        logger.info(
            f"🔗 WebSocket чат подключен для пользователя {user.user_id}, session_id: {chat_session_id}"
        )

        await websocket_manager.connect(websocket, chat_session_id, "chat")

        # Запускаем polling уведомлений (передаем контекст явно)
        logger.info(f"🚀 Запускаем polling для {chat_session_id}, user_id={user.user_id}, company={context.active_company.company_id}")
        websocket_manager.start_polling(
            chat_session_id,
            _poll_notifications(chat_session_id, context),
            "chat"
        )

        # Основной цикл WebSocket
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)

            # Обрабатываем сообщения от клиента
            await handle_chat_message(message, chat_session_id)

    except WebSocketDisconnect:
        websocket_manager.disconnect(chat_session_id, "chat")
        _pending_acks.pop(chat_session_id, None)
    except Exception as e:
        logger.error(f"WebSocket ошибка для чата {chat_session_id}: {e}")
        websocket_manager.disconnect(chat_session_id, "chat")
        _pending_acks.pop(chat_session_id, None)
    finally:
        clear_context()


async def handle_chat_message(message: dict, session_id: str):
    """Обработка сообщения от клиента чата"""
    message_type = message.get("type")

    if message_type == "USER_MESSAGE":
        message_session_id = message["data"].get("session_id", session_id)
        await process_user_message(
            message["data"],
            websocket_session_id=session_id,
            message_session_id=message_session_id,
        )
    elif message_type == "INTERRUPT_RESPONSE":
        await process_interrupt_response(message["data"], session_id)
    elif message_type == "ACK":
        # Подтверждение получения сообщения от клиента
        await _handle_ack(message.get("message_id"), session_id)
    elif message_type == "PING":
        pong_message = {"type": "PONG"}
        await websocket_manager.send_to_session(session_id, pong_message, "chat")
        logger.debug(f"PONG отправлен в {session_id}")


async def _handle_ack(message_id: str, session_id: str):
    """Обработка ACK от клиента.
    
    Клиент отправляет ACK после успешного получения сообщения.
    Используется для логирования и трекинга доставки.
    """
    if not message_id:
        return
    
    # Удаляем из pending
    if session_id in _pending_acks:
        notification_key = _pending_acks[session_id].pop(message_id, None)
        if notification_key:
            logger.debug(f"ACK получен: message_id={message_id}, session_id={session_id}")
        
        # Очищаем пустые записи
        if not _pending_acks[session_id]:
            del _pending_acks[session_id]


async def process_user_message(
    data: dict, websocket_session_id: str, message_session_id: str
):
    """Обработка сообщения пользователя - создание задачи для агента"""

    agent_id = data.get("agent_id")
    message_text = data.get("message", "")
    files_data = data.get("files", [])  # Получаем файлы если есть

    # Polling автоматически найдет уведомления для всех чат-сессий пользователя
    logger.info(
        f"📨 WebSocket session: {websocket_session_id}, Chat session: {message_session_id}"
    )

    files_info = f" с {len(files_data)} файлами" if files_data else ""
    logger.info(
        f"Создаем задачу для агента {agent_id}: {message_text[:50]}...{files_info}"
    )

    # Получаем контекст с настоящим пользователем
    context = get_context()
    if not context:
        logger.error("Нет контекста в process_user_message")
        return

    # Для фронтенда флоу = агент, поэтому agent_id уже содержит правильный flow_id
    flow_id = agent_id

    # Создаем Message через WebInterface
    raw_message_data = {
        "message": message_text,
        "agent_id": agent_id,
        "session_id": message_session_id,  # Используем session_id из сообщения
        "user_id": context.user.user_id,  # Используем настоящего пользователя
        "files": files_data,  # Добавляем файлы в данные сообщения
    }

    agents_container = get_agents_container()
    
    from apps.agents.interfaces.web_interface import get_web_interface
    web_interface = get_web_interface()
    
    message = await web_interface.handle_message(raw_message_data, flow_id)
    if message:
        logger.info(
            f"🔍 Создаем задачу: session_id={message.session_id}, agent={agent_id}"
        )
        # Создаем задачу через WebInterface (теперь контекст есть)
        task_id = await web_interface.create_task(message, flow_id)
        if task_id:
            logger.info(
                f"✅ Создана задача {task_id} для агента {agent_id} с session_id={message.session_id}"
            )
        else:
            logger.info(f"⏳ Задача не создана - сессия занята для {agent_id}")
    else:
        # Для команд это нормально - они обрабатываются напрямую
        logger.info(
            f"📋 Сообщение обработано напрямую (возможно команда): {message_text[:50]}..."
        )


async def process_interrupt_response(data: dict, session_id: str):
    """Обработка ответа на interrupt"""
    # TODO: Продолжение выполнения агента
    logger.info(
        f"Получен ответ на interrupt в чате {session_id}: {data.get('response', '')[:50]}..."
    )
