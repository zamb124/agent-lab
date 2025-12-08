"""
Отправка прогресс-сообщений пользователю во время работы tools.
"""

import logging
from core.context import get_context

logger = logging.getLogger(__name__)


async def send_progress(message: str, chat_action: str = "typing") -> None:
    """
    Отправляет прогресс-сообщение пользователю через интерфейс.
    
    Используется в tools для информирования пользователя о текущем прогрессе:
    - "🔍 Ищу информацию через Tavily..."
    - "📊 Анализирую текст..."
    - "🔬 Извлекаю факты..."
    
    Args:
        message: Текст сообщения для пользователя
        chat_action: Действие для платформы ("typing", "upload_document", etc)
    """
    context = get_context()
    
    if not context:
        raise ValueError("Нет контекста для отправки прогресса")
    
    if not context.interface:
        logger.debug("Нет интерфейса в контексте для отправки прогресса - пропускаем")
        return
    
    if not context.session_id:
        raise ValueError("Нет session_id для отправки прогресса")
    
    try:
        # Отправляем typing индикатор перед сообщением
        await context.interface.send_typing_notification(context.session_id, is_typing=True)
        
        # Отправляем сообщение
        from apps.agents.interfaces.base import Message
        
        if not context.user:
            raise ValueError("Нет пользователя в контексте для отправки прогресса")
        if not context.flow_config:
            raise ValueError("Нет flow_config в контексте для отправки прогресса")
        
        progress_msg = Message(
            user_id=context.user.user_id,
            flow_id=context.flow_config.flow_id,
            session_id=context.session_id,
            content=message,
            platform=context.platform or "web",
            metadata={"type": "progress", "temporary": True}
        )
        
        await context.interface.send_message(progress_msg)
        logger.info(f"📤 Прогресс отправлен: {message[:60]}...")
        
        # Отправляем typing индикатор снова после сообщения
        await context.interface.send_typing_notification(context.session_id, is_typing=True)
        
    except Exception as e:
        logger.warning(f"Не удалось отправить прогресс: {e}")

