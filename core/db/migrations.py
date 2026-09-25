"""Миграции Oxyde: диф зарегистрированных моделей против ``migrations/<db>/``.

Таблицы ищутся по ``Meta.is_table = True`` в ``core/`` и ``apps/``. База строки —
``__database_alias__`` или ``__database_aliases__``. Файл пишется, только если
диф не пустой и в каталоге ещё нет нумерованной миграции.
"""

from __future__ import annotations

import ast
import asyncio
import importlib
import json
from pathlib import Path

from _oxyde_core import migration_compute_diff
from asyncpg.exceptions import UndefinedTableError
from oxyde.migrations import (
    apply_migrations,
    extract_current_schema,
    generate_migration_file,
    replay_migrations,
)
from oxyde.models.registry import assert_no_pending_models, iter_tables

from core.config import get_settings
from core.config.loader import get_project_root
from core.db.migration_manifest import load_migration_manifest, register_migration_services
from core.db.oxyde_runtime import init_oxyde_databases
from core.db.postgres_service_databases import open_postgres_connection
from core.db.service_registry import ServiceDBConfig, get_all_services, get_service_by_name
from core.logging import get_logger
from core.models.platform_model import PlatformModel
from core.types import JsonObject, JsonValue, parse_json_object, parse_json_value

logger = get_logger(__name__)

_tables_loaded = False
_MIGRATION_LOCK_HELD = "Cannot acquire migration lock"
_MIGRATION_WAIT_ATTEMPTS = 90


def _declares_table(path: Path, source: str) -> bool:
    tree = ast.parse(source, filename=str(path))
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef) or node.name != "Meta":
            continue
        for statement in node.body:
            value: ast.expr | None = None
            if isinstance(statement, ast.Assign):
                if any(isinstance(target, ast.Name) and target.id == "is_table" for target in statement.targets):
                    value = statement.value
            elif isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name):
                if statement.target.id == "is_table":
                    value = statement.value
            if isinstance(value, ast.Constant) and value.value is True:
                return True
    return False


def _table_module_names() -> list[str]:
    root = get_project_root()
    names: list[str] = []
    for package in (root / "core", root / "apps"):
        for path in sorted(package.rglob("*.py")):
            if "__pycache__" in path.parts or "migrations" in path.parts:
                continue
            source = path.read_text(encoding="utf-8")
            if "is_table" not in source:
                continue
            if not _declares_table(path, source):
                continue
            relative = path.relative_to(root).with_suffix("")
            names.append(".".join(relative.parts))
    return names


def _load_tables() -> None:
    global _tables_loaded
    if _tables_loaded:
        return
    for module_name in _table_module_names():
        _ = importlib.import_module(module_name)
    assert_no_pending_models()
    _tables_loaded = True


def _model_aliases(model: type[PlatformModel]) -> tuple[str, ...]:
    aliases = model.__database_aliases__
    if aliases:
        return aliases
    alias = model.__database_alias__
    if alias is None:
        raise RuntimeError(f"{model.__name__} has no __database_alias__")
    return (alias,)


def _table_name(model: type[PlatformModel]) -> str:
    return model.table_name()


def _tables_for_alias(alias: str) -> set[str]:
    names: set[str] = set()
    for model in iter_tables():
        if not issubclass(model, PlatformModel):
            raise RuntimeError(f"{model.__name__} is not a PlatformModel")
        if alias not in _model_aliases(model):
            continue
        names.add(_table_name(model))
    if not names:
        raise RuntimeError(f"database {alias} has no tables")
    return names


def _assert_aliases_registered() -> None:
    registered = {service.name for service in get_all_services()}
    for model in iter_tables():
        if not issubclass(model, PlatformModel):
            raise RuntimeError(f"{model.__name__} is not a PlatformModel")
        for alias in _model_aliases(model):
            if alias not in registered:
                raise RuntimeError(f"{model.__name__} uses unknown database alias {alias}")


def _json_object_from_schema(schema: object, field_name: str) -> JsonObject:
    return parse_json_object(json.dumps(schema), field_name)


def _schema_json(table_names: set[str]) -> str:
    parsed = _json_object_from_schema(extract_current_schema(dialect="postgres"), "oxyde schema")
    tables = parsed.get("tables")
    if not isinstance(tables, dict):
        raise RuntimeError("oxyde schema tables is not an object")
    selected: dict[str, JsonValue] = {}
    for table_name in table_names:
        spec = tables.get(table_name)
        if not isinstance(spec, dict):
            raise RuntimeError(f"table {table_name} is missing from the oxyde schema")
        selected[table_name] = spec
    parsed["tables"] = selected
    return json.dumps(parsed)


def _replayed_schema_json(directory: Path) -> str:
    if not any(directory.glob("[0-9]*.py")):
        return json.dumps({"version": 1, "tables": {}})
    parsed = _json_object_from_schema(replay_migrations(str(directory)), "oxyde replay")
    return json.dumps(parsed)


def _diff_operations(old_schema: str, new_schema: str) -> list[JsonObject]:
    parsed = parse_json_value(migration_compute_diff(old_schema, new_schema), "oxyde diff")
    if not isinstance(parsed, list):
        raise RuntimeError("oxyde diff is not a list")
    operations: list[JsonObject] = []
    for item in parsed:
        if not isinstance(item, dict):
            raise RuntimeError("oxyde diff operation is not an object")
        operations.append(item)
    return operations


def _postgres_database_name(db_url: str) -> str:
    name = db_url.split("?", 1)[0].rsplit("/", 1)[-1]
    if name == "":
        raise RuntimeError("database name is missing in the connection URL")
    return name


def _prepend_vector_extension(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    needle = "def upgrade(ctx):\n    \"\"\"Apply migration.\"\"\"\n"
    replacement = (
        "def upgrade(ctx):\n"
        "    \"\"\"Apply migration.\"\"\"\n"
        "    ctx.execute(\"CREATE EXTENSION IF NOT EXISTS vector\")\n"
    )
    if needle not in text:
        raise RuntimeError(f"{path}: upgrade() header was not found")
    _ = path.write_text(text.replace(needle, replacement, 1), encoding="utf-8")


def generate_migration_files(service: str | None = None) -> None:
    """Пишет миграцию по дифу моделей и уже лежащих файлов ``migrations/<db>/``."""
    register_migration_services()
    _load_tables()
    _assert_aliases_registered()
    services = [get_service_by_name(service)] if service is not None else get_all_services()
    vector_databases = set(load_migration_manifest().postgres.vector_extensions)
    root = get_project_root()
    for svc in services:
        directory = root / svc.migrations_dir
        directory.mkdir(parents=True, exist_ok=True)
        operations = _diff_operations(
            _replayed_schema_json(directory),
            _schema_json(_tables_for_alias(svc.name)),
        )
        existing = sorted(directory.glob("[0-9]*.py"))
        if not operations:
            logger.info("oxyde_migration_unchanged", service=svc.name)
            continue
        if existing:
            raise RuntimeError(
                f"{svc.name}: schema differs from {existing[-1].name}. Delete that file and generate the migration again.",
            )
        path = generate_migration_file(operations, directory, "initial")
        if _postgres_database_name(svc.get_db_url()) in vector_databases:
            _prepend_vector_extension(path)
        logger.info("oxyde_migration_written", service=svc.name, path=str(path))


async def _initial_applied(db_url: str) -> bool:
    connection = await open_postgres_connection(db_url)
    try:
        try:
            marker = await connection.fetchval(
                "SELECT 1 FROM oxyde_migrations WHERE name = $1",
                "0001_initial",
            )
        except UndefinedTableError:
            return False
    finally:
        await connection.close()
    return marker is not None


async def _has_tables(db_url: str) -> bool:
    connection = await open_postgres_connection(db_url)
    try:
        count = await connection.fetchval(
            """
            SELECT COUNT(*)::int FROM information_schema.tables
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
            AND table_name <> 'oxyde_migrations'
            """,
        )
    finally:
        await connection.close()
    if isinstance(count, bool) or not isinstance(count, int):
        raise RuntimeError(f"table count is {count!r}")
    return count > 0


async def _apply_service(service: ServiceDBConfig, db_url: str, directory: str) -> None:
    """Накатывает каталог. Пока другой процесс держит lock или пишет ``0001``, ждёт."""
    for _attempt in range(_MIGRATION_WAIT_ATTEMPTS):
        if await _initial_applied(db_url):
            logger.info("oxyde_migrations_already_applied", service=service.name)
            return
        if await _has_tables(db_url):
            await asyncio.sleep(2)
            continue
        try:
            applied = await apply_migrations(directory, db_alias=service.name)
        except RuntimeError as exc:
            if _MIGRATION_LOCK_HELD not in str(exc):
                raise
            await asyncio.sleep(2)
            continue
        logger.info("oxyde_migrations_applied", service=service.name, applied=applied)
        return
    if await _initial_applied(db_url):
        logger.info("oxyde_migrations_already_applied", service=service.name)
        return
    if await _has_tables(db_url):
        raise RuntimeError(
            f"{service.name}: database already has tables and no oxyde migration 0001_initial. Drop the database and run upgrade again.",
        )
    raise RuntimeError(f"{service.name}: migration lock was not released")


async def run_migrations_async(service: str | None = None) -> None:
    """Применяет ``0001_initial`` к пустой базе. База со старыми таблицами — ошибка."""
    register_migration_services()
    settings = get_settings()
    shared_url = settings.database.shared_url
    if shared_url is None or shared_url == "":
        raise ValueError("database.shared_url is not set")
    await init_oxyde_databases(default_url=shared_url, shared_url=shared_url, all_aliases=True)
    services: list[ServiceDBConfig] = (
        [get_service_by_name(service)] if service is not None else get_all_services()
    )
    root = get_project_root()
    for svc in services:
        await _apply_service(svc, svc.get_db_url(), str(root / svc.migrations_dir))
