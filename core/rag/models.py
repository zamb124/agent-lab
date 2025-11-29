"""
Pydantic модели для RAG системы.
"""

from pydantic import BaseModel
from typing import Optional, List, Dict, Any, Literal
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





