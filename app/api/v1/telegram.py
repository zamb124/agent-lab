"""
Telegram webhook endpoints.
Создают интерфейсы на лету для обработки сообщений.
"""

import logging
from fastapi import APIRouter, Request, HTTPException

from app.core.storage import Storage
from app.interfaces.telegram_interface import TelegramInterface

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/webhook/telegram/{flow_key:path}")
async def telegram_webhook(flow_key: str, request: Request):
    """
    Universal Telegram webhook для любого flow.
    Создает TelegramInterface на лету.
    
    Args:
        flow_key: Полный ключ flow включая company (company:ssd:flow:app.flows...)
    """
    # Извлекаем flow_id из ключа
    if ":flow:" in flow_key:
        flow_id = flow_key.split(":flow:")[1]
    else:
        flow_id = flow_key
    
    storage = Storage()
    flow_config = await storage.get_flow_config(flow_id)

    if not flow_config:
        logger.error(f"Flow {flow_id} не найден в БД")
        raise HTTPException(status_code=404, detail=f"Flow {flow_id} not found")

    telegram_config = flow_config.platforms.get("telegram")
    if not telegram_config:
        logger.error(f"Flow {flow_id} не поддерживает Telegram")
        raise HTTPException(
            status_code=400, detail=f"Flow {flow_id} does not support Telegram"
        )

    bot_token = await TelegramInterface.get_bot_token_for_flow(
        flow_id, telegram_config
    )
    if not bot_token:
        logger.error(f"Не найден токен для Telegram бота flow {flow_id}")
        raise HTTPException(status_code=500, detail="Bot token not found")

    telegram_interface = TelegramInterface(bot_token, telegram_config)

    raw_data = await request.json()
    logger.info(
        f"📨 Telegram webhook для {flow_key}: update {raw_data.get('update_id', 'unknown')}"
    )

    message = await telegram_interface.handle_message(raw_data, flow_id)
    if not message:
        return {"ok": True}

    task_id = await telegram_interface.create_task(message, flow_id)

    if task_id:
        logger.info(
            f"📋 Создана задача {task_id} для {flow_key} от пользователя {message.user_id}"
        )
    else:
        logger.info(f"⏳ Задача не создана - сессия занята для {message.user_id}")

    return {"ok": True}


@router.post("/admin/telegram/set_webhook/{flow_id}")
async def set_telegram_webhook(flow_id: str, webhook_base_url: str):
    """
    Устанавливает webhook для Telegram бота flow.
    """
    try:
        # Получаем flow config
        storage = Storage()
        flow_config = await storage.get_flow_config(flow_id)

        if not flow_config:
            raise HTTPException(status_code=404, detail=f"Flow {flow_id} not found")

        telegram_config = flow_config.platforms.get("telegram")
        if not telegram_config:
            raise HTTPException(
                status_code=400, detail=f"Flow {flow_id} does not support Telegram"
            )

        # Получаем токен
        bot_token = await TelegramInterface.get_bot_token_for_flow(
            flow_id, telegram_config
        )
        if not bot_token:
            raise HTTPException(status_code=500, detail="Bot token not found")

        # Формируем URL webhook
        webhook_url = f"{webhook_base_url}/api/v1/webhook/telegram/{flow_id}"

        # Устанавливаем webhook
        success = await TelegramInterface.set_webhook(bot_token, webhook_url)

        if success:
            # Также устанавливаем команды бота
            telegram_interface = TelegramInterface(bot_token, telegram_config)
            await telegram_interface.setup_commands()

            return {
                "success": True,
                "flow_id": flow_id,
                "webhook_url": webhook_url,
                "bot_username": telegram_config.get("username"),
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to set webhook")

    except Exception as e:
        logger.error(f"Ошибка установки webhook для {flow_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/admin/telegram/setup_commands/{flow_id}")
async def setup_telegram_commands(flow_id: str):
    """Устанавливает команды для Telegram бота"""
    # Получаем flow config из БД
    storage = Storage()
    flow_config = await storage.get_flow_config(flow_id)

    if not flow_config:
        raise HTTPException(status_code=404, detail=f"Flow {flow_id} not found")

    # Проверяем что flow поддерживает Telegram
    telegram_config = flow_config.platforms.get("telegram")
    if not telegram_config:
        raise HTTPException(
            status_code=400, detail=f"Flow {flow_id} does not support Telegram"
        )

    # Получаем токен бота
    bot_token = await TelegramInterface.get_bot_token_for_flow(flow_id, telegram_config)
    if not bot_token:
        raise HTTPException(status_code=500, detail="Bot token not found")

    # Устанавливаем команды
    telegram_interface = TelegramInterface(bot_token, telegram_config)
    success = await telegram_interface.setup_commands()

    if success:
        return {
            "success": True,
            "flow_id": flow_id,
            "bot_username": telegram_config.get("username"),
            "commands": ["start", "help", "clear"],
        }
    else:
        raise HTTPException(status_code=500, detail="Failed to setup commands")
