"""
SQLAlchemy модели для Sync Service.

Все таблицы имеют префикс sync_ для изоляции от других сервисов.
Все сущности изолированы по company_id.
Таблица users НЕ создаётся -- используются платформенные пользователи из shared_db.
"""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from core.db.models import Base
from core.types import JsonObject


class SyncChannel(Base):
    """Каналы/чаты (direct, group, topic).

    Привязка к платформенному namespace — строковое поле `namespace`
    (`apps/crm/api/namespaces.py` создаёт/удаляет, sync читает через
    `NamespaceRepository`). Дефолты транскрипции (`transcribe_voice_messages`,
    `speech_to_chat_enabled`) живут в `Namespace.sync_settings`; на канале
    оставлены оверрайды для редких случаев точечной настройки.
    """

    __tablename__ = "sync_channels"

    channel_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    namespace: Mapped[str] = mapped_column(String(100), nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_private: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    created_by_user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    pinned_message_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    transcribe_voice_messages: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    speech_to_chat_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __table_args__ = (
        Index("ix_sync_channels_company", "company_id"),
        Index("ix_sync_channels_company_namespace", "company_id", "namespace"),
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
    last_read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )
    notifications_muted: Mapped[bool] = mapped_column(
        Boolean(),
        default=False,
        nullable=False,
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
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
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
    thread_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("sync_threads.thread_id", ondelete="SET NULL"), nullable=True
    )
    parent_message_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("sync_messages.message_id", ondelete="SET NULL"), nullable=True
    )
    call_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("sync_calls.call_id", ondelete="SET NULL"), nullable=True
    )
    sender_user_id: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reactions: Mapped[list[JsonObject]] = mapped_column(JSONB, nullable=False, default=list)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    forwarded_from_channel_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    forwarded_from_channel_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    __table_args__ = (
        Index("ix_sync_messages_company", "company_id"),
        Index("ix_sync_messages_channel", "channel_id"),
        Index("ix_sync_messages_thread", "thread_id"),
        Index("ix_sync_messages_sent_at", "sent_at"),
        Index("ix_sync_messages_call_id", "call_id"),
        Index("ix_sync_messages_channel_call", "channel_id", "call_id"),
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
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

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
    content_type: Mapped[str] = mapped_column(String(255), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    storage_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    checksum: Mapped[str | None] = mapped_column(String(128), nullable=True)
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
    extra: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    __table_args__ = (
        Index("ix_sync_git_refs_company", "company_id"),
        Index("ix_sync_git_refs_provider_kind", "provider", "kind"),
    )

    def __repr__(self) -> str:
        return f"<SyncGitResourceRef(git_ref_id='{self.git_ref_id}', provider='{self.provider}', kind='{self.kind}')>"


class SyncCall(Base):
    """Звонок в канале (аудио/видео).

    mode:   "p2p"  — браузер ↔ браузер (сигналинг через WS, без SFU);
            "sfu"  — через LiveKit SFU (3+ участников).
    status: "ringing" → "active" → "ended".
    """

    __tablename__ = "sync_calls"

    call_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    channel_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("sync_channels.channel_id", ondelete="CASCADE"), nullable=False
    )
    mode: Mapped[str] = mapped_column(String(8), nullable=False)
    call_type: Mapped[str] = mapped_column(String(8), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ringing")
    livekit_room_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    created_by_user_id: Mapped[str] = mapped_column(String(64), nullable=False)

    __table_args__ = (
        Index("ix_sync_calls_company", "company_id"),
        Index("ix_sync_calls_channel", "channel_id"),
        Index("ix_sync_calls_status", "status"),
    )

    def __repr__(self) -> str:
        return f"<SyncCall(call_id='{self.call_id}', mode='{self.mode}', status='{self.status}')>"


class SyncCallSpeechEgressTrack(Base):
    """LiveKit track composite egress для «речи в ленту» (один egress на микрофонный трек)."""

    __tablename__ = "sync_call_speech_egress_tracks"

    row_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    call_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("sync_calls.call_id", ondelete="CASCADE"), nullable=False, index=True
    )
    company_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    channel_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("sync_channels.channel_id", ondelete="CASCADE"), nullable=False
    )
    participant_identity: Mapped[str] = mapped_column(String(200), nullable=False)
    track_sid: Mapped[str] = mapped_column(String(128), nullable=False)
    egress_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    segments_posted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_segment_s3_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        UniqueConstraint("call_id", "track_sid", name="uq_sync_call_speech_track"),
    )

    def __repr__(self) -> str:
        return f"<SyncCallSpeechEgressTrack(call='{self.call_id}', egress='{self.egress_id}')>"


class SyncCallParticipant(Base):
    """Участник звонка.

    status: "invited" → "joined" / "declined" / "left".
    """

    __tablename__ = "sync_call_participants"

    call_participant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    call_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("sync_calls.call_id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="invited")
    joined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_sync_call_participants_call", "call_id"),
        Index("ix_sync_call_participants_user", "user_id"),
        UniqueConstraint("call_id", "user_id", name="uq_sync_call_participant"),
    )

    def __repr__(self) -> str:
        return f"<SyncCallParticipant(call_id='{self.call_id}', user_id='{self.user_id}', status='{self.status}')>"


class SyncCallLink(Base):
    """Гостевая ссылка-приглашение на звонок.

    Гость переходит по /sync/join/{link_token}, вводит имя и получает LiveKit токен.
    Звонок всегда создаётся в режиме SFU — P2P для гостей не поддерживается.
    """

    __tablename__ = "sync_call_links"

    link_token: Mapped[str] = mapped_column(String(64), primary_key=True)
    channel_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("sync_channels.channel_id", ondelete="CASCADE"), nullable=False
    )
    company_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    call_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("sync_calls.call_id", ondelete="SET NULL"), nullable=True
    )
    call_type: Mapped[str] = mapped_column(String(8), nullable=False, default="video")
    created_by_user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    scheduled_start_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    scheduled_end_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    calendar_event_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_persistent_channel_link: Mapped[bool] = mapped_column(
        Boolean(),
        nullable=False,
        default=False,
    )

    __table_args__ = (
        Index("ix_sync_call_links_channel", "channel_id"),
        Index("ix_sync_call_links_company", "company_id"),
        Index("ix_sync_call_links_expires", "expires_at"),
        Index("ix_sync_call_links_calendar_event_id", "calendar_event_id"),
    )

    def __repr__(self) -> str:
        return f"<SyncCallLink(token='{self.link_token}', channel='{self.channel_id}')>"


class SyncCallRecording(Base):
    """Серверная запись звонка."""

    __tablename__ = "sync_call_recordings"

    recording_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    call_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("sync_calls.call_id", ondelete="CASCADE"), nullable=False
    )
    company_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    channel_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("sync_channels.channel_id", ondelete="CASCADE"), nullable=False
    )
    namespace: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="requested")
    started_by_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    provider_job_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    raw_file_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("sync_files.file_id", ondelete="SET NULL"), nullable=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_sync_call_recordings_company", "company_id"),
        Index("ix_sync_call_recordings_call", "call_id"),
        Index("ix_sync_call_recordings_channel", "channel_id"),
        Index("ix_sync_call_recordings_status", "status"),
        Index("ix_sync_call_recordings_company_namespace", "company_id", "namespace"),
    )

    def __repr__(self) -> str:
        return f"<SyncCallRecording(recording_id='{self.recording_id}', call_id='{self.call_id}', status='{self.status}')>"
