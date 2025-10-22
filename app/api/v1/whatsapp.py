"""
WhatsApp webhook endpoints.
Обработка webhooks от WhatsApp Business Cloud API.
"""

import logging
from fastapi import APIRouter, Request, HTTPException, Query

from app.interfaces.whatsapp_interface import WhatsAppInterface
from app.frontend.dependencies import FlowRepositoryDep, StorageDep
from app.models import FlowConfig
from app.core.container import get_container

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/webhook/whatsapp/{flow_key:path}")
async def whatsapp_webhook_verify(
    flow_key: str,
    storage: StorageDep,
    hub_mode: str = Query(alias="hub.mode"),
    hub_verify_token: str = Query(alias="hub.verify_token"),
    hub_challenge: str = Query(alias="hub.challenge"),
):
    """
    Верификация webhook для WhatsApp Business API.
    
    WhatsApp отправляет GET запрос с параметрами для верификации.
    Необходимо вернуть hub.challenge если verify_token совпадает.
    """
    flow_data = await storage.get(flow_key, force_global=True)
    
    if not flow_data:
        raise HTTPException(status_code=404, detail=f"Flow not found")
    
    flow_config = FlowConfig.model_validate_json(flow_data)
    whatsapp_config = flow_config.platforms.get("whatsapp")
    
    if not whatsapp_config:
        raise HTTPException(status_code=400, detail="Flow does not support WhatsApp")

    if hub_mode != "subscribe":
        raise HTTPException(status_code=403, detail="Invalid hub.mode")

    variables_service = get_container().variables_service
    expected_verify_token = await variables_service.resolve(whatsapp_config.get("verify_token", ""))

    if hub_verify_token != expected_verify_token:
        logger.error(f"❌ Неверный verify_token: ожидалось '{expected_verify_token}', получено '{hub_verify_token}'")
        raise HTTPException(status_code=403, detail="Invalid verify_token")

    logger.info(f"✅ WhatsApp webhook верифицирован")
    return int(hub_challenge)


@router.post("/webhook/whatsapp/{flow_key:path}")
async def whatsapp_webhook(flow_key: str, request: Request, storage: StorageDep):
    """
    Обработка webhook от WhatsApp Business API.
    Получает входящие сообщения, статусы доставки и другие события.
    """
    flow_data = await storage.get(flow_key, force_global=True)
    
    if not flow_data:
        raise HTTPException(status_code=404, detail="Flow not found")
    
    flow_config = FlowConfig.model_validate_json(flow_data)
    whatsapp_config = flow_config.platforms.get("whatsapp")
    
    if not whatsapp_config:
        raise HTTPException(status_code=400, detail="Flow does not support WhatsApp")

    flow_id = flow_key.split(":flow:")[-1]
    access_token = await WhatsAppInterface.get_access_token_for_flow(flow_id, whatsapp_config)
    if not access_token:
        raise HTTPException(status_code=500, detail="Access token not found")

    whatsapp_interface = WhatsAppInterface(access_token, whatsapp_config)
    raw_data = await request.json()
    
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
async def register_whatsapp_flow(flow_id: str, flow_repo: FlowRepositoryDep):
    """
    Регистрирует WhatsApp для flow.
    
    Проверяет credentials и возвращает информацию для настройки webhook.
    """
    flow_config = await flow_repo.get(flow_id)

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
    flow_repo: FlowRepositoryDep,
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
    flow_config = await flow_repo.get(flow_id)

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
            result = response.json()
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
async def get_phone_info(flow_id: str, flow_repo: FlowRepositoryDep):
    """
    Получает информацию о телефонном номере WhatsApp Business.
    
    Полезно для проверки статуса и лимитов.
    """
    flow_config = await flow_repo.get(flow_id)

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
            phone_data = response.json()
            return {
                "success": True,
                "phone_data": phone_data
            }
        else:
            raise HTTPException(
                status_code=response.status_code,
                detail=f"WhatsApp API error: {response.text}"
            )

