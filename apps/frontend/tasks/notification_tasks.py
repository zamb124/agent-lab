"""
TaskIQ задачи для отправки уведомлений через WebSocket.
"""

import logging
from typing import Any, Dict, Optional

from core.websocket import websocket_manager
from core.rag.factory import get_default_rag_provider
from core.tasks.broker import broker

logger = logging.getLogger(__name__)


@broker.task
async def send_notification_task(
    user_id: str,
    notification_type: str,
    data: Dict[str, Any],
    session_id: str = None,
) -> bool:
    """
    Отправка уведомления через WebSocket.
    
    Args:
        user_id: ID пользователя
        notification_type: Тип уведомления (AGENT_RESPONSE, TYPING, ERROR и т.д.)
        data: Данные уведомления
        session_id: ID сессии (опционально, для отправки в конкретную сессию)
    
    Returns:
        True если уведомление отправлено
    """
    notification = {
        "type": notification_type,
        "data": data,
    }
    
    if session_id:
        # Отправляем в конкретную сессию
        await websocket_manager.send_to_session(session_id, notification, "chat")
        logger.debug(f"Уведомление отправлено в сессию {session_id}: {notification_type}")
    else:
        # Отправляем всем сессиям пользователя
        # TODO: реализовать send_to_user в websocket_manager
        logger.debug(f"Уведомление для пользователя {user_id}: {notification_type}")
    
    return True


@broker.task
async def send_model_update_task(
    model_type: str,
    action: str,
    model_id: str,
    data: Dict[str, Any] = None,
) -> bool:
    """
    Уведомление об изменении модели (для обновления UI).
    
    Args:
        model_type: Тип модели (agent, flow, tool и т.д.)
        action: Действие (created, updated, deleted)
        model_id: ID модели
        data: Дополнительные данные
    
    Returns:
        True если уведомление отправлено
    """
    notification = {
        "type": "MODEL_UPDATE",
        "data": {
            "model_type": model_type,
            "action": action,
            "model_id": model_id,
            "data": data or {},
        },
    }
    
    await websocket_manager.send_to_all(notification, "updates")
    logger.debug(f"Model update: {model_type}/{action}/{model_id}")
    
    return True


@broker.task(retry_on_error=True, max_retries=3)
async def process_rag_document_task(
    namespace_id: str,
    s3_key: str,
    document_name: str,
    flow_id: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Асинхронная обработка документа для RAG (парсинг, chunking, embedding).
    
    Args:
        namespace_id: ID namespace в RAG
        s3_key: Ключ файла в S3
        document_name: Имя документа
        flow_id: ID flow
        metadata: Дополнительные метаданные
    
    Returns:
        Dict с результатом обработки
    """
    logger.info(f"RAG: начало обработки документа {document_name} в namespace {namespace_id}")
    
    try:
        provider = get_default_rag_provider()
        document = await provider.upload_document_from_s3(
            namespace_id=namespace_id,
            s3_key=s3_key,
            document_name=document_name,
            metadata=metadata or {},
        )
        
        logger.info(f"RAG: документ {document_name} успешно обработан, document_id={document.document_id}")
        
        notification = {
            "type": "RAG_DOCUMENT_READY",
            "data": {
                "document_id": document.document_id,
                "document_name": document_name,
                "flow_id": flow_id,
                "status": "completed",
            },
        }
        # Публикуем в Redis для межпроцессной доставки в FastAPI
        await websocket_manager.publish_to_redis(notification, "notifications")
        
        return {
            "status": "completed",
            "document_id": document.document_id,
            "document_name": document_name,
        }
        
    except Exception as e:
        logger.error(f"RAG: ошибка обработки документа {document_name}: {e}", exc_info=True)
        
        notification = {
            "type": "RAG_DOCUMENT_ERROR",
            "data": {
                "document_name": document_name,
                "flow_id": flow_id,
                "error": str(e),
            },
        }
        await websocket_manager.publish_to_redis(notification, "notifications")
        
        raise

