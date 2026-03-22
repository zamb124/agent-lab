"""
SQLAlchemy модели для Sync Service.

Все таблицы имеют префикс sync_ для изоляции от других сервисов.
Все сущности изолированы по company_id.
Таблица users НЕ создаётся -- используются платформенные пользователи из shared_db.
"""

from datetime import datetime, timezone
from typing import Optional, Dict, Any

from sqlalchemy import (
    String, Text, Boolean, Integer, BigInteger, DateTime,
    Index, ForeignKey, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB

from core.db.models import Base


class SyncSpace(Base):
    """Пространства, объединяющие каналы."""

    __tablename__ = "sync_spaces"

    space_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    created_by_user_id: Mapped[str] = mapped_column(String(64), nullable=False)

    __table_args__ = (
        Index("ix_sync_spaces_company", "company_id"),
    )

    def __repr__(self) -> str:
        return f"<SyncSpace(space_id='{self.space_id}', name='{self.name}', company='{self.company_id}')>"


class SyncChannel(Base):
    """Каналы/чаты (direct, group, topic)."""

    __tablename__ = "sync_channels"

    channel_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    space_id: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("sync_spaces.space_id"), nullable=True
    )
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_private: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    avatar_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    created_by_user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    pinned_message_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    __table_args__ = (
        Index("ix_sync_channels_company", "company_id"),
        Index("ix_sync_channels_space", "space_id"),
    )

    def __repr__(self) -> str:
        return f"<SyncChannel(channel_id='{self.channel_id}', type='{self.type}', company='{self.company_id}')>"


class SyncChannelMember(Base):
    """Участники каналов (роль: owner/admin/member/viewer)."""

    __tablename__ = "sync_channel_members"

    channel_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("sync_channels.channel_id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    last_read_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )

    __table_args__ = (
        Index("ix_sync_channel_members_company", "company_id"),
    )

    def __repr__(self) -> str:
        return f"<SyncChannelMember(channel='{self.channel_id}', user='{self.user_id}', role='{self.role}')>"


class SyncThread(Base):
    """Треды (ветки обсуждения) от корневого сообщения."""

    __tablename__ = "sync_threads"

    thread_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    channel_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("sync_channels.channel_id", ondelete="CASCADE"), nullable=False
    )
    root_message_id: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    created_by_user_id: Mapped[str] = mapped_column(String(64), nullable=False)

    __table_args__ = (
        Index("ix_sync_threads_company", "company_id"),
        Index("ix_sync_threads_channel", "channel_id"),
    )

    def __repr__(self) -> str:
        return f"<SyncThread(thread_id='{self.thread_id}', channel='{self.channel_id}')>"


class SyncMessage(Base):
    """Сообщения в каналах и тредах."""

    __tablename__ = "sync_messages"

    message_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    channel_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("sync_channels.channel_id", ondelete="CASCADE"), nullable=False
    )
    thread_id: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("sync_threads.thread_id", ondelete="SET NULL"), nullable=True
    )
    parent_message_id: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("sync_messages.message_id", ondelete="SET NULL"), nullable=True
    )
    sender_user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    edited_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    reactions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    forwarded_from_channel_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    forwarded_from_channel_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    __table_args__ = (
        Index("ix_sync_messages_company", "company_id"),
        Index("ix_sync_messages_channel", "channel_id"),
        Index("ix_sync_messages_thread", "thread_id"),
        Index("ix_sync_messages_sent_at", "sent_at"),
    )

    def __repr__(self) -> str:
        return f"<SyncMessage(message_id='{self.message_id}', channel='{self.channel_id}')>"


class SyncMessageContent(Base):
    """Полиморфный контент сообщений (text/plain, code/block, git/reference, ...)."""

    __tablename__ = "sync_message_contents"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    message_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("sync_messages.message_id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    order: Mapped[int] = mapped_column(Integer, nullable=False)
    data: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False)

    __table_args__ = (
        Index("ix_sync_message_contents_message", "message_id"),
    )

    def __repr__(self) -> str:
        return f"<SyncMessageContent(id={self.id}, message='{self.message_id}', type='{self.type}')>"


class SyncMessageFile(Base):
    """Связь файлов с сообщениями."""

    __tablename__ = "sync_message_files"

    message_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("sync_messages.message_id", ondelete="CASCADE"),
        primary_key=True,
    )
    file_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("sync_files.file_id", ondelete="CASCADE"),
        primary_key=True,
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False)

    def __repr__(self) -> str:
        return f"<SyncMessageFile(message='{self.message_id}', file='{self.file_id}')>"


class SyncFile(Base):
    """Загруженные файлы (метаданные)."""

    __tablename__ = "sync_files"

    file_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(255), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    storage_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    checksum: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        Index("ix_sync_files_company", "company_id"),
    )

    def __repr__(self) -> str:
        return f"<SyncFile(file_id='{self.file_id}', name='{self.original_name}')>"


class SyncGitResourceRef(Base):
    """Нормализованные Git-ресурсы (repo, MR, PR, commit, file)."""

    __tablename__ = "sync_git_resource_refs"

    git_ref_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    project_key: Mapped[str] = mapped_column(String(255), nullable=False)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    extra: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    __table_args__ = (
        Index("ix_sync_git_refs_company", "company_id"),
        Index("ix_sync_git_refs_provider_kind", "provider", "kind"),
    )

    def __repr__(self) -> str:
        return f"<SyncGitResourceRef(git_ref_id='{self.git_ref_id}', provider='{self.provider}', kind='{self.kind}')>"
