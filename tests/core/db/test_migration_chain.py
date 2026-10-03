"""Цепочка миграций: следующий файл, накат только неприменённых, отказ грязной базе, гейт номеров."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import pytest
import pytest_asyncio
from oxyde import PoolSettings
from oxyde.db.pool import AsyncDatabase

from core.config import get_settings
from core.db.migrations import apply_service_migrations, write_next_migration
from core.db.postgres_service_databases import open_postgres_connection
from core.db.service_registry import ServiceDBConfig
from core.types import JsonObject
from scripts.check_migration_files_canon import migration_chain_errors

_CREATE_TABLE: JsonObject = {
    "type": "create_table",
    "table": {
        "name": "probe",
        "fields": [{"name": "probe_id", "type": "varchar", "primary_key": True, "nullable": False}],
    },
}
_ADD_COLUMN: JsonObject = {
    "type": "add_column",
    "table": "probe",
    "field": {"name": "extra", "type": "varchar", "nullable": True},
}

_INITIAL = """\
depends_on = None


def upgrade(ctx):
    ctx.execute("CREATE TABLE chain_probe (probe_id text PRIMARY KEY, label text NOT NULL)")
    ctx.execute("INSERT INTO chain_probe (probe_id, label) VALUES ('seed', 'initial')")


def downgrade(ctx):
    ctx.execute("DROP TABLE chain_probe")
"""

_SECOND = """\
depends_on = "0001_initial"


def upgrade(ctx):
    ctx.execute("ALTER TABLE chain_probe ADD COLUMN extra text")
    ctx.execute("UPDATE chain_probe SET extra = 'second' WHERE probe_id = 'seed'")


def downgrade(ctx):
    ctx.execute("ALTER TABLE chain_probe DROP COLUMN extra")
"""


def _url_for_database(base_url: str, database: str) -> str:
    parsed = urlparse(base_url)
    return urlunparse(parsed._replace(path=f"/{database}"))


@dataclass(frozen=True)
class ChainDatabase:
    name: str
    url: str
    service: ServiceDBConfig
    pool: AsyncDatabase


@pytest_asyncio.fixture
async def chain_database(unique_id: str) -> AsyncIterator[ChainDatabase]:
    """Пустая база Postgres и пул Oxyde с отдельным алиасом. После теста база удаляется."""
    name = f"mig{unique_id}"
    if not name.isidentifier():
        raise RuntimeError(f"database name {name} is not an identifier")
    settings = get_settings()
    shared_url = settings.database.shared_url
    if shared_url is None or shared_url == "":
        raise RuntimeError("database.shared_url is not set")
    admin = await open_postgres_connection(shared_url)
    try:
        _ = await admin.execute(f"CREATE DATABASE {name}")
    finally:
        await admin.close()
    url = _url_for_database(shared_url, name)
    pool = AsyncDatabase(
        url,
        name=name,
        settings=PoolSettings(
            # Advisory lock держит одно соединение, SQL миграции — второе.
            max_connections=2,
            acquire_timeout=settings.database.pool_acquire_timeout_seconds,
        ),
        auto_register=True,
        overwrite=True,
    )
    await pool.connect()
    service = ServiceDBConfig(
        name=name,
        get_db_url=lambda: url,
        models_module="core.db.migrations",
        migrations_dir=f"migrations/{name}",
    )
    try:
        yield ChainDatabase(name=name, url=url, service=service, pool=pool)
    finally:
        await pool.disconnect()
        admin = await open_postgres_connection(shared_url)
        try:
            _ = await admin.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = $1 AND pid <> pg_backend_pid()",
                name,
            )
            _ = await admin.execute(f"DROP DATABASE {name}")
        finally:
            await admin.close()


def test_write_next_migration_appends_file_and_keeps_initial(tmp_path: Path) -> None:
    """Второй вызов дописывает 0002 и не меняет байты 0001. vector — только в 0001."""
    directory = tmp_path / "svc"
    directory.mkdir()

    first = write_next_migration([_CREATE_TABLE], directory, vector_database=True)
    initial_bytes = first.read_bytes()

    second = write_next_migration([_ADD_COLUMN], directory, vector_database=True)

    assert first.name == "0001_initial.py"
    assert second.name == "0002_add_extra_to_probe.py"
    assert first.read_bytes() == initial_bytes
    assert 'ctx.execute("CREATE EXTENSION IF NOT EXISTS vector")' in first.read_text(encoding="utf-8")
    assert "vector" not in second.read_text(encoding="utf-8")
    assert sorted(path.name for path in directory.glob("[0-9]*.py")) == [
        "0001_initial.py",
        "0002_add_extra_to_probe.py",
    ]


def test_migration_chain_errors_reject_gaps_and_foreign_files(tmp_path: Path) -> None:
    """Гейт принимает сплошную цепочку и отвергает дыру, чужой файл и каталог без 0001."""
    root = tmp_path
    valid = root / "valid"
    valid.mkdir()
    _ = (valid / "0001_initial.py").write_text("", encoding="utf-8")
    _ = (valid / "0002_add_extra.py").write_text("", encoding="utf-8")
    broken = root / "broken"
    broken.mkdir()
    _ = (broken / "0001_initial.py").write_text("", encoding="utf-8")
    _ = (broken / "0003_skipped.py").write_text("", encoding="utf-8")
    _ = (broken / "notes.txt").write_text("", encoding="utf-8")
    empty = root / "empty"
    empty.mkdir()

    assert migration_chain_errors(valid, root=root) == []
    assert migration_chain_errors(broken, root=root) == [
        "broken/notes.txt: migration file must be NNNN_<name>.py",
        "broken: migration numbers must be 0001..0002 without gaps",
    ]
    assert migration_chain_errors(empty, root=root) == ["empty/0001_initial.py: missing"]


@pytest.mark.asyncio
async def test_upgrade_applies_only_pending_files(chain_database: ChainDatabase, tmp_path: Path) -> None:
    """0001 пишет одну строку. 0002 добавляет колонку. Повтор не дублирует строку и не теряет 0001."""
    directory = tmp_path / "migrations"
    directory.mkdir()
    _ = (directory / "0001_initial.py").write_text(_INITIAL, encoding="utf-8")

    await apply_service_migrations(chain_database.service, chain_database.url, str(directory))
    _ = (directory / "0002_add_extra.py").write_text(_SECOND, encoding="utf-8")
    await apply_service_migrations(chain_database.service, chain_database.url, str(directory))
    await apply_service_migrations(chain_database.service, chain_database.url, str(directory))

    connection = await open_postgres_connection(chain_database.url)
    try:
        rows = await connection.fetch("SELECT probe_id, label, extra FROM chain_probe ORDER BY probe_id")
        applied = await connection.fetch("SELECT name FROM oxyde_migrations ORDER BY name")
    finally:
        await connection.close()

    assert [(row["probe_id"], row["label"], row["extra"]) for row in rows] == [("seed", "initial", "second")]
    assert [row["name"] for row in applied] == ["0001_initial", "0002_add_extra"]


@pytest.mark.asyncio
async def test_upgrade_rejects_database_with_tables_and_without_initial(
    chain_database: ChainDatabase,
    tmp_path: Path,
) -> None:
    """Таблицы без записи 0001_initial не накатываются, чужая таблица остаётся."""
    connection = await open_postgres_connection(chain_database.url)
    try:
        _ = await connection.execute("CREATE TABLE leftover (leftover_id text PRIMARY KEY)")
    finally:
        await connection.close()
    directory = tmp_path / "migrations"
    directory.mkdir()
    _ = (directory / "0001_initial.py").write_text(_INITIAL, encoding="utf-8")

    with pytest.raises(RuntimeError, match="no oxyde migration 0001_initial"):
        await apply_service_migrations(
            chain_database.service,
            chain_database.url,
            str(directory),
            wait_attempts=1,
        )

    connection = await open_postgres_connection(chain_database.url)
    try:
        leftover = await connection.fetchval(
            "SELECT to_regclass('public.leftover')::text",
        )
        probe = await connection.fetchval("SELECT to_regclass('public.chain_probe')::text")
    finally:
        await connection.close()
    assert leftover == "leftover"
    assert probe is None
