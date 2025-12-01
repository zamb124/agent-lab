"""
Инструменты для работы с RAG хранилищем.
Позволяют агентам загружать и искать документы.
"""

import logging
from typing import Optional
from langchain_core.runnables import RunnableConfig

from apps.agents.services.tool_decorator import tool
from apps.agents.container import get_agents_container
from core.rag.namespace_manager import get_or_create_namespace
from core.context import get_context
from core.files.processors import get_default_file_processor

logger = logging.getLogger(__name__)


def _get_rag_config_from_context(context):
    """
    Получает RAG конфигурацию из context.
    Агент может переопределить RAG конфигурацию flow.
    Приоритет: agent_config > flow_config
    Если конфига нет - возвращает None (RAG отключен)
    """
    # Сначала проверяем агентскую конфигурацию (высокий приоритет)
    if context.agent_config and context.agent_config.rag_config:
        return context.agent_config.rag_config

    # Затем проверяем flow конфигурацию
    if context.flow_config and context.flow_config.rag_config:
        return context.flow_config.rag_config

    return None


@tool(is_public=True, group="База знаний", title="Поиск в базе знаний")
async def search_knowledge_base(
    query: str,
    limit: int = 5,
    config: RunnableConfig = None
) -> str:
    """
    Поиск информации в базе знаний.
    Автоматически ищет в настроенных скоупах (компания/агент/сессия).
    
    Args:
        query: Запрос для поиска
        limit: Максимальное количество фрагментов для возврата (по умолчанию 5).
               Увеличь если нужно больше контекста (например, 10-15 для сложных запросов)
        
    Returns:
        Найденные фрагменты документов с релевантностью
    """
    context = get_context()
    rag_config = _get_rag_config_from_context(context)
    
    if not rag_config or not rag_config.enabled:
        return "RAG не настроен для этого flow"
    
    limit = max(1, min(limit, 50))
    
    namespace_ids = []
    company_id = context.active_company.company_id
    flow_id = context.flow_config.flow_id if context.flow_config else "unknown"
    session_id = context.session_id
    
    if "company" in rag_config.search_scopes:
        ns_id = await get_or_create_namespace("company", company_id)
        namespace_ids.append(ns_id)
    
    if "flow" in rag_config.search_scopes:
        ns_id = await get_or_create_namespace("flow", f"{company_id}_{flow_id}")
        namespace_ids.append(ns_id)
    
    if "session" in rag_config.search_scopes:
        ns_id = await get_or_create_namespace("session", f"{company_id}_{flow_id}_{session_id}")
        namespace_ids.append(ns_id)
    
    if not namespace_ids:
        return "Не настроены скоупы поиска"
    
    logger.info(f"Поиск в RAG: query='{query[:50]}...', limit={limit}, scopes={len(namespace_ids)}")
    
    rag_repo = get_agents_container().rag_repository
    all_results = await rag_repo.search_multiple_namespaces(
        namespace_ids=namespace_ids,
        query=query,
        limit=limit
    )
    
    formatted = []
    total_found = 0
    
    for ns_id, results in all_results.items():
        if results:
            scope_name = ns_id.split("_")[-1] if "_" in ns_id else ns_id
            formatted.append(f"\n📁 Результаты из скоупа '{scope_name}':")
            
            for i, result in enumerate(results, 1):
                formatted.append(
                    f"{i}. {result.document_name} (релевантность: {result.score:.2f})\n"
                    f"   {result.content[:300]}..."
                )
                total_found += 1
    
    if not formatted:
        return f"По запросу '{query}' ничего не найдено в базе знаний"
    
    header = f"Найдено {total_found} релевантных фрагментов:\n"
    return header + "\n".join(formatted)


@tool(group="База знаний")
async def upload_document_to_knowledge_base(
    file_id: str,
    description: Optional[str] = None,
    config: RunnableConfig = None
) -> str:
    """
    Загружает документ в базу знаний.
    
    Args:
        file_id: ID файла уже загруженного в S3 через file_tools
        description: Описание документа
        
    Returns:
        Результат загрузки
    """
    context = get_context()
    rag_config = _get_rag_config_from_context(context)
    
    logger.info(f"upload_document: context.flow_config={context.flow_config is not None}, rag_config={rag_config}")
    
    if not rag_config or not rag_config.enabled:
        return "RAG не настроен для этого flow"
    
    file_processor = await get_default_file_processor()
    file_record = await file_processor.get_file_record(file_id)
    
    if not file_record:
        return f"Файл {file_id} не найден в системе"
    
    company_id = context.active_company.company_id
    flow_id = context.flow_config.flow_id if context.flow_config else "unknown"
    session_id = context.session_id
    scope = rag_config.namespace_scope
    
    logger.info(f"upload_document: scope={scope}, company={company_id}, flow={flow_id}, session={session_id}")
    
    if scope == "flow":
        namespace_id = await get_or_create_namespace("flow", f"{company_id}_{flow_id}")
    elif scope == "company":
        namespace_id = await get_or_create_namespace("company", company_id)
    else:
        namespace_id = await get_or_create_namespace("session", f"{company_id}_{flow_id}_{session_id}")
    
    logger.info(f"upload_document: используем namespace_id={namespace_id}")
    
    rag_repo = get_agents_container().rag_repository
    document = await rag_repo.upload_document_from_s3(
        namespace_id=namespace_id,
        s3_key=file_record.s3_key,
        document_name=file_record.original_name,
        metadata={
            "description": description,
            "uploaded_by": context.user.user_id,
            "file_id": file_id,
            "original_name": file_record.original_name
        }
    )
    
    scope_name = {
        "flow": "базу текущего flow",
        "company": "общую базу компании",
        "session": "базу текущей сессии"
    }.get(scope, scope)
    
    return (
        f"✅ Документ '{document.name}' успешно добавлен в {scope_name}\n"
        f"ID документа: {document.document_id}\n"
        f"Статус: {document.status}\n"
        f"Документ будет проиндексирован и доступен для поиска через несколько минут"
    )


@tool(is_public=True, group="База знаний", title="Загрузить текст в базу знаний")
async def upload_text_to_knowledge_base(
    text: str,
    document_name: Optional[str] = None,
    description: Optional[str] = None,
    config: RunnableConfig = None
) -> str:
    """
    Загружает текст напрямую в базу знаний бота.

    Args:
        text: Текст для загрузки в RAG
        document_name: Имя документа (опционально, будет сгенерировано автоматически)
        description: Описание документа

    Returns:
        Результат загрузки
    """
    context = get_context()
    rag_config = _get_rag_config_from_context(context)

    if not rag_config or not rag_config.enabled:
        return "RAG не настроен для этого flow"

    company_id = context.active_company.company_id
    flow_id = context.flow_config.flow_id if context.flow_config else "unknown"
    session_id = context.session_id
    scope = rag_config.namespace_scope

    if scope == "flow":
        namespace_id = await get_or_create_namespace("flow", f"{company_id}_{flow_id}")
    elif scope == "company":
        namespace_id = await get_or_create_namespace("company", company_id)
    else:
        namespace_id = await get_or_create_namespace("session", f"{company_id}_{flow_id}_{session_id}")

    doc_name = document_name or f"Text document ({len(text)} chars)"

    rag_repo = get_agents_container().rag_repository
    document = await rag_repo.upload_text(
        namespace_id=namespace_id,
        text=text,
        document_name=doc_name,
        metadata={
            "description": description,
            "uploaded_by": context.user.user_id,
        }
    )

    scope_name = {
        "flow": "базу текущего flow",
        "company": "общую базу компании",
        "session": "базу текущей сессии"
    }.get(scope, scope)

    return (
        f"✅ Текст '{document.name}' успешно добавлен в {scope_name}\n"
        f"ID документа: {document.document_id}\n"
        f"Статус: {document.status}\n"
        f"Текст будет проиндексирован и доступен для поиска через несколько минут"
    )


@tool(is_public=True, group="База знаний", title="Список документов")
async def list_documents_in_knowledge_base(
    config: RunnableConfig = None
) -> str:
    """
    Показывает список всех документов в базе знаний.

    Returns:
        Список документов с деталями
    """
    context = get_context()
    rag_config = _get_rag_config_from_context(context)
    
    if not rag_config or not rag_config.enabled:
        return "RAG не настроен для этого flow"
    
    company_id = context.active_company.company_id
    flow_id = context.flow_config.flow_id if context.flow_config else "unknown"
    session_id = context.session_id
    scope = rag_config.namespace_scope
    
    if scope == "flow":
        namespace_id = await get_or_create_namespace("flow", f"{company_id}_{flow_id}")
    elif scope == "company":
        namespace_id = await get_or_create_namespace("company", company_id)
    else:
        namespace_id = await get_or_create_namespace("session", f"{company_id}_{flow_id}_{session_id}")
    
    logger.info(f"list_documents: используем namespace_id={namespace_id}")
    
    rag_repo = get_agents_container().rag_repository
    documents = await rag_repo.list_documents(namespace_id, limit=50)
    
    if not documents:
        return "В базе знаний пока нет документов"
    
    formatted = [f"📚 Документы в базе знаний ({len(documents)}):"]
    
    for i, doc in enumerate(documents, 1):
        status_emoji = {
            "ready": "✅",
            "processing": "⏳",
            "failed": "❌"
        }.get(doc.status, "❓")
        
        # Используем signed URL (срок 1 час) вместо публичного
        signed_url = doc.metadata.get("signed_url")
        
        if signed_url:
            # Signed URL уже правильно закодирован, не нужно quote!
            doc_name = f"**[{doc.name}]({signed_url})**"
        else:
            doc_name = f"**{doc.name}**"
        
        formatted.append(
            f"\n{i}. {status_emoji} {doc_name}\n"
            f"   - ID: `{doc.document_id}`\n"
            f"   - Статус: {doc.status}\n"
            f"   - Создан: {doc.created_at or 'неизвестно'}"
        )
    
    return "\n".join(formatted)

