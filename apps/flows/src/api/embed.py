"""
Публичный API для встраиваемых виджетов чата.
"""

import json
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Request, Query
from fastapi.responses import StreamingResponse

from core.context import set_context
from core.models.context_models import Context, Company
from core.models.embed_models import EmbedStatus
from core.models.identity_models import User, UserStatus, AuthProvider

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/embed", tags=["embed"])


@router.get("/{embed_id}/settings")
async def get_embed_settings(embed_id: str, request: Request):
    """
    Публичный endpoint для получения настроек виджета.
    
    Возвращает только публичные настройки UI, не раскрывая внутренние детали.
    Не требует авторизации.
    """
    from apps.flows.src.container import get_container
    
    container = get_container()
    
    # Находим company_id через глобальный маппинг
    embed_mapping_repo = container.embed_mapping_repository
    company_id = await embed_mapping_repo.get_company_id(embed_id)
    
    if not company_id:
        raise HTTPException(status_code=404, detail="Виджет не найден")
    
    # Устанавливаем контекст компании для получения конфига
    anonymous_user = User(
        user_id="anonymous",
        provider=AuthProvider.YANDEX,
        provider_user_id="anonymous",
        email="",
        name="Anonymous",
        status=UserStatus.ACTIVE,
        groups=["guest"],
        companies={company_id: ["guest"]},
        active_company_id=company_id,
    )
    temp_context = Context(
        user=anonymous_user,
        active_company=Company(company_id=company_id, name=""),
        channel="embed",
        metadata={}
    )
    set_context(temp_context)
    
    # Получаем конфигурацию (is_global=False автоматически добавит префикс компании)
    embed_config_repo = container.embed_config_repository
    config = await embed_config_repo.get(embed_id)
    
    if not config:
        raise HTTPException(status_code=404, detail="Конфигурация не найдена")
    
    if config.status != EmbedStatus.ACTIVE:
        raise HTTPException(status_code=403, detail="Виджет отключен")
    
    # Возвращаем только публичные настройки UI
    return {
        "embed_id": config.embed_id,
        "flow_id": config.flow_id,
        "skill_id": config.skill_id,
        "theme": config.theme,
        "position": config.position,
        "show_reasoning": config.show_reasoning,
        "show_tool_calls": config.show_tool_calls,
        "primary_color": config.primary_color,
        "greeting_message": config.greeting_message,
        "placeholder": config.placeholder,
        "branding": config.branding,
    }


@router.get("/{embed_id}/stream")
async def embed_chat_stream(
    embed_id: str,
    message: str = Query(..., description="Сообщение пользователя"),
    context_id: Optional[str] = Query(None, description="ID контекста для продолжения диалога"),
    request: Request = None,
):
    """
    Публичный SSE endpoint для стриминга чата.
    
    Проверяет:
    1. Существование embed_id
    2. Статус виджета (active/disabled)
    3. Разрешенные домены (allowed_origins)
    
    Не требует JWT авторизации - безопасность через проверку домена.
    """
    from apps.flows.src.container import get_container
    from apps.flows.src.channels.a2a import A2AChannel
    from a2a.types import MessageSendParams
    
    container = get_container()
    
    # Находим company_id через глобальный маппинг
    embed_mapping_repo = container.embed_mapping_repository
    company_id = await embed_mapping_repo.get_company_id(embed_id)
    
    if not company_id:
        raise HTTPException(status_code=404, detail="Виджет не найден")
    
    # Устанавливаем контекст компании с анонимным пользователем
    anonymous_user = User(
        user_id="anonymous",
        provider=AuthProvider.YANDEX,
        provider_user_id="anonymous",
        email="",
        name="Anonymous",
        status=UserStatus.ACTIVE,
        groups=["guest"],
        companies={company_id: ["guest"]},
        active_company_id=company_id,
    )
    temp_context = Context(
        user=anonymous_user,
        active_company=Company(company_id=company_id, name=""),
        channel="embed",
        metadata={"embed_id": embed_id}
    )
    set_context(temp_context)
    
    # Получаем конфигурацию
    embed_config_repo = container.embed_config_repository
    config = await embed_config_repo.get(embed_id)
    
    if not config:
        raise HTTPException(status_code=404, detail="Конфигурация не найдена")
    
    if config.status != EmbedStatus.ACTIVE:
        raise HTTPException(status_code=403, detail="Виджет отключен")
    
    # Проверка origin (CORS безопасность)
    origin = request.headers.get("origin", "")
    if config.allowed_origins and origin not in config.allowed_origins:
        logger.warning(f"Запрос с недопустимого домена: {origin} для виджета {embed_id}")
        raise HTTPException(status_code=403, detail="Домен не разрешен")
    
    # Увеличиваем счетчик использований
    await embed_config_repo.increment_usage(embed_id)
    
    # Создаем контекст для диалога
    if not context_id:
        import uuid as uuid_lib
        context_id = f"embed_{embed_id}_{uuid_lib.uuid4().hex[:8]}"
    
    # Запускаем A2A канал
    handler = A2AChannel(
        flow_id=config.flow_id,
        context=temp_context,
        flow_config=None  # Будет загружен автоматически
    )
    
    # Создаем A2A Message
    import uuid as uuid_lib
    a2a_message = {
        "messageId": str(uuid_lib.uuid4()),
        "role": "user",
        "parts": [{"kind": "text", "text": message}],
        "contextId": context_id,
    }
    
    # Параметры сообщения
    params = MessageSendParams(
        message=a2a_message,
        metadata={"skill": config.skill_id},
    )
    
    # SSE генератор
    async def event_generator():
        try:
            async for event in handler.on_message_stream(params, context=None):
                event_data = event.model_dump(by_alias=True, exclude_none=True)
                response = {
                    "jsonrpc": "2.0",
                    "id": f"embed_{embed_id}",
                    "result": event_data
                }
                yield f"data: {json.dumps(response)}\n\n"
        except Exception as e:
            logger.error(f"Ошибка стриминга виджета {embed_id}: {e}", exc_info=True)
            error_response = {
                "jsonrpc": "2.0",
                "id": f"embed_{embed_id}",
                "error": {
                    "code": -32000,
                    "message": "Ошибка обработки сообщения"
                }
            }
            yield f"data: {json.dumps(error_response)}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )

