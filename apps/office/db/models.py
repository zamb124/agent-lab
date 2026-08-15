"""
Модели SQLAlchemy для platform_office.
"""

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from core.db.models import Base
from core.types import JsonObject


class OfficeDocumentCatalog(Base):
    """Каталог документов в рамках компании и namespace."""

    __tablename__: str = "office_document_catalogs"

    catalog_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    namespace: Mapped[str] = mapped_column(String(64), nullable=False, default="default")
    parent_catalog_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("office_document_catalogs.catalog_id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    owner_user_id: Mapped[str] = mapped_column(String(100), nullable=False)
    rag_index_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    rag_index_include_subcatalogs: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    rag_index_search_options: Mapped[JsonObject | None] = mapped_column(JSONB, nullable=True)
    rag_index_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    link_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    link_token_hash: Mapped[str | None] = mapped_column(String(128), nullable=True, unique=True)
    link_permission: Mapped[str] = mapped_column(String(16), nullable=False, default="viewer")
    link_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__: tuple[Index, ...] = (
        Index("ix_office_catalogs_company_namespace", "company_id", "namespace"),
        Index(
            "ix_office_catalogs_company_namespace_parent",
            "company_id",
            "namespace",
            "parent_catalog_id",
        ),
    )


class OfficeDocumentBinding(Base):
    """Привязка файла Office (S3 / FileRecord) к компании и namespace.

    `file_id` — первичный ключ: у файла может быть не более одной привязки в каталоге
    документов (глобально, вне зависимости от company/namespace).
    """

    __tablename__: str = "office_document_bindings"

    file_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    namespace: Mapped[str] = mapped_column(String(64), nullable=False, default="default")
    catalog_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("office_document_catalogs.catalog_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    file_category: Mapped[str] = mapped_column(String(32), nullable=False)
    onlyoffice_document_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    created_by_user_id: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_by_user_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    link_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    link_token_hash: Mapped[str | None] = mapped_column(String(128), nullable=True, unique=True)
    link_permission: Mapped[str] = mapped_column(String(16), nullable=False, default="viewer")
    link_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__: tuple[Index, ...] = (
        Index("ix_office_bindings_company_namespace_created", "company_id", "namespace", "created_at"),
        Index("ix_office_bindings_deleted_at", "company_id", "namespace", "deleted_at"),
        # Полный unique для консистентности ORM-схемы; фактический constraint в БД —
        # партиальный (WHERE deleted_at IS NULL), создаётся миграцией office_0013,
        # чтобы soft-deleted привязка не блокировала повторное создание по тому же file_id.
        Index("uq_office_bindings_company_namespace_file", "company_id", "namespace", "file_id", unique=True),
    )


class OfficeDocumentRevision(Base):
    """Снимок версии документа.

    `file_id` — родительская привязка (FK на `office_document_bindings.file_id`);
    `revision_file_id` — снимок содержимого (S3 / `FileRecord.file_id`) на момент
    ревизии, без FK (перекрёстная ссылка на shared-БД файлов).
    """

    __tablename__: str = "office_document_revisions"

    revision_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    file_id: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("office_document_bindings.file_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    revision_file_id: Mapped[str] = mapped_column(String(128), nullable=False)
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    created_by_user_id: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__: tuple[Index, ...] = (
        Index("ix_office_revisions_file_number", "file_id", "revision_number"),
    )


class OfficeDocumentEvent(Base):
    """Журнал активности по документу."""

    __tablename__: str = "office_document_events"

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    file_id: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("office_document_bindings.file_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    company_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[str] = mapped_column(String(100), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
