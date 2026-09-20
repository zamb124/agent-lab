"""Запрет подключения datasource к platform PostgreSQL."""

from __future__ import annotations

from urllib.parse import urlparse

from core.config import get_settings
from core.config.models import DatabaseConfig

_BLOCKED_HOSTS = frozenset(
    {
        "postgres.platform.svc",
        "postgres.platform.svc.cluster.local",
        "postgres",
    }
)


def assert_datasource_host_allowed(host: str, port: int, database_name: str) -> None:
    resolved_host = host.strip().lower()
    if not resolved_host:
        raise ValueError("datasource host is required")
    if resolved_host in _BLOCKED_HOSTS:
        raise ValueError(f"datasource host {host!r} is a platform database")
    target = (resolved_host, port, database_name.strip())
    for field_name, url in _platform_postgres_urls(get_settings().database):
        parsed = _parse_postgres_target(url)
        if parsed is None:
            continue
        if parsed == target:
            raise ValueError(
                f"datasource {host}:{port}/{database_name} matches platform DSN {field_name}"
            )


def _platform_postgres_urls(database: DatabaseConfig) -> tuple[tuple[str, str], ...]:
    candidates: tuple[tuple[str, str | None], ...] = (
        ("checkpointer_url", database.checkpointer_url),
        ("shared_url", database.shared_url),
        ("flows_url", database.flows_url),
        ("crm_url", database.crm_url),
        ("sync_url", database.sync_url),
        ("rag_url", database.rag_url),
        ("office_url", database.office_url),
        ("worktracker_url", database.worktracker_url),
        ("secrets_url", database.secrets_url),
        ("tracing_url", database.tracing_url),
        ("search_url", database.search_url),
        ("wiki_url", database.wiki_url),
        ("realtime_url", database.realtime_url),
    )
    urls: list[tuple[str, str]] = []
    for field_name, url in candidates:
        if url is None or not url.strip():
            continue
        urls.append((field_name, url))
    return tuple(urls)


def _parse_postgres_target(url: str) -> tuple[str, int, str] | None:
    parsed = urlparse(url)
    if parsed.scheme not in {"postgres", "postgresql", "postgresql+asyncpg"}:
        return None
    hostname = parsed.hostname
    if hostname is None or not hostname.strip():
        return None
    port = parsed.port if parsed.port is not None else 5432
    database_name = parsed.path.lstrip("/")
    if not database_name:
        raise ValueError(f"platform DSN has empty database name: {url!r}")
    return (hostname.lower(), port, database_name)
