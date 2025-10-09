"""
WhatsApp webhook endpoints.
Обработка webhooks от WhatsApp Business Cloud API.
"""

import logging
from fastapi import APIRouter, Request, HTTPException, Query

from app.core.storage import Storage
from app.interfaces.whatsapp_interface import WhatsAppInterface

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/webhook/whatsapp/{flow_key:path}")
async def whatsapp_webhook_verify(
    flow_key: str,
    hub_mode: str = Query(alias="hub.mode"),
    hub_verify_token: str = Query(alias="hub.verify_token"),
    hub_challenge: str = Query(alias="hub.challenge")
):
    """
    Верификация webhook для WhatsApp Business API.
    
    WhatsApp отправляет GET запрос с параметрами для верификации.
    Необходимо вернуть hub.challenge если verify_token совпадает.
    
    Args:
        flow_key: Полный ключ flow включая company (company:ssd:flow:...)
        hub_mode: Должен быть "subscribe"
        hub_verify_token: Токен для верификации
        hub_challenge: Значение которое нужно вернуть
    """
    # Извлекаем flow_id из ключа
    if ":flow:" in flow_key:
        flow_id = flow_key.split(":flow:")[1]
    else:
        flow_id = flow_key
    
    logger.info(f"🔍 WhatsApp webhook verification для flow: {flow_id}")
    
    storage = Storage()
    flow_config = await storage.get_flow_config(flow_id)

    if not flow_config:
        logger.error(f"Flow {flow_id} не найден в БД")
        raise HTTPException(status_code=404, detail=f"Flow {flow_id} not found")

    whatsapp_config = flow_config.platforms.get("whatsapp")
    if not whatsapp_config:
        logger.error(f"Flow {flow_id} не поддерживает WhatsApp")
        raise HTTPException(
            status_code=400, detail=f"Flow {flow_id} does not support WhatsApp"
        )

    # Получаем verify_token из конфигурации
    from app.services.variables_service import get_variables_service
    variables_service = get_variables_service()
    
    expected_verify_token = whatsapp_config.get("verify_token", "")
    expected_verify_token = await variables_service.resolve(expected_verify_token)

    # Проверяем режим и токен
    if hub_mode != "subscribe":
        logger.error(f"❌ Неверный hub.mode: {hub_mode}")
        raise HTTPException(status_code=403, detail="Invalid hub.mode")

    if hub_verify_token != expected_verify_token:
        logger.error(f"❌ Неверный verify_token")
        raise HTTPException(status_code=403, detail="Invalid verify_token")

    logger.info(f"✅ WhatsApp webhook верифицирован для flow {flow_id}")
    
    # Возвращаем challenge для подтверждения
    return int(hub_challenge)


@router.post("/webhook/whatsapp/{flow_key:path}")
async def whatsapp_webhook(flow_key: str, request: Request):
    """
    Обработка webhook от WhatsApp Business API.
    
    Получает входящие сообщения, статусы доставки и другие события.
    
    Args:
        flow_key: Полный ключ flow включая company
        request: FastAPI Request с webhook payload
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

    whatsapp_config = flow_config.platforms.get("whatsapp")
    if not whatsapp_config:
        logger.error(f"Flow {flow_id} не поддерживает WhatsApp")
        raise HTTPException(
            status_code=400, detail=f"Flow {flow_id} does not support WhatsApp"
        )

    # Получаем access token
    access_token = await WhatsAppInterface.get_access_token_for_flow(
        flow_id, whatsapp_config
    )
    if not access_token:
        logger.error(f"Не найден access token для WhatsApp flow {flow_id}")
        raise HTTPException(status_code=500, detail="Access token not found")

    # Создаем WhatsApp интерфейс
    whatsapp_interface = WhatsAppInterface(access_token, whatsapp_config)

    # Парсим webhook payload
    raw_data = await request.json()
    
    # Опциональная верификация подписи webhook
    # signature = request.headers.get("x-hub-signature-256", "")
    # app_secret = whatsapp_config.get("app_secret")
    # if app_secret and signature:
    #     body_bytes = await request.body()
    #     is_valid = await WhatsAppInterface.verify_webhook_signature(
    #         body_bytes, signature, app_secret
    #     )
    #     if not is_valid:
    #         logger.error("❌ Неверная подпись webhook")
    #         raise HTTPException(status_code=403, detail="Invalid signature")

    logger.info(f"📨 WhatsApp webhook для {flow_key}: {raw_data.get('entry', [{}])[0].get('id', 'unknown')}")

    # Обрабатываем сообщение через интерфейс
    message = await whatsapp_interface.handle_message(raw_data, flow_id)

    if message:
        # Создаем задачу для обработки
        task_id = await whatsapp_interface.create_task(message, flow_id)
        logger.info(f"📋 Создана задача {task_id} для WhatsApp сообщения от {message.user_id}")
    else:
        logger.info("ℹ️ Webhook обработан, но задача не создана (статус/уведомление)")

    # WhatsApp требует быстрый ответ 200 OK
    return {"status": "ok"}


@router.post("/admin/whatsapp/register/{flow_id}")
async def register_whatsapp_flow(flow_id: str):
    """
    Регистрирует WhatsApp для flow.
    
    Проверяет credentials и возвращает информацию для настройки webhook.
    """
    storage = Storage()
    flow_config = await storage.get_flow_config(flow_id)

    if not flow_config:
        raise HTTPException(status_code=404, detail=f"Flow {flow_id} not found")

    whatsapp_config = flow_config.platforms.get("whatsapp")
    if not whatsapp_config:
        raise HTTPException(
            status_code=400, detail=f"Flow {flow_id} does not have WhatsApp platform"
        )

    # Получаем username/display_name
    display_name = whatsapp_config.get("display_name", "WhatsApp Bot")

    # Регистрируем через WhatsAppInterface
    result = await WhatsAppInterface.register(flow_id, display_name, whatsapp_config)

    return {
        "success": True,
        "flow_id": flow_id,
        "result": result,
    }


@router.post("/admin/whatsapp/send_template/{flow_id}")
async def send_template_message(
    flow_id: str,
    phone_number: str,
    template_name: str,
    language_code: str = "ru",
    parameters: list = None
):
    """
    Отправляет template сообщение для инициации диалога.
    
    Template messages требуют предварительного одобрения в Meta.
    Используются для инициации разговора вне 24-часового окна.
    
    Args:
        flow_id: ID flow
        phone_number: Номер получателя
        template_name: Название template
        language_code: Код языка (ru, en, etc.)
        parameters: Параметры для подстановки в template
    """
    storage = Storage()
    flow_config = await storage.get_flow_config(flow_id)

    if not flow_config:
        raise HTTPException(status_code=404, detail=f"Flow {flow_id} not found")

    whatsapp_config = flow_config.platforms.get("whatsapp")
    if not whatsapp_config:
        raise HTTPException(
            status_code=400, detail=f"Flow {flow_id} does not have WhatsApp"
        )

    access_token = await WhatsAppInterface.get_access_token_for_flow(
        flow_id, whatsapp_config
    )
    phone_number_id = whatsapp_config.get("phone_number_id")
    graph_api_url = whatsapp_config.get("graph_api_url", "https://graph.facebook.com")
    graph_api_version = whatsapp_config.get("graph_api_version", "v18.0")

    # Формируем payload для template
    url = f"{graph_api_url}/{graph_api_version}/{phone_number_id}/messages"
    
    payload = {
        "messaging_product": "whatsapp",
        "to": phone_number,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {
                "code": language_code
            }
        }
    }
    
    # Добавляем параметры если есть
    if parameters:
        payload["template"]["components"] = [{
            "type": "body",
            "parameters": [{"type": "text", "text": param} for param in parameters]
        }]
    
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    import httpx
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, json=payload, headers=headers)
        
        if response.status_code == 200:
            result = await response.json()
            logger.info(f"✅ Template сообщение отправлено: {phone_number}")
            return {
                "success": True,
                "message_id": result.get("messages", [{}])[0].get("id"),
                "phone_number": phone_number
            }
        else:
            logger.error(f"❌ Ошибка отправки template: {response.status_code}")
            logger.error(f"❌ Ответ API: {response.text}")
            raise HTTPException(
                status_code=response.status_code,
                detail=f"WhatsApp API error: {response.text}"
            )


@router.get("/admin/whatsapp/phone_info/{flow_id}")
async def get_phone_info(flow_id: str):
    """
    Получает информацию о телефонном номере WhatsApp Business.
    
    Полезно для проверки статуса и лимитов.
    """
    storage = Storage()
    flow_config = await storage.get_flow_config(flow_id)

    if not flow_config:
        raise HTTPException(status_code=404, detail=f"Flow {flow_id} not found")

    whatsapp_config = flow_config.platforms.get("whatsapp")
    if not whatsapp_config:
        raise HTTPException(
            status_code=400, detail=f"Flow {flow_id} does not have WhatsApp"
        )

    access_token = await WhatsAppInterface.get_access_token_for_flow(
        flow_id, whatsapp_config
    )
    phone_number_id = whatsapp_config.get("phone_number_id")
    graph_api_url = whatsapp_config.get("graph_api_url", "https://graph.facebook.com")
    graph_api_version = whatsapp_config.get("graph_api_version", "v18.0")

    url = f"{graph_api_url}/{graph_api_version}/{phone_number_id}"
    headers = {"Authorization": f"Bearer {access_token}"}

    import httpx
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(url, headers=headers)
        
        if response.status_code == 200:
            phone_data = await response.json()
            return {
                "success": True,
                "phone_data": phone_data
            }
        else:
            raise HTTPException(
                status_code=response.status_code,
                detail=f"WhatsApp API error: {response.text}"
            )

