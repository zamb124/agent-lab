"""
Модели SQLAlchemy для platform_office.
"""

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from core.db.models import Base


class OfficeDocumentCatalog(Base):
    """Каталог документов в рамках компании и CRM namespace; владелец управляет участниками."""

    __tablename__ = "office_document_catalogs"

    catalog_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    namespace: Mapped[str] = mapped_column(String(64), nullable=False, default="default")
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    owner_user_id: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("ix_office_catalogs_company_namespace", "company_id", "namespace"),
    )


class OfficeCatalogMember(Base):
    """Пользователь с доступом к каталогу (владелец хранится в catalog.owner_user_id)."""

    __tablename__ = "office_catalog_members"

    catalog_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("office_document_catalogs.catalog_id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )


class OfficeDocumentBinding(Base):
    """Привязка файла Office (S3 / FileRecord) к компании и namespace."""

    __tablename__ = "office_document_bindings"

    binding_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    namespace: Mapped[str] = mapped_column(String(64), nullable=False, default="default")
    catalog_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("office_document_catalogs.catalog_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    file_id: Mapped[str] = mapped_column(String(128), nullable=False)
    document_type: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    created_by_user_id: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("ix_office_bindings_company_namespace_created", "company_id", "namespace", "created_at"),
    )
