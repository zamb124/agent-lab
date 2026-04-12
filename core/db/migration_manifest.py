"""
Манифест миграций: migrations/services.json — единственный список сервисных БД и модулей моделей.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path

from core.config.loader import get_project_root


def load_migration_manifest() -> dict:
    path = get_project_root() / "migrations" / "services.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def get_migration_service_names() -> tuple[str, ...]:
    return tuple(entry["name"] for entry in load_migration_manifest()["services"])


def migration_entry_is_active(entry: dict) -> bool:
    """Сервис попадает в реестр миграций: обязательные всегда; optional — только если database.*_url задан."""
    if not entry.get("optional"):
        return True
    from core.config import get_settings

    url = getattr(get_settings().database, entry["database_url_key"])
    return bool(url and str(url).strip())


def expected_migration_registry_names() -> frozenset[str]:
    """Имена сервисов, которые должны быть зарегистрированы при текущем конфиге."""
    return frozenset(
        e["name"] for e in load_migration_manifest()["services"] if migration_entry_is_active(e)
    )


def _make_db_url_getter(database_url_key: str):
    def _get() -> str:
        from core.config import get_settings

        settings = get_settings()
        url = getattr(settings.database, database_url_key)
        if not url:
            raise ValueError(
                f"В настройках database.{database_url_key} не задан URL (миграции и conf.json)"
            )
        return url

    return _get


def register_migration_services() -> None:
    from core.db.service_registry import register_service

    for entry in load_migration_manifest()["services"]:
        if not migration_entry_is_active(entry):
            continue
        register_service(
            entry["name"],
            _make_db_url_getter(entry["database_url_key"]),
            entry["models_module"],
        )


def bootstrap_migration_registry() -> None:
    """Регистрирует сервисы по манифесту и импортирует модули моделей."""
    register_migration_services()
    for entry in load_migration_manifest()["services"]:
        if not migration_entry_is_active(entry):
            continue
        importlib.import_module(entry["models_module"])
