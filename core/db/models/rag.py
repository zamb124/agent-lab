"""
Модели RAG-базы данных.

Таблицы rag БД: document_processing_status, vector_documents.
Конфигурация нарезки/парсинга — в ``rag.document_indexing`` (merged settings), не в БД.
"""

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import (
    Boolean,
    Computed,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from pgvector.sqlalchemy import Vector

from core.db.models.base import Base


class DocumentProcessingStatus(Base):
    """
    Статус обработки документов в RAG.

    Статусы: pending, processing, completed, failed.
    Одна строка на document_id
    """

    __tablename__ = "document_processing_status"

    document_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    task_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True, unique=True)
    namespace_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    document_name: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    error_message: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    s3_key: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    s3_bucket: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    file_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    chunks_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    extra_metadata: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    ttl_seconds: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("864000"),
    )

    __table_args__ = (
        Index("ix_document_status_task_id", "task_id"),
        Index("ix_document_status_namespace_status", "namespace_id", "status"),
    )

    def __repr__(self) -> str:
        return f"<DocumentProcessingStatus(document_id='{self.document_id}', status='{self.status}')>"


class VectorDocument(Base):
    """
    Хранилище векторных документов для семантического поиска через pgvector.
    Изоляция данных через namespace_id и company_id.
    """

    __tablename__ = "vector_documents"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    namespace_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    company_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    document_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    document_name: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_tsv: Mapped[Any] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('simple', coalesce(content, ''))", persisted=True),
    )
    embedding = mapped_column(Vector(1024), nullable=True)
    embedding_model: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, default=None, index=True,
        comment="Идентификатор модели эмбеддинга (напр. qwen/qwen3-embedding-8b). NULL у старых чанков до переиндексации."
    )
    chunk_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_chunks: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("ix_vd_namespace_company", "namespace_id", "company_id"),
        Index("ix_vd_document_id", "document_id"),
        Index(
            "ix_vd_content_tsv_gin",
            "content_tsv",
            postgresql_using="gin",
        ),
    )
