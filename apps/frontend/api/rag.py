"""
API endpoints для RAG модуля
"""

import logging
from typing import Optional, List
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Query
from pydantic import BaseModel
import httpx

from core.config import get_settings
from core.rag.factory import get_rag_provider, RAG_PROVIDERS
from core.rag.models import RAGDocument, RAGSearchResult, RAGNamespace

logger = logging.getLogger(__name__)


def handle_provider_error(e: Exception) -> HTTPException:
    """Преобразует ошибки провайдера в HTTPException"""
    if isinstance(e, HTTPException):
        return e
    if isinstance(e, httpx.HTTPStatusError):
        status_code = e.response.status_code
        if status_code == 401:
            return HTTPException(status_code=404, detail="Ресурс не найден или недоступен")
        if status_code == 422:
            return HTTPException(status_code=400, detail=f"Некорректные данные: {e.response.text[:200]}")
        if status_code >= 500:
            return HTTPException(status_code=502, detail="Ошибка RAG провайдера")
        return HTTPException(status_code=status_code, detail=str(e))
    if isinstance(e, ValueError):
        return HTTPException(status_code=400, detail=str(e))
    logger.error(f"Неожиданная ошибка RAG: {e}", exc_info=True)
    return HTTPException(status_code=500, detail="Внутренняя ошибка сервера")

router = APIRouter(prefix="/rag", tags=["rag-api"])


class ProviderInfo(BaseModel):
    """Информация о RAG провайдере"""
    name: str
    enabled: bool
    is_default: bool


class SearchRequest(BaseModel):
    """Запрос на поиск"""
    query: str
    limit: int = 10


class SearchResultItem(BaseModel):
    """Результат поиска"""
    content: str
    score: float
    document_id: str
    document_name: str
    namespace: str


class NamespaceCreateRequest(BaseModel):
    """Запрос на создание неймспейса"""
    name: str
    description: Optional[str] = None


@router.get("/providers", response_model=List[ProviderInfo])
async def list_providers():
    """Список доступных RAG провайдеров"""
    settings = get_settings()
    
    if not settings.rag.enabled:
        return []
    
    providers = []
    default_provider = settings.rag.default_provider
    
    for name in RAG_PROVIDERS.keys():
        provider_config = settings.rag.providers.get(name)
        if provider_config:
            enabled = provider_config.enabled if hasattr(provider_config, 'enabled') else False
        else:
            enabled = False
        
        providers.append(ProviderInfo(
            name=name,
            enabled=enabled,
            is_default=(name == default_provider)
        ))
    
    return providers


@router.get("/namespaces", response_model=List[RAGNamespace])
async def list_namespaces(provider: Optional[str] = Query(None, description="Имя провайдера")):
    """Список всех неймспейсов провайдера"""
    settings = get_settings()
    
    if not settings.rag.enabled:
        raise HTTPException(status_code=400, detail="RAG не включен")
    
    try:
        rag_provider = get_rag_provider(provider)
        namespaces = await rag_provider.list_namespaces()
        return namespaces
    except Exception as e:
        raise handle_provider_error(e)


@router.post("/namespaces", response_model=RAGNamespace)
async def create_namespace(request: NamespaceCreateRequest, provider: Optional[str] = Query(None)):
    """Создать новый неймспейс"""
    settings = get_settings()
    
    if not settings.rag.enabled:
        raise HTTPException(status_code=400, detail="RAG не включен")
    
    try:
        rag_provider = get_rag_provider(provider)
        namespace = await rag_provider.create_namespace(
            name=request.name,
            description=request.description
        )
        return namespace
    except Exception as e:
        raise handle_provider_error(e)


@router.delete("/namespaces/{namespace_id}")
async def delete_namespace(namespace_id: str, provider: Optional[str] = Query(None)):
    """Удалить неймспейс"""
    settings = get_settings()
    
    if not settings.rag.enabled:
        raise HTTPException(status_code=400, detail="RAG не включен")
    
    try:
        rag_provider = get_rag_provider(provider)
        success = await rag_provider.delete_namespace(namespace_id)
    except Exception as e:
        raise handle_provider_error(e)
    
    if not success:
        raise HTTPException(status_code=404, detail="Неймспейс не найден")
    return {"status": "deleted", "namespace_id": namespace_id}


@router.get("/namespaces/{namespace_id}/documents", response_model=List[RAGDocument])
async def list_documents(
    namespace_id: str,
    provider: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000)
):
    """Список документов в неймспейсе"""
    settings = get_settings()
    
    if not settings.rag.enabled:
        raise HTTPException(status_code=400, detail="RAG не включен")
    
    try:
        rag_provider = get_rag_provider(provider)
        documents = await rag_provider.list_documents(namespace_id, limit=limit)
        return documents
    except Exception as e:
        raise handle_provider_error(e)


@router.post("/namespaces/{namespace_id}/documents", response_model=RAGDocument)
async def upload_document(
    namespace_id: str,
    file: UploadFile = File(...),
    document_name: Optional[str] = Form(None),
    provider: Optional[str] = Query(None)
):
    """Загрузить документ в неймспейс"""
    import tempfile
    import os
    
    settings = get_settings()
    
    if not settings.rag.enabled:
        raise HTTPException(status_code=400, detail="RAG не включен")
    
    tmp_path = None
    try:
        rag_provider = get_rag_provider(provider)
        
        suffix = os.path.splitext(file.filename or "")[1]
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name
        
        document = await rag_provider.upload_document_from_file(
            namespace_id=namespace_id,
            file_path=tmp_path,
            document_name=document_name or file.filename
        )
        return document
    except Exception as e:
        raise handle_provider_error(e)
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


@router.delete("/namespaces/{namespace_id}/documents/{document_id}")
async def delete_document(
    namespace_id: str,
    document_id: str,
    provider: Optional[str] = Query(None)
):
    """Удалить документ из неймспейса"""
    settings = get_settings()
    
    if not settings.rag.enabled:
        raise HTTPException(status_code=400, detail="RAG не включен")
    
    try:
        rag_provider = get_rag_provider(provider)
        success = await rag_provider.delete_document(namespace_id, document_id)
    except Exception as e:
        raise handle_provider_error(e)
    
    if not success:
        raise HTTPException(status_code=404, detail="Документ не найден")
    return {"status": "deleted", "document_id": document_id}


@router.post("/namespaces/{namespace_id}/search", response_model=List[SearchResultItem])
async def search_documents(
    namespace_id: str,
    request: SearchRequest,
    provider: Optional[str] = Query(None)
):
    """Поиск по документам в неймспейсе"""
    settings = get_settings()
    
    if not settings.rag.enabled:
        raise HTTPException(status_code=400, detail="RAG не включен")
    
    try:
        rag_provider = get_rag_provider(provider)
        results = await rag_provider.search(
            namespace_id=namespace_id,
            query=request.query,
            limit=request.limit
        )
        
        return [
            SearchResultItem(
                content=r.content,
                score=r.score,
                document_id=r.document_id,
                document_name=r.document_name,
                namespace=r.namespace
            )
            for r in results
        ]
    except Exception as e:
        raise handle_provider_error(e)


@router.get("/namespaces/{namespace_id}/documents/{document_id}/download")
async def get_document_download_url(
    namespace_id: str,
    document_id: str,
    provider: Optional[str] = Query(None)
):
    """Получить URL для скачивания документа"""
    settings = get_settings()
    
    if not settings.rag.enabled:
        raise HTTPException(status_code=400, detail="RAG не включен")
    
    try:
        rag_provider = get_rag_provider(provider)
        
        if not hasattr(rag_provider, 'generate_download_url'):
            raise HTTPException(status_code=404, detail="Провайдер не поддерживает скачивание")
        
        url = await rag_provider.generate_download_url(namespace_id, document_id)
    except Exception as e:
        raise handle_provider_error(e)
    
    if not url:
        raise HTTPException(status_code=404, detail="Документ не найден или не имеет файла")
    return {"download_url": url}

