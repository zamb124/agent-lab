"""
API для работы с базой знаний (RAG) в frontend.

Эндпоинты для загрузки/удаления документов, привязанных к flow.
Использует RAGRepository для работы с namespace.
"""

import logging
from typing import List, Optional
from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel

from core.context import get_context
from core.files.processors import get_default_file_processor
from core.rag.models import RAGDocument, AgentRAGConfig
from core.rag.namespace_manager import get_or_create_namespace
from apps.frontend.dependencies import FlowRepositoryDep, RAGRepositoryDep

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/knowledge-base", tags=["knowledge-base"])


class UploadDocumentResponse(BaseModel):
    """Ответ на загрузку документа"""
    document_id: str
    name: str
    status: str


class UploadTextRequest(BaseModel):
    """Запрос на загрузку текста"""
    text: str
    document_name: Optional[str] = None
    description: Optional[str] = None


class DocumentListResponse(BaseModel):
    """Список документов"""
    documents: List[RAGDocument]
    total: int


async def _get_namespace_id_for_flow(flow_id: str, flow_repo: FlowRepositoryDep) -> str:
    """
    Определяет namespace_id для flow на основе его rag_config.
    
    Args:
        flow_id: ID flow
        flow_repo: Репозиторий flow
        
    Returns:
        namespace_id для RAG операций
    """
    context = get_context()
    
    if not context or not context.active_company:
        raise HTTPException(status_code=401, detail="Не авторизован")
    
    flow_config = await flow_repo.get(flow_id)
    
    if not flow_config:
        raise HTTPException(status_code=404, detail=f"Flow {flow_id} не найден")
    
    if flow_config.rag_config is None:
        flow_config.rag_config = AgentRAGConfig(
            enabled=True,
            namespace_scope="flow",
            search_scopes=["flow", "company"]
        )
        await flow_repo.set(flow_config)
    
    company_id = context.active_company.company_id
    scope = flow_config.rag_config.namespace_scope
    
    if scope == "flow":
        namespace_id = await get_or_create_namespace("flow", f"{company_id}_{flow_id}")
    elif scope == "company":
        namespace_id = await get_or_create_namespace("company", company_id)
    else:
        raise HTTPException(status_code=400, detail=f"Неподдерживаемый scope: {scope}")
    
    return namespace_id


@router.get("/flows/{flow_id:path}/documents", response_model=DocumentListResponse)
async def get_flow_documents(
    flow_id: str,
    flow_repo: FlowRepositoryDep,
    rag_repo: RAGRepositoryDep
):
    """Получает список документов в базе знаний flow."""
    namespace_id = await _get_namespace_id_for_flow(flow_id, flow_repo)
    
    logger.info(f"Получаем документы из namespace: {namespace_id} для flow {flow_id}")
    
    documents = await rag_repo.list_documents(namespace_id, limit=100)
    
    return DocumentListResponse(documents=documents, total=len(documents))


@router.post("/flows/{flow_id:path}/documents", response_model=UploadDocumentResponse)
async def upload_document_to_flow(
    flow_id: str,
    flow_repo: FlowRepositoryDep,
    rag_repo: RAGRepositoryDep,
    file: UploadFile = File(...)
):
    """
    Загружает документ в базу знаний flow.
    
    Поддерживаемые форматы: PDF, DOCX, TXT, MD, HTML, CSV
    """
    context = get_context()
    
    if not context or not context.active_company:
        raise HTTPException(status_code=401, detail="Не авторизован")
    
    namespace_id = await _get_namespace_id_for_flow(flow_id, flow_repo)
    
    file_content = await file.read()
    
    file_processor = await get_default_file_processor()
    file_record = await file_processor.process_file_from_bytes(
        data=file_content,
        original_name=file.filename or "document",
        content_type=file.content_type or "application/octet-stream",
        uploaded_by=context.user.user_id,
        public=False,
        metadata={"uploaded_via": "rag_ui", "flow_id": flow_id}
    )
    
    document = await rag_repo.upload_document_from_s3(
        namespace_id=namespace_id,
        s3_key=file_record.s3_key,
        document_name=file.filename,
        metadata={"flow_id": flow_id, "uploaded_by": context.user.user_id}
    )
    
    logger.info(f"Документ {file.filename} загружен в flow {flow_id}, document_id={document.document_id}")
    
    return UploadDocumentResponse(
        document_id=document.document_id,
        name=file.filename or "document",
        status="processing"
    )


@router.post("/flows/{flow_id:path}/text", response_model=UploadDocumentResponse)
async def upload_text_to_flow(
    flow_id: str,
    request: UploadTextRequest,
    flow_repo: FlowRepositoryDep,
    rag_repo: RAGRepositoryDep
):
    """Загружает текст напрямую в базу знаний flow."""
    context = get_context()
    
    if not context or not context.active_company:
        raise HTTPException(status_code=401, detail="Не авторизован")
    
    namespace_id = await _get_namespace_id_for_flow(flow_id, flow_repo)
    
    document = await rag_repo.upload_text(
        namespace_id=namespace_id,
        text=request.text,
        document_name=request.document_name,
        metadata={
            "flow_id": flow_id,
            "uploaded_by": context.user.user_id,
            "description": request.description
        }
    )
    
    doc_name = request.document_name or f"Text document ({len(request.text)} chars)"
    
    logger.info(f"Текст загружен в flow {flow_id}, document_id={document.document_id}")
    
    return UploadDocumentResponse(
        document_id=document.document_id,
        name=doc_name,
        status="processing"
    )


@router.delete("/flows/{flow_id:path}/documents/{document_id}")
async def delete_flow_document(
    flow_id: str,
    document_id: str,
    flow_repo: FlowRepositoryDep,
    rag_repo: RAGRepositoryDep
):
    """Удаляет документ из базы знаний flow."""
    namespace_id = await _get_namespace_id_for_flow(flow_id, flow_repo)
    
    success = await rag_repo.delete_document(namespace_id, document_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="Документ не найден")
    
    logger.info(f"Документ {document_id} удален из flow {flow_id}")
    
    return {"success": True, "message": "Документ удален"}

