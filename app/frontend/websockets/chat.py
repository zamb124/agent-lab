"""
WebSocket для чата с агентами
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import json
import logging
import asyncio
from app.core.storage import Storage
from app.interfaces.web_interface import web_interface
from app.core.context import get_context, set_context, clear_context
from app.models import Context
from app.identity.auth_service import AuthService
from app.identity.models import Company
from app.frontend.core.websocket_manager import websocket_manager

logger = logging.getLogger(__name__)

router = APIRouter()


async def _poll_notifications(session_id: str, context: Context):
    """Polling уведомлений из БД для конкретной сессии
    
    Args:
        session_id: ID сессии для polling
        context: Контекст пользователя (передается явно, т.к. asyncio.create_task теряет contextvars)
    """
    
    set_context(context)
    
    storage = Storage()
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
                
                keys = await storage.list_by_prefix(notification_pattern, limit=1000, force_global=True)
                
                if keys:
                    logger.info(f"📬 [Итерация {iteration}] Найдено {len(keys)} уведомлений: {keys[:3]}...")
                    
                    for key in keys:
                        if key not in processed_notifications:
                            notification_data = await storage.get(key)
                            if notification_data:
                                try:
                                    notification = json.loads(notification_data)
                                    notification_type = notification.get('type', 'unknown')
                                    logger.info(f"📨 Отправляем уведомление типа {notification_type}: {key}")
                                    
                                    await websocket_manager.send_to_session(session_id, notification, "chat")
                                    processed_notifications.add(key)
                                    
                                    await storage.delete(key)
                                    logger.debug(f"🗑️ Уведомление удалено: {key}")
                                except json.JSONDecodeError as e:
                                    logger.error(f"❌ Ошибка парсинга уведомления {key}: {e}")
                                    await storage.delete(key)
                                except Exception as e:
                                    logger.error(f"❌ Ошибка обработки уведомления {key}: {e}", exc_info=True)
                
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
