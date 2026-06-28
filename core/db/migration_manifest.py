"""
Манифест миграций: migrations/services.json — единственный список сервисных БД и модулей моделей.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable
from typing import ClassVar

from pydantic import ConfigDict, Field

from core.config import get_settings
from core.config.loader import get_project_root
from core.config.models import DatabaseConfig
from core.db.service_registry import register_service
from core.models import StrictBaseModel
from core.types import MigrationDatabaseUrlKey


class MigrationPostgresConfig(StrictBaseModel):
    """Контракт bootstrap PostgreSQL из migrations/services.json."""

    databases: list[str]
    vector_extensions: list[str] = Field(default_factory=list)


class MigrationServiceEntry(StrictBaseModel):
    """Контракт регистрации дерева Alembic из migrations/services.json."""

    model_config: ClassVar[ConfigDict] = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        str_strip_whitespace=True,
        validate_default=True,
    )

    name: str
    database_url_key: MigrationDatabaseUrlKey
    models_module: str
    optional: bool = False


class MigrationManifest(StrictBaseModel):
    """Строгий манифест миграций из migrations/services.json."""

    services: list[MigrationServiceEntry]
    postgres: MigrationPostgresConfig


def load_migration_manifest() -> MigrationManifest:
    path = get_project_root() / "migrations" / "services.json"
    return MigrationManifest.model_validate_json(path.read_text(encoding="utf-8"))


def get_migration_service_names() -> tuple[str, ...]:
    return tuple(entry.name for entry in load_migration_manifest().services)


def database_url_for_migration_key(
    database: DatabaseConfig,
    database_url_key: MigrationDatabaseUrlKey,
) -> str | None:
    match database_url_key:
        case "shared_url":
            return database.shared_url
        case "flows_url":
            return database.flows_url
        case "crm_url":
            return database.crm_url
        case "sync_url":
            return database.sync_url
        case "rag_url":
            return database.rag_url
        case "office_url":
            return database.office_url
        case "worktracker_url":
            return database.worktracker_url
        case "tracing_url":
            return database.tracing_url
        case "search_url":
            return database.search_url
        case "secrets_url":
            return database.secrets_url


def migration_entry_is_active(entry: MigrationServiceEntry) -> bool:
    """Сервис попадает в реестр миграций: обязательные всегда; optional — только если database.*_url задан."""
    if not entry.optional:
        return True
    url = database_url_for_migration_key(get_settings().database, entry.database_url_key)
    return bool(url and str(url).strip())


def expected_migration_registry_names() -> frozenset[str]:
    """Имена сервисов, которые должны быть зарегистрированы при текущем конфиге."""
    return frozenset(
        entry.name
        for entry in load_migration_manifest().services
        if migration_entry_is_active(entry)
    )


def _make_db_url_getter(database_url_key: MigrationDatabaseUrlKey) -> Callable[[], str]:
    def _get() -> str:
        settings = get_settings()
        url = database_url_for_migration_key(settings.database, database_url_key)
        if not url:
            raise ValueError(
                f"В настройках database.{database_url_key} не задан URL (миграции и conf.json)"
            )
        return url

    return _get


def register_migration_services() -> None:
    for entry in load_migration_manifest().services:
        if not migration_entry_is_active(entry):
            continue
        register_service(
            entry.name,
            _make_db_url_getter(entry.database_url_key),
            entry.models_module,
        )


def bootstrap_migration_registry() -> None:
    """Регистрирует сервисы по манифесту и импортирует модули моделей."""
    register_migration_services()
    for entry in load_migration_manifest().services:
        if not migration_entry_is_active(entry):
            continue
        _ = importlib.import_module(entry.models_module)
