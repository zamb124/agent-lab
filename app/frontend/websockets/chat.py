"""
WebSocket для чата с агентами
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import json
import logging
import asyncio
from datetime import datetime, timezone
from app.core.storage import Storage
from app.interfaces.web_interface import web_interface
from app.core.context import get_context, set_context, clear_context
from app.models import Context
from app.identity.auth_service import AuthService
from app.identity.models import Company
from app.frontend.core.websocket_manager import websocket_manager

logger = logging.getLogger(__name__)

router = APIRouter()


async def _poll_notifications(session_id: str):
    """Polling уведомлений из БД для конкретной сессии"""
    
    storage = Storage()
    processed_notifications = set()
    
    logger.info(f"🔄 Начинаем polling уведомлений для сессии {session_id}")
    
    while session_id in websocket_manager.connections["chat"]:
            try:
                # Ищем уведомления для всех web сессий пользователя
                context = get_context()
                if not context:
                    logger.warning(f"Нет контекста для polling {session_id}")
                    await asyncio.sleep(2)
                    continue

                user_id = context.user.user_id
                notification_pattern = f"web_notification:web:{user_id}:"
                logger.debug(f"🔍 Ищем уведомления по pattern: {notification_pattern}")

                # Ищем все уведомления и сортируем по timestamp
                keys = await storage.list_by_prefix(notification_pattern)

                # Фильтруем и сортируем уведомления по timestamp
                notifications_to_process = []
                current_time = datetime.now(timezone.utc).timestamp()

                for key in keys:
                    if key not in processed_notifications:
                        # Извлекаем timestamp из ключа
                        parts = key.split(":")
                        if len(parts) >= 2:
                            try:
                                key_timestamp = float(parts[-1])
                                age = current_time - key_timestamp
                                # Обрабатываем только свежие уведомления (за последние 60 секунд)
                                if age <= 60:
                                    notifications_to_process.append(
                                        (key, key_timestamp)
                                    )
                                else:
                                    logger.debug(f"⏭️ Пропускаем старое уведомление (age={age:.1f}s)")
                            except ValueError:
                                logger.debug(f"⚠️ Не удалось распарсить timestamp из ключа")
                                continue

                # Сортируем по timestamp (старые сначала)
                notifications_to_process.sort(key=lambda x: x[1])

                # Обрабатываем уведомления в правильном порядке
                for key, timestamp in notifications_to_process:
                    notification_data = await storage.get(key)
                    if notification_data:
                        logger.info(f"📨 Найдено уведомление: {key}")
                        notification = json.loads(notification_data)
                        await websocket_manager.send_to_session(session_id, notification, "chat")
                        processed_notifications.add(key)

                        # Удаляем обработанное уведомление
                        await storage.delete(key)
                        logger.info(f"🗑️ Уведомление удалено: {key}")

                # Очищаем старые processed_notifications (старше 5 минут)
                if len(processed_notifications) > 300:
                    processed_notifications.clear()

            except Exception as e:
                logger.error(f"❌ Ошибка в polling для {session_id}: {e}")

            # Ждем перед следующей проверкой
            await asyncio.sleep(2)


@router.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket, session_id: str = None):
    """WebSocket endpoint для чата"""

    chat_session_id = None  # Инициализируем переменную
    
    try:
        # Получаем session_id из cookies (как в AuthMiddleware)
        auth_session_id = websocket.cookies.get("session_id")

        if not auth_session_id:
            # Нет авторизации - закрываем соединение
            await websocket.close(code=4001, reason="Unauthorized - no session")
            return

        # Получаем пользователя по сессии (как в AuthMiddleware)
        auth_service = AuthService()
        user = await auth_service.get_user_by_session(auth_session_id)

        if not user:
            # Невалидная сессия - закрываем соединение
            await websocket.close(code=4001, reason="Invalid session")
            return

        # Получаем активную компанию пользователя
        storage = Storage()
        
        if not user.active_company_id:
            await websocket.close(code=4003, reason="User has no active company")
            return
            
        company_data = await storage.get(f"company:{user.active_company_id}", force_global=True)
        if not company_data:
            await websocket.close(code=4003, reason=f"Company {user.active_company_id} not found")
            return
        
        active_company = Company.model_validate_json(company_data)
        
        # Получаем все компании пользователя
        user_companies = []
        for company_id in user.companies.keys():
            comp_data = await storage.get(f"company:{company_id}", force_global=True)
            if comp_data:
                user_companies.append(Company.model_validate_json(comp_data))
        
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
        
        # Запускаем polling уведомлений
        websocket_manager.start_polling(
            chat_session_id, 
            _poll_notifications(chat_session_id),
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
    except Exception as e:
        logger.error(f"WebSocket ошибка для чата {chat_session_id}: {e}")
        websocket_manager.disconnect(chat_session_id, "chat")
    finally:
        # Очищаем контекст после отключения
        clear_context()


async def handle_chat_message(message: dict, session_id: str):
    """Обработка сообщения от клиента чата"""
    message_type = message.get("type")

    if message_type == "USER_MESSAGE":
        # Обработка сообщения пользователя
        # Используем session_id из сообщения для правильного polling
        message_session_id = message["data"].get("session_id", session_id)
        await process_user_message(
            message["data"],
            websocket_session_id=session_id,
            message_session_id=message_session_id,
        )
    elif message_type == "INTERRUPT_RESPONSE":
        # Ответ на запрос ввода от агента
        await process_interrupt_response(message["data"], session_id)
    elif message_type == "PING":
        # Ping/pong для поддержания соединения
        await websocket_manager.send_to_session(session_id, {"type": "PONG"}, "chat")


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
