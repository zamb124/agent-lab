"""
Модели shared-базы данных.

Таблицы platform БД: storage, users, variables, usage, namespaces, push_subscriptions.
"""

from datetime import datetime, timezone
from typing import TypeAlias, override

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from core.db.models.base import Base
from core.types import JsonObject, PushSubscriptionKeys

_TableArgs: TypeAlias = tuple[CheckConstraint | Index | UniqueConstraint, ...]


class Storage(Base):
    """
    Таблица для key-value хранения сущностей.

    Ключи имеют префиксы:
    - agent:flow_id
    - flow:flow_id
    - session:session_id
    - company:system:request:{uuid} — заявки с лендинга (frontend), значение JSON
    """

    __tablename__: str = "storage"

    key: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    value: Mapped[JsonObject] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    expired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__: _TableArgs = (
        UniqueConstraint("key", name="uq_storage_key"),
        Index("ix_storage_key_prefix", "key"),
        Index("ix_storage_updated_at", "updated_at"),
        Index("ix_storage_expired_at", "expired_at"),
        Index("ix_storage_key_created_at", "key", "created_at"),
        Index("ix_storage_key_updated_at", "key", "updated_at"),
        Index("ix_storage_key_expired_at", "key", "expired_at"),
    )

    @override
    def __repr__(self) -> str:
        return f"<Storage(key='{self.key}', updated_at='{self.updated_at}')>"


class Users(Base):
    """
    Таблица для хранения пользователей и аутентификации.

    Ключи имеют префиксы:
    - user:user_id (основная запись пользователя - source of truth)
    - user_providers:user_id (провайдеры)
    - auth_session:session_id (сессии)
    - auth_state:state (временные OAuth-состояния)
    """

    __tablename__: str = "users"

    key: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    value: Mapped[JsonObject] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    expired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__: _TableArgs = (
        UniqueConstraint("key", name="uq_users_key"),
        Index("ix_users_key_prefix", "key"),
        Index("ix_users_updated_at", "updated_at"),
        Index("ix_users_expired_at", "expired_at"),
        Index("ix_users_key_created_at", "key", "created_at"),
        Index("ix_users_key_updated_at", "key", "updated_at"),
        Index("ix_users_key_expired_at", "key", "expired_at"),
        Index(
            "ix_users_providers_jsonb",
            text("value jsonb_path_ops"),
            postgresql_using="gin",
            postgresql_where=text("key LIKE 'user_providers:%'"),
        ),
    )

    @override
    def __repr__(self) -> str:
        return f"<Users(key='{self.key}', updated_at='{self.updated_at}')>"


class Variables(Base):
    """
    Таблица для переменных всех компаний.

    Ключи имеют формат: company:{company_id}:var:{key}
    """

    __tablename__: str = "variables"

    key: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    value: Mapped[JsonObject] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    expired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__: _TableArgs = (
        UniqueConstraint("key", name="uq_variables_key"),
        Index("ix_variables_key_prefix", "key"),
        Index("ix_variables_updated_at", "updated_at"),
        Index("ix_variables_expired_at", "expired_at"),
    )

    @override
    def __repr__(self) -> str:
        return f"<Variables(key='{self.key}', updated_at='{self.updated_at}')>"


class Usage(Base):
    """
    Таблица для записей использования ресурсов (биллинг).

    Ключи имеют формат: company:{company_id}:usage:{resource_name}:{usage_id}
    """

    __tablename__: str = "usage"

    key: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    value: Mapped[JsonObject] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    expired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__: _TableArgs = (
        UniqueConstraint("key", name="uq_usage_key"),
        Index("ix_usage_key_prefix", "key"),
        Index("ix_usage_updated_at", "updated_at"),
        Index("ix_usage_expired_at", "expired_at"),
        Index("ix_usage_company_id", text("(value->>'company_id')")),
        Index("ix_usage_user_id", text("(value->>'user_id')")),
        Index("ix_usage_timestamp", text("(value->>'timestamp')")),
        Index("ix_usage_resource_name", text("(value->>'resource_name')")),
    )

    @override
    def __repr__(self) -> str:
        return f"<Usage(key='{self.key}', updated_at='{self.updated_at}')>"


class Namespaces(Base):
    """
    Таблица для namespace (изолированные области данных).

    Ключи имеют формат: namespace:{company_id}:{namespace_name}
    """

    __tablename__: str = "namespaces"

    key: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    value: Mapped[JsonObject] = mapped_column(JSONB, nullable=False)
    expired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__: _TableArgs = (
        UniqueConstraint("key", name="uq_namespaces_key"),
        Index("ix_namespaces_key_prefix", "key"),
        Index("ix_namespaces_company_id", text("(value->>'company_id')")),
    )

    @override
    def __repr__(self) -> str:
        return f"<Namespaces(key='{self.key}', updated_at='{self.updated_at}')>"


class CalendarEventRecord(Base):
    """Реляционная таблица событий платформенного календаря."""

    __tablename__: str = "calendar_events"

    event_id: Mapped[str] = mapped_column(String(255), primary_key=True, index=True)
    company_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_id: Mapped[str] = mapped_column(String(255), nullable=False)
    namespace: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(1024), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    location: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    all_day: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    attendees: Mapped[list[JsonObject]] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    recurrence_rule: Mapped[str | None] = mapped_column(Text, nullable=True)
    recurrence_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    series_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    deep_link: Mapped[str | None] = mapped_column(Text, nullable=True)
    external_refs: Mapped[list[JsonObject]] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    metadata_json: Mapped[JsonObject] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    created_by_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    updated_by_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__: _TableArgs = (
        UniqueConstraint("company_id", "source", "source_id", name="uq_calendar_events_company_source"),
        Index("ix_calendar_events_company_time", "company_id", "start_at", "end_at"),
        Index("ix_calendar_events_company_kind_time", "company_id", "kind", "start_at"),
        Index("ix_calendar_events_attendees_gin", "attendees", postgresql_using="gin"),
        Index("ix_calendar_events_external_refs_gin", "external_refs", postgresql_using="gin"),
        Index("ix_calendar_events_metadata_gin", "metadata", postgresql_using="gin"),
    )


class CalendarIntegrationRecord(Base):
    """Реляционная таблица интеграций календаря на уровне пользователя."""

    __tablename__: str = "calendar_integrations"

    integration_id: Mapped[str] = mapped_column(String(255), primary_key=True, index=True)
    company_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    credentials: Mapped[JsonObject] = mapped_column(JSONB, nullable=False)
    settings: Mapped[JsonObject] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__: _TableArgs = (
        UniqueConstraint("company_id", "user_id", "provider", name="uq_calendar_integrations_user_provider"),
        Index("ix_calendar_integrations_credentials_gin", "credentials", postgresql_using="gin"),
        Index("ix_calendar_integrations_settings_gin", "settings", postgresql_using="gin"),
    )


class IntegrationCredentialRecord(Base):
    """Per-user OAuth токены внешних интеграций (shared БД)."""

    __tablename__: str = "integration_credentials"

    credential_id: Mapped[str] = mapped_column(String(255), primary_key=True, index=True)
    company_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    service: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    access_token: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    scope: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    metadata_json: Mapped[JsonObject] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__: _TableArgs = (
        UniqueConstraint(
            "company_id", "user_id", "provider", "service",
            name="uq_integration_credentials_user_provider_service",
        ),
    )


class SchedulerTaskRecord(Base):
    """Служебная таблица задач платформенного scheduler (shared БД)."""

    __tablename__: str = "scheduler_tasks"

    schedule_task_id: Mapped[str] = mapped_column("id", String(255), primary_key=True, index=True)
    company_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    schedule_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    target_service: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    task_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    queue_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    schedule_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    cron: Mapped[str | None] = mapped_column(String(128), nullable=True)
    interval_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")
    payload: Mapped[JsonObject] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True, default="pending")
    created_by_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__: _TableArgs = (
        Index("ix_scheduler_tasks_company_status", "company_id", "status"),
        Index("ix_scheduler_tasks_company_service", "company_id", "target_service"),
        Index("ix_scheduler_tasks_company_task", "company_id", "task_name"),
        Index("ix_scheduler_tasks_company_next_run", "company_id", "next_run_at"),
    )


class PushSubscription(Base):
    """Подписка пользователя на push-уведомления."""

    __tablename__: str = "push_subscriptions"

    id: Mapped[str] = mapped_column(String(255), primary_key=True, index=True)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    endpoint: Mapped[str] = mapped_column(String(2048), nullable=False, unique=True)
    keys: Mapped[PushSubscriptionKeys] = mapped_column(JSONB, nullable=False)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    platform: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    last_used_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__: _TableArgs = (
        Index("ix_push_subscriptions_user_endpoint", "user_id", "endpoint"),
    )

    @override
    def __repr__(self) -> str:
        return f"<PushSubscription(user_id={self.user_id}, platform={self.platform})>"


class ApiKeyRecord(Base):
    """API-ключи компаний (shared БД)."""

    __tablename__: str = "api_keys"

    key_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    scopes: Mapped[list[str]] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    created_by: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    last_used: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__: _TableArgs = (
        Index("ix_api_keys_company_id", "company_id"),
        Index("ix_api_keys_key_hash", "key_hash", unique=True),
    )


class CompanyVoiceProvider(Base):
    """Per-company override провайдеров речи (STT/TTS/VAD).

    Перекрывает deployment-default из `settings.voice.<kind>` для конкретной
    компании. Per-call переопределение делается через
    `core.clients.speech_override.SpeechOverride`.

    Резолв (Zero-Guess, см. `core.clients.voice_resolver`):

    1. Поля из `SpeechOverride` (per-call/per-process).
    2. Поля из этой записи (per-company).
    3. `settings.voice.<kind>` (deployment-default).
    """

    __tablename__: str = "company_voice_providers"

    company_id: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    kind: Mapped[str] = mapped_column(String, primary_key=True)
    provider: Mapped[str] = mapped_column(String, nullable=False)
    model: Mapped[str | None] = mapped_column(String, nullable=True)
    voice: Mapped[str | None] = mapped_column(String, nullable=True)
    language: Mapped[str | None] = mapped_column(String, nullable=True)
    sample_rate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    response_format: Mapped[str | None] = mapped_column(String, nullable=True)
    secrets: Mapped[dict[str, str] | None] = mapped_column(JSONB, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__: _TableArgs = (
        CheckConstraint(
            "kind IN ('stt','tts','vad')",
            name="company_voice_providers_kind_check",
        ),
        CheckConstraint(
            "provider IN ('litserve','cloud_ru','yandex','sber','silero_local','mock')",
            name="company_voice_providers_provider_check",
        ),
    )


class PlatformShortLink(Base):
    """Короткий публичный код -> полезная нагрузка (вход по звонку Sync, JWT инвайта)."""

    __tablename__: str = "platform_short_links"

    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    kind: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    payload: Mapped[JsonObject] = mapped_column(JSONB, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    __table_args__: _TableArgs = (
        Index(
            "ix_platform_short_links_sync_link_token",
            text("(payload->>'link_token')"),
            postgresql_where=text("kind = 'sync_call_join'"),
        ),
    )


class PlatformPronunciationRule(Base):
    """Глобальные правила произношения TTS, управляемые суперадмином.

    Применяются ко всем компаниям (platform tier), перекрываются
    per-company правилами из ``CompanyPronunciationRule``.
    """

    __tablename__: str = "platform_pronunciation_rules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    pattern: Mapped[str] = mapped_column(Text, nullable=False)
    replacement: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str | None] = mapped_column(String(16), nullable=True)
    case_sensitive: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    word_boundary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    providers: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    voices: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__: _TableArgs = (
        CheckConstraint(
            "kind IN ('alias','regex','stress')",
            name="platform_pronunciation_rules_kind_check",
        ),
        Index("ix_platform_pronunciation_rules_enabled", "enabled"),
        Index("ix_platform_pronunciation_rules_language", "language"),
    )


class LLMModelScore(Base):
    """Платформенный скоринг LLM-модели для provider-neutral routing.

    Таблица живёт в shared БД и задаёт глобальный порядок выбора моделей.
    Конфиг используется только как initial seed; source of truth после старта
    сервиса — эта таблица.
    """

    __tablename__: str = "llm_model_scores"

    provider: Mapped[str] = mapped_column(String(64), primary_key=True)
    model_id: Mapped[str] = mapped_column(String(512), primary_key=True)
    capability: Mapped[str] = mapped_column(String(64), primary_key=True)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    score_dimensions: Mapped[JsonObject] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_by_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__: _TableArgs = (
        CheckConstraint("score >= 0 AND score <= 1000", name="llm_model_scores_score_range_check"),
        CheckConstraint(
            "source IN ('config_seed','manual','benchmark_import')",
            name="llm_model_scores_source_check",
        ),
        Index("ix_llm_model_scores_provider", "provider"),
        Index("ix_llm_model_scores_capability", "capability"),
        Index("ix_llm_model_scores_enabled_score", "enabled", "score"),
        Index("ix_llm_model_scores_updated_at", "updated_at"),
    )


class CompanyPronunciationRule(Base):
    """Per-company правила произношения TTS.

    Накладываются поверх платформенных (``PlatformPronunciationRule``):
    порядок применения — platform → company → per-call (SpeechOverride).
    """

    __tablename__: str = "company_pronunciation_rules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    pattern: Mapped[str] = mapped_column(Text, nullable=False)
    replacement: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str | None] = mapped_column(String(16), nullable=True)
    case_sensitive: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    word_boundary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    providers: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    voices: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__: _TableArgs = (
        CheckConstraint(
            "kind IN ('alias','regex','stress')",
            name="company_pronunciation_rules_kind_check",
        ),
        Index("ix_company_pronunciation_rules_company_id", "company_id"),
        Index("ix_company_pronunciation_rules_company_enabled", "company_id", "enabled"),
        UniqueConstraint("company_id", "id", name="uq_company_pronunciation_rules_company_id"),
    )
