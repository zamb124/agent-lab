"""
TaskIQ задачи для отправки сообщений через интерфейсы.
"""

import logging
from typing import Any, Dict

from core.tasks.broker import broker
from apps.agents.container import get_agents_container
from apps.agents.interfaces.base import Message

logger = logging.getLogger(__name__)


@broker.task(retry_on_error=True, max_retries=5)
async def send_message_task(
    platform: str,
    flow_id: str,
    session_id: str,
    content: str,
    metadata: Dict[str, Any],
    user_id: str,
) -> bool:
    """
    Отправка сообщения через интерфейс платформы.
    
    Args:
        platform: Платформа (web, telegram, whatsapp, api)
        flow_id: ID flow
        session_id: ID сессии
        content: Текст сообщения
        metadata: Дополнительные данные (chat_id, bot_token и т.д.)
        user_id: ID пользователя
    
    Returns:
        True если сообщение отправлено успешно
    """
    # Системные платформы не требуют отправки
    if platform in ("migration", "system"):
        logger.debug(f"Пропускаем отправку для системной платформы {platform}")
        return True
    
    container = get_agents_container()
    interface_factory = container.interface_factory
    
    # Добавляем flow_id в metadata для telegram
    config = {**metadata, "flow_id": flow_id}
    
    interface = await interface_factory.create_interface(platform, config)
    
    if interface is None:
        logger.info(f"Интерфейс не создан для платформы {platform}, результат сохранен в БД")
        return True
    
    message = Message(
        user_id=user_id,
        session_id=session_id,
        flow_id=flow_id,
        content=content,
        platform=platform,
        metadata=metadata,
    )
    
    await interface.send_message(message)
    
    logger.info(
        f"Сообщение отправлено: session={session_id}, "
        f"platform={platform}, content={content[:80]}{'...' if len(content) > 80 else ''}"
    )
    
    return True


@broker.task(retry_on_error=True, max_retries=3)
async def send_typing_task(
    platform: str,
    flow_id: str,
    session_id: str,
    metadata: Dict[str, Any],
    action: str = "start",
) -> bool:
    """
    Отправка индикатора набора текста.
    
    Args:
        platform: Платформа
        flow_id: ID flow
        session_id: ID сессии
        metadata: Дополнительные данные
        action: "start" или "stop"
    
    Returns:
        True если успешно
    """
    if platform in ("migration", "system", "api"):
        return True
    
    container = get_agents_container()
    interface_factory = container.interface_factory
    
    config = {**metadata, "flow_id": flow_id}
    interface = await interface_factory.create_interface(platform, config)
    
    if interface is None:
        return True
    
    if action == "start":
        await interface.start_typing_indicator(session_id)
    else:
        await interface.stop_typing_indicator(session_id)
    
    return True

