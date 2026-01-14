"""
Pydantic модели для RAG системы.
"""

from pydantic import BaseModel, ConfigDict
from typing import Optional, List, Dict, Any, Literal
from datetime import datetime
from core.fields import Field


class RAGDocument(BaseModel):
    """Универсальная модель документа для RAG"""
    
    document_id: str
    name: str
    namespace: str
    content: Optional[str] = None
    metadata: Dict[str, Any] = {}
    status: str = "processing"
    created_at: Optional[str] = None


class RAGSearchResult(BaseModel):
    """Универсальная модель результата поиска"""
    
    content: str
    score: float
    document_id: str
    document_name: str
    metadata: Dict[str, Any] = {}
    namespace: str


class RAGNamespace(BaseModel):
    """Универсальная модель namespace"""
    
    namespace_id: str
    name: str
    description: Optional[str] = None
    document_count: int = 0
    created_at: Optional[str] = None
    metadata: Dict[str, Any] = {}


class AgentRAGConfig(BaseModel):
    """Конфигурация RAG для flow"""
    
    enabled: bool = False
    
    namespace_scope: Literal["flow", "company", "session"] = Field(
        default="flow",
        title="Скоуп хранения",
        description="Где хранить документы: company (общие), flow (для этого flow), session (для сессии)"
    )
    
    search_scopes: List[Literal["flow", "company", "session"]] = Field(
        default_factory=lambda: ["flow"],
        title="Скоупы поиска",
        description="Где искать документы при запросах"
    )
    
    auto_index_messages: bool = Field(
        default=False,
        title="Автоматическая индексация",
        description="Автоматически индексировать сообщения из сессии"
    )


class DocumentProcessingStatus(BaseModel):
    """
    Статус обработки документа в RAG.
    
    Статусы:
    - pending: документ принят, ожидает обработки
    - processing: документ обрабатывается (парсинг, chunking, индексация)
    - completed: документ успешно проиндексирован
    - failed: ошибка при обработке
    """
    
    model_config = ConfigDict(from_attributes=True)
    
    document_id: str
    task_id: str
    namespace_id: str
    document_name: str
    status: Literal["pending", "processing", "completed", "failed"]
    error_message: Optional[str] = None
    s3_key: Optional[str] = None
    s3_bucket: Optional[str] = None
    file_size: Optional[int] = None
    chunks_count: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None
    extra_metadata: Optional[Dict[str, Any]] = None













