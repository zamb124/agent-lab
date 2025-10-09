"""
Менеджер namespace для RAG системы.
Управляет созданием namespace для компаний/flow/сессий.
"""

import logging
from app.core.rag.factory import get_default_rag_provider

logger = logging.getLogger(__name__)


async def get_or_create_namespace(scope_type: str, scope_id: str) -> str:
    """
    Получает или создает namespace для указанного скоупа.
    
    Args:
        scope_type: Тип скоупа (company, flow, session)
        scope_id: ID скоупа (company_123, flow_456, session_xyz)
        
    Returns:
        Реальный namespace_id в Agentset
    """
    namespace_name = f"{scope_type}_{scope_id}"
    
    rag_provider = get_default_rag_provider()
    
    namespaces = await rag_provider.list_namespaces()
    
    for ns in namespaces:
        if ns.name == namespace_name:
            logger.debug(f"Найден существующий namespace: {namespace_name} -> {ns.namespace_id}")
            return ns.namespace_id
    
    namespace = await rag_provider.create_namespace(
        name=namespace_name,
        description=f"Namespace для {scope_type}: {scope_id}"
    )
    
    logger.info(f"Создан новый namespace: {namespace_name} -> {namespace.namespace_id}")
    
    return namespace.namespace_id

