"""
Менеджер namespace для RAG системы.
Управляет созданием namespace для компаний/flow/сессий.
"""

import logging
import hashlib
from app.core.rag.factory import get_default_rag_provider

logger = logging.getLogger(__name__)


def _extract_short_name(scope_id: str, max_length: int = 20) -> str:
    """
    Извлекает короткое имя из scope_id.
    
    Логика:
    - Если есть точка (flow из кода) - берет последнюю часть после точки
    - Если нет точки (flow из БД) - использует весь ID
    - Обрезает до max_length если длиннее
    
    Args:
        scope_id: Полный ID
            - Из кода: "app.flows.lawyer_flow.lawyer_flow" → "lawyer_flow"
            - Из БД: "flow_abc123" → "flow_abc123"
        max_length: Максимальная длина результата
        
    Returns:
        Короткое имя
    """
    if "." in scope_id:
        short_name = scope_id.split(".")[-1]
    else:
        short_name = scope_id
    
    if len(short_name) > max_length:
        short_name = short_name[-max_length:]
    
    return short_name


async def get_or_create_namespace(scope_type: str, scope_id: str) -> str:
    """
    Получает или создает namespace для указанного скоупа.
    
    Args:
        scope_type: Тип скоупа (company, flow, session)
        scope_id: ID скоупа (company_123, app.flows.lawyer_flow.lawyer_flow, etc)
        
    Returns:
        Реальный namespace_id в Agentset
    """
    short_name = _extract_short_name(scope_id, max_length=20)
    scope_hash = hashlib.md5(scope_id.encode()).hexdigest()[:6]
    namespace_name = f"{scope_type}_{short_name}_{scope_hash}"
    
    rag_provider = get_default_rag_provider()
    
    namespaces = await rag_provider.list_namespaces()
    
    for ns in namespaces:
        if ns.name == namespace_name:
            logger.debug(f"Найден существующий namespace: {namespace_name} -> {ns.namespace_id}")
            return ns.namespace_id
    
    namespace = await rag_provider.create_namespace(
        name=namespace_name,
        description=f"Namespace для {scope_type}: {scope_id}",
        slug=namespace_name
    )
    
    logger.info(f"Создан новый namespace: {namespace_name} -> {namespace.namespace_id}")
    
    return namespace.namespace_id

