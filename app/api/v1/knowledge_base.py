"""
API endpoints для работы с базой знаний (RAG).
Простые обертки над RAG tools.
"""

import logging
from typing import List
from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel

from app.core.context import get_context
from app.core.storage import Storage
from app.core.file_processor import FileProcessor
from app.models.rag_models import RAGDocument
from app.tools.rag_tools import upload_document_to_knowledge_base

router = APIRouter(
    prefix="/knowledge-base",
    tags=["База знаний (RAG)"],
    responses={
        404: {"description": "Документ или бот не найден"},
        500: {"description": "Ошибка индексации"}
    }
)
logger = logging.getLogger(__name__)


class UploadDocumentResponse(BaseModel):
    """Ответ на загрузку документа"""
    document_id: str
    name: str
    status: str


class DocumentListResponse(BaseModel):
    """Список документов"""
    documents: List[RAGDocument]
    total: int


@router.post("/flows/{flow_id}/documents", response_model=UploadDocumentResponse, summary="Загрузить документ")
async def upload_document_to_flow(
    flow_id: str,
    file: UploadFile = File(...)
):
    """
    Загружает документ в базу знаний бота для использования в RAG.
    
    **Поддерживаемые форматы:**
    - PDF
    - DOCX, DOC
    - TXT, MD
    - HTML
    - CSV
    
    **Процесс:**
    1. Документ загружается и сохраняется
    2. Текст извлекается и разбивается на фрагменты
    3. Создаются векторные embeddings
    4. Индексируется в векторной БД
    5. Бот может искать информацию в этом документе
    
    **Максимальный размер:** 10MB

    Args:
        flow_id: ID бота
        file: Файл документа для загрузки
        
    Returns:
        document_id и статус обработки
    """
    context = get_context()
    
    if not context or not context.active_company:
        raise HTTPException(status_code=401, detail="Не авторизован")
    
    storage = Storage()
    flow_config = await storage.get_flow_config(flow_id)
    
    if not flow_config:
        raise HTTPException(status_code=404, detail=f"Flow {flow_id} не найден")
    
    if flow_config.rag_config is None:
        from app.models.rag_models import AgentRAGConfig
        flow_config.rag_config = AgentRAGConfig(
            enabled=True,
            namespace_scope="flow",
            search_scopes=["flow", "company"]
        )
        await storage.set_flow_config(flow_config)
    
    file_content = await file.read()
    
    file_processor = FileProcessor()
    file_record = await file_processor.process_file_from_bytes(
        data=file_content,
        original_name=file.filename or "document",
        content_type=file.content_type or "application/octet-stream",
        uploaded_by=context.user.user_id,
        public=False,
        metadata={"uploaded_via": "rag_ui", "flow_id": flow_id}
    )
    
    context.flow_config = flow_config
    logger.info(f"🔥 Context перед tool: flow_config={flow_config.flow_id}, rag_scope={flow_config.rag_config.namespace_scope if flow_config.rag_config else None}")
    
    logger.info(f"🔥 Вызываем upload_document_to_knowledge_base tool с file_id={file_record.file_id}")
    
    result_text = await upload_document_to_knowledge_base.ainvoke({
        "file_id": file_record.file_id,
        "description": "Загружен через UI"
    }, config={})
    
    document_id = "uploaded"
    if "ID документа:" in result_text:
        document_id = result_text.split("ID документа:")[1].split("\n")[0].strip()
    
    logger.info(f"✅ Документ {file.filename} загружен через tool: {result_text[:200]}")
    
    return UploadDocumentResponse(
        document_id=document_id,
        name=file.filename,
        status="processing"
    )


@router.get("/flows/{flow_id}/documents", response_model=DocumentListResponse)
async def get_flow_documents(flow_id: str):
    """
    Получает список документов в базе знаний flow.
    Прямой вызов RAG provider для получения списка.
    """
    from app.core.rag.factory import get_default_rag_provider
    from app.core.rag.namespace_manager import get_or_create_namespace
    
    context = get_context()
    
    if not context or not context.active_company:
        raise HTTPException(status_code=401, detail="Не авторизован")
    
    storage = Storage()
    flow_config = await storage.get_flow_config(flow_id)
    
    if not flow_config:
        raise HTTPException(status_code=404, detail=f"Flow {flow_id} не найден")
    
    if flow_config.rag_config is None:
        from app.models.rag_models import AgentRAGConfig
        flow_config.rag_config = AgentRAGConfig(enabled=True, namespace_scope="flow", search_scopes=["flow", "company"])
    
    company_id = context.active_company.company_id
    scope = flow_config.rag_config.namespace_scope
    
    if scope == "flow":
        namespace_id = await get_or_create_namespace("flow", f"{company_id}_{flow_id}")
    elif scope == "company":
        namespace_id = await get_or_create_namespace("company", company_id)
    else:
        return DocumentListResponse(documents=[], total=0)
    
    logger.info(f"🔍 Получаем документы из namespace: {namespace_id} (scope={scope}, flow_id={flow_id})")
    
    rag_provider = get_default_rag_provider()
    documents = await rag_provider.list_documents(namespace_id, limit=100)
    
    logger.info(f"📚 Найдено {len(documents)} документов в namespace {namespace_id}")
    
    return DocumentListResponse(documents=documents, total=len(documents))


@router.delete("/flows/{flow_id}/documents/{document_id}")
async def delete_flow_document(flow_id: str, document_id: str):
    """Удаляет документ из базы знаний flow"""
    from app.core.rag.factory import get_default_rag_provider
    from app.core.rag.namespace_manager import get_or_create_namespace
    
    context = get_context()
    
    if not context or not context.active_company:
        raise HTTPException(status_code=401, detail="Не авторизован")
    
    storage = Storage()
    flow_config = await storage.get_flow_config(flow_id)
    
    if not flow_config:
        raise HTTPException(status_code=404, detail=f"Flow {flow_id} не найден")
    
    if flow_config.rag_config is None:
        from app.models.rag_models import AgentRAGConfig
        flow_config.rag_config = AgentRAGConfig(enabled=True, namespace_scope="flow", search_scopes=["flow", "company"])
    
    company_id = context.active_company.company_id
    scope = flow_config.rag_config.namespace_scope
    
    if scope == "flow":
        namespace_id = await get_or_create_namespace("flow", f"{company_id}_{flow_id}")
    elif scope == "company":
        namespace_id = await get_or_create_namespace("company", company_id)
    else:
        raise HTTPException(status_code=400, detail="Неподдерживаемый scope")
    
    rag_provider = get_default_rag_provider()
    success = await rag_provider.delete_document(namespace_id, document_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="Документ не найден")
    
    logger.info(f"Документ {document_id} удален из flow {flow_id}")
    
    return {"success": True, "message": "Документ удален"}
