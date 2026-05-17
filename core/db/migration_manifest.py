"""
Манифест миграций: migrations/services.json — единственный список сервисных БД и модулей моделей.
"""

from __future__ import annotations

import importlib
import json
from typing import TypedDict

from core.config import get_settings
from core.config.loader import get_project_root
from core.db.service_registry import register_service


class MigrationServiceEntry(TypedDict):
    name: str
    database_url_key: str
    models_module: str
    optional: bool


class MigrationManifest(TypedDict):
    services: list[MigrationServiceEntry]


def load_migration_manifest() -> MigrationManifest:
    path = get_project_root() / "migrations" / "services.json"
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    if not isinstance(raw, dict) or not isinstance(raw.get("services"), list):
        raise ValueError("migrations/services.json must contain object with services array")
    services: list[MigrationServiceEntry] = []
    for index, entry in enumerate(raw["services"]):
        if not isinstance(entry, dict):
            raise ValueError(f"migrations/services.json services[{index}] must be object")
        name = entry.get("name")
        database_url_key = entry.get("database_url_key")
        models_module = entry.get("models_module")
        if not isinstance(name, str) or not isinstance(database_url_key, str) or not isinstance(models_module, str):
            raise ValueError(
                f"migrations/services.json services[{index}] requires name/database_url_key/models_module strings"
            )
        services.append({
            "name": name,
            "database_url_key": database_url_key,
            "models_module": models_module,
            "optional": bool(entry.get("optional", False)),
        })
    return {"services": services}


def get_migration_service_names() -> tuple[str, ...]:
    return tuple(entry["name"] for entry in load_migration_manifest()["services"])


def migration_entry_is_active(entry: MigrationServiceEntry) -> bool:
    """Сервис попадает в реестр миграций: обязательные всегда; optional — только если database.*_url задан."""
    if not entry.get("optional"):
        return True
    url = getattr(get_settings().database, entry["database_url_key"])
    return bool(url and str(url).strip())


def expected_migration_registry_names() -> frozenset[str]:
    """Имена сервисов, которые должны быть зарегистрированы при текущем конфиге."""
    return frozenset(
        e["name"] for e in load_migration_manifest()["services"] if migration_entry_is_active(e)
    )


def _make_db_url_getter(database_url_key: str):
    def _get() -> str:
        settings = get_settings()
        url = getattr(settings.database, database_url_key)
        if not url:
            raise ValueError(
                f"В настройках database.{database_url_key} не задан URL (миграции и conf.json)"
            )
        return url

    return _get


def register_migration_services() -> None:
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
