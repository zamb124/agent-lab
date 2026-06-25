"""Crawl official MCP registry и upsert глобального catalog."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, TypedDict, cast
from urllib.parse import quote, urljoin

import httpx
import yaml
from pydantic import ValidationError

from apps.flows.config import get_settings
from apps.flows.src.clients.mcp_client import MCPClient, MCPClientError
from apps.flows.src.container_contracts import FlowRuntimeContainer
from apps.flows.src.models.mcp import MCPServerConfig, MCPTransportType
from apps.flows.src.models.mcp_catalog import (
    MCPAuthPolicy,
    MCPCatalogAllowlistItemPayload,
    MCPCatalogEntry,
    MCPCatalogHostClass,
    MCPCatalogVerifyStatus,
    compute_catalog_snapshot_hash,
)
from apps.flows.src.services.mcp_catalog_ids import catalog_id_from_registry_name
from core.http import get_httpx_client
from core.logging import get_logger

logger = get_logger(__name__)


class RegistryRemote(TypedDict):
    type: str
    url: str


class RegistryServerPayload(TypedDict, total=False):
    name: str
    title: str
    description: str
    version: str
    remotes: list[RegistryRemote]


class RegistryListItem(TypedDict, total=False):
    server: RegistryServerPayload
    _meta: dict[str, object]


class RegistryListResponse(TypedDict, total=False):
    servers: list[RegistryListItem]
    metadata: dict[str, object]


@dataclass(frozen=True)
class MCPCatalogAllowlistEntry:
    catalog_id: str
    platform_approved: bool
    auth_template: dict[str, str]
    required_variables: list[str]
    auth_policy: MCPAuthPolicy
    registry_name: str | None = None
    upstream_url: str | None = None
    transport_type: str = "http"
    title: str | None = None
    description: str | None = None


@dataclass(frozen=True)
class MCPCatalogCrawlStats:
    fetched: int
    upserted: int
    deprecated: int
    verified: int
    verify_failed: int


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def load_mcp_catalog_allowlist() -> dict[str, MCPCatalogAllowlistEntry]:
    settings = get_settings()
    allowlist_path = _repo_root() / settings.mcp_catalog.allowlist_path
    if not allowlist_path.is_file():
        return {}
    raw_text = allowlist_path.read_text(encoding="utf-8")
    raw_payload: object = cast(object, yaml.safe_load(raw_text))
    if raw_payload is None:
        return {}
    if not isinstance(raw_payload, list):
        raise ValueError(f"MCP allowlist must be a yaml list: {allowlist_path}")
    result: dict[str, MCPCatalogAllowlistEntry] = {}
    for raw_item in cast(list[object], raw_payload):
        item = MCPCatalogAllowlistItemPayload.model_validate(raw_item)
        result[item.catalog_id] = MCPCatalogAllowlistEntry(
            catalog_id=item.catalog_id,
            platform_approved=item.platform_approved,
            auth_template=item.auth_template,
            required_variables=item.required_variables,
            auth_policy=item.auth_policy,
            registry_name=item.registry_name,
            upstream_url=item.upstream_url,
            transport_type=item.transport_type,
            title=item.title,
            description=item.description,
        )
    return result


def _parse_registry_remote(raw: object) -> RegistryRemote | None:
    if not isinstance(raw, dict):
        return None
    raw_mapping = cast(dict[object, object], raw)
    remote_type = raw_mapping.get("type")
    remote_url = raw_mapping.get("url")
    if not isinstance(remote_type, str) or not isinstance(remote_url, str):
        return None
    return {"type": remote_type, "url": remote_url}


def _registry_list_items_from_page(page: RegistryListResponse) -> list[RegistryListItem]:
    servers_raw: object = cast(dict[object, object], cast(object, page)).get("servers")
    if servers_raw is None:
        return []
    if not isinstance(servers_raw, list):
        raise ValueError("registry servers must be list")
    items: list[RegistryListItem] = []
    for raw_item in cast(list[object], servers_raw):
        if not isinstance(raw_item, dict):
            continue
        items.append(cast(RegistryListItem, cast(object, raw_item)))
    return items


def _registry_server_payload(raw: object) -> RegistryServerPayload | None:
    if not isinstance(raw, dict):
        return None
    return cast(RegistryServerPayload, cast(object, raw))


def _is_latest_registry_item(item: RegistryListItem) -> bool:
    meta_raw: object = item.get("_meta")
    if not isinstance(meta_raw, dict):
        return True
    meta = cast(dict[object, object], meta_raw)
    official_raw: object = meta.get("io.modelcontextprotocol.registry/official")
    if not isinstance(official_raw, dict):
        return True
    official = cast(dict[object, object], official_raw)
    is_latest_raw: object = official.get("isLatest")
    if is_latest_raw is None:
        return True
    if not isinstance(is_latest_raw, bool):
        raise ValueError("registry isLatest must be bool")
    return is_latest_raw


def _pick_https_remote(remotes: list[RegistryRemote]) -> RegistryRemote | None:
    for remote in remotes:
        remote_type = remote.get("type", "").lower()
        remote_url = remote.get("url", "")
        if remote_type not in ("streamable-http", "sse", "http"):
            continue
        if not remote_url.startswith("https://"):
            continue
        return remote
    return None


def _host_class_from_url(url: str) -> MCPCatalogHostClass:
    if "server.smithery.ai" in url:
        return MCPCatalogHostClass.SMITHERY_PROXY
    return MCPCatalogHostClass.DIRECT


def upstream_url_is_probeable(url: str) -> bool:
    """Registry иногда отдаёт шаблонные remotes вроде https://host:{HAPI_PORT}/mcp."""
    if "{" in url or "}" in url:
        return False
    try:
        _ = httpx.URL(url)
    except ValueError:
        return False
    return True


def _transport_type_from_remote(remote_type: str) -> MCPTransportType:
    if remote_type.lower() == "sse":
        return MCPTransportType.SSE
    return MCPTransportType.HTTP


async def _fetch_registry_page(
    *,
    base_url: str,
    cursor: str | None,
    page_limit: int,
) -> RegistryListResponse:
    path = f"/v0/servers?limit={page_limit}"
    if cursor is not None:
        path = f"{path}&cursor={quote(cursor, safe='')}"
    url = urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
    async with get_httpx_client(timeout=60.0) as client:
        response = await client.get(url, headers={"Accept": "application/json"})
        _ = response.raise_for_status()
    raw_json: object = cast(object, response.json())
    if not isinstance(raw_json, dict):
        raise ValueError("registry response must be object")
    return cast(RegistryListResponse, cast(object, raw_json))


async def _verify_catalog_entry(
    *,
    upstream_url: str,
    transport_type: MCPTransportType,
    timeout_seconds: float,
) -> tuple[MCPCatalogVerifyStatus, MCPAuthPolicy, int]:
    if not upstream_url_is_probeable(upstream_url):
        return MCPCatalogVerifyStatus.UNREACHABLE, MCPAuthPolicy.UNKNOWN, 0
    probe = MCPServerConfig(
        server_id="catalog_verify_probe",
        name="Catalog Verify Probe",
        url=upstream_url,
        transport_type=transport_type,
        headers={},
        is_active=True,
    )
    client = MCPClient(probe, timeout=timeout_seconds)
    try:
        _ = await client.initialize()
        tools = await client.list_tools()
    except MCPClientError as exc:
        message = str(exc).lower()
        if "401" in message or "403" in message or "unauthorized" in message:
            return MCPCatalogVerifyStatus.AUTH_REQUIRED, MCPAuthPolicy.API_KEY, 0
        return MCPCatalogVerifyStatus.UNREACHABLE, MCPAuthPolicy.UNKNOWN, 0
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in (401, 403):
            return MCPCatalogVerifyStatus.AUTH_REQUIRED, MCPAuthPolicy.API_KEY, 0
        return MCPCatalogVerifyStatus.UNREACHABLE, MCPAuthPolicy.UNKNOWN, 0
    except httpx.HTTPError:
        return MCPCatalogVerifyStatus.UNREACHABLE, MCPAuthPolicy.UNKNOWN, 0
    except ValidationError:
        return MCPCatalogVerifyStatus.UNREACHABLE, MCPAuthPolicy.UNKNOWN, 0
    except ValueError:
        return MCPCatalogVerifyStatus.UNREACHABLE, MCPAuthPolicy.UNKNOWN, 0
    return MCPCatalogVerifyStatus.VERIFIED, MCPAuthPolicy.NONE, len(tools)


async def _upsert_allowlist_seed_entries(
    *,
    container: FlowRuntimeContainer,
    allowlist: dict[str, MCPCatalogAllowlistEntry],
    crawled_at: datetime,
    seen_catalog_ids: set[str],
    verify_budget: int,
    verify_timeout_seconds: float,
) -> tuple[int, int, int, int]:
    """Curated allowlist seeds с upstream_url — MCP вне official registry."""
    upserted = 0
    verified = 0
    verify_failed = 0
    budget = verify_budget
    for allow in allowlist.values():
        if allow.upstream_url is None:
            continue
        if allow.registry_name is None:
            raise ValueError(f"MCP allowlist seed {allow.catalog_id}: registry_name is required")
        title = allow.title if allow.title is not None else allow.catalog_id
        if allow.transport_type == "sse":
            transport_type: Literal["http", "sse"] = "sse"
        elif allow.transport_type == "http":
            transport_type = "http"
        else:
            raise ValueError(f"MCP allowlist seed {allow.catalog_id}: invalid transport_type")
        verify_status = MCPCatalogVerifyStatus.PENDING
        entry = MCPCatalogEntry(
            catalog_id=allow.catalog_id,
            registry_name=allow.registry_name,
            title=title,
            description=allow.description,
            version=None,
            upstream_url=allow.upstream_url,
            transport_type=transport_type,
            host_class=_host_class_from_url(allow.upstream_url),
            auth_policy=allow.auth_policy,
            auth_template=dict(allow.auth_template),
            required_variables=list(allow.required_variables),
            verify_status=verify_status,
            tool_count_snapshot=0,
            catalog_snapshot_hash=compute_catalog_snapshot_hash(
                title=title,
                description=allow.description,
                upstream_url=allow.upstream_url,
                transport_type=allow.transport_type,
                auth_template=dict(allow.auth_template),
                is_deprecated=False,
                verify_status=verify_status,
            ),
            platform_approved=allow.platform_approved,
            is_deprecated=False,
            last_crawled_at=crawled_at,
            last_verified_at=None,
        )
        seen_catalog_ids.add(entry.catalog_id)
        existing = await container.mcp_catalog_repository.get(entry.catalog_id)
        if existing is not None:
            entry.verify_status = existing.verify_status
            entry.tool_count_snapshot = existing.tool_count_snapshot
            entry.last_verified_at = existing.last_verified_at
            if (
                existing.upstream_url != entry.upstream_url
                or existing.transport_type != entry.transport_type
            ):
                entry.verify_status = MCPCatalogVerifyStatus.PENDING
                entry.tool_count_snapshot = 0
                entry.last_verified_at = None
        should_verify = budget > 0 and entry.verify_status == MCPCatalogVerifyStatus.PENDING
        if should_verify:
            verify_status, auth_policy, tool_count = await _verify_catalog_entry(
                upstream_url=entry.upstream_url,
                transport_type=MCPTransportType(entry.transport_type),
                timeout_seconds=verify_timeout_seconds,
            )
            entry.verify_status = verify_status
            entry.auth_policy = auth_policy
            entry.tool_count_snapshot = tool_count
            entry.last_verified_at = crawled_at
            budget -= 1
            if verify_status == MCPCatalogVerifyStatus.UNREACHABLE:
                verify_failed += 1
            else:
                verified += 1
        entry.catalog_snapshot_hash = entry.recompute_snapshot_hash()
        _ = await container.mcp_catalog_repository.set(entry)
        upserted += 1
    return upserted, verified, verify_failed, budget


def _entry_from_registry(
    *,
    server_payload: RegistryServerPayload,
    allowlist: dict[str, MCPCatalogAllowlistEntry],
    crawled_at: datetime,
) -> MCPCatalogEntry | None:
    registry_name = server_payload.get("name")
    if not isinstance(registry_name, str) or not registry_name.strip():
        return None
    remotes_raw = server_payload.get("remotes")
    if not isinstance(remotes_raw, list):
        return None
    remotes: list[RegistryRemote] = []
    for remote_raw in remotes_raw:
        remote = _parse_registry_remote(remote_raw)
        if remote is not None:
            remotes.append(remote)
    picked = _pick_https_remote(remotes)
    if picked is None:
        return None
    catalog_id = catalog_id_from_registry_name(registry_name)
    title_raw = server_payload.get("title")
    title = title_raw if isinstance(title_raw, str) and title_raw.strip() else registry_name
    description_raw = server_payload.get("description")
    description = description_raw if isinstance(description_raw, str) else None
    version_raw = server_payload.get("version")
    version = version_raw if isinstance(version_raw, str) else None
    upstream_url = picked["url"]
    transport_type = _transport_type_from_remote(picked["type"]).value
    allow = allowlist.get(catalog_id)
    auth_template = allow.auth_template if allow is not None else {}
    required_variables = allow.required_variables if allow is not None else []
    auth_policy = allow.auth_policy if allow is not None else MCPAuthPolicy.UNKNOWN
    platform_approved = allow.platform_approved if allow is not None else False
    verify_status = MCPCatalogVerifyStatus.PENDING
    snapshot_hash = compute_catalog_snapshot_hash(
        title=title,
        description=description,
        upstream_url=upstream_url,
        transport_type=transport_type,
        auth_template=auth_template,
        is_deprecated=False,
        verify_status=verify_status,
    )
    return MCPCatalogEntry(
        catalog_id=catalog_id,
        registry_name=registry_name,
        title=title,
        description=description,
        version=version,
        upstream_url=upstream_url,
        transport_type=transport_type,
        host_class=_host_class_from_url(upstream_url),
        auth_policy=auth_policy,
        auth_template=auth_template,
        required_variables=required_variables,
        verify_status=verify_status,
        tool_count_snapshot=0,
        catalog_snapshot_hash=snapshot_hash,
        platform_approved=platform_approved,
        is_deprecated=False,
        last_crawled_at=crawled_at,
        last_verified_at=None,
    )


@dataclass(frozen=True)
class MCPCatalogSeedStats:
    upserted: int
    verified: int
    verify_failed: int


async def upsert_allowlist_seed_entries_only(
    *,
    container: FlowRuntimeContainer,
    allowlist: dict[str, MCPCatalogAllowlistEntry] | None = None,
) -> MCPCatalogSeedStats:
    """Только curated seeds из allowlist yaml (без paginate registry)."""
    settings = get_settings()
    catalog_cfg = settings.mcp_catalog
    resolved_allowlist = allowlist if allowlist is not None else load_mcp_catalog_allowlist()
    crawled_at = datetime.now(tz=timezone.utc)
    seen_catalog_ids: set[str] = set()
    upserted, verified, verify_failed, _budget = await _upsert_allowlist_seed_entries(
        container=container,
        allowlist=resolved_allowlist,
        crawled_at=crawled_at,
        seen_catalog_ids=seen_catalog_ids,
        verify_budget=catalog_cfg.max_verify_per_crawl,
        verify_timeout_seconds=catalog_cfg.verify_timeout_seconds,
    )
    return MCPCatalogSeedStats(
        upserted=upserted,
        verified=verified,
        verify_failed=verify_failed,
    )


async def crawl_mcp_registry(*, container: FlowRuntimeContainer) -> MCPCatalogCrawlStats:
    settings = get_settings()
    catalog_cfg = settings.mcp_catalog
    if not catalog_cfg.enabled:
        return MCPCatalogCrawlStats(
            fetched=0, upserted=0, deprecated=0, verified=0, verify_failed=0
        )

    allowlist = load_mcp_catalog_allowlist()
    crawled_at = datetime.now(tz=timezone.utc)
    seen_catalog_ids: set[str] = set()
    fetched = 0
    upserted = 0
    verified = 0
    verify_failed = 0
    verify_budget = catalog_cfg.max_verify_per_crawl
    cursor: str | None = None

    while True:
        page = await _fetch_registry_page(
            base_url=catalog_cfg.registry_base_url,
            cursor=cursor,
            page_limit=catalog_cfg.crawl_page_limit,
        )
        for item in _registry_list_items_from_page(page):
            if not _is_latest_registry_item(item):
                continue
            server_payload = _registry_server_payload(item.get("server"))
            if server_payload is None:
                continue
            entry = _entry_from_registry(
                server_payload=server_payload,
                allowlist=allowlist,
                crawled_at=crawled_at,
            )
            if entry is None:
                continue
            fetched += 1
            seen_catalog_ids.add(entry.catalog_id)
            existing = await container.mcp_catalog_repository.get(entry.catalog_id)
            if existing is not None:
                entry.verify_status = existing.verify_status
                entry.tool_count_snapshot = existing.tool_count_snapshot
                entry.last_verified_at = existing.last_verified_at
                if (
                    existing.upstream_url != entry.upstream_url
                    or existing.transport_type != entry.transport_type
                ):
                    entry.verify_status = MCPCatalogVerifyStatus.PENDING
                    entry.tool_count_snapshot = 0
                    entry.last_verified_at = None
            should_verify = (
                verify_budget > 0
                and entry.verify_status == MCPCatalogVerifyStatus.PENDING
            )
            if should_verify:
                verify_status, auth_policy, tool_count = await _verify_catalog_entry(
                    upstream_url=entry.upstream_url,
                    transport_type=MCPTransportType(entry.transport_type),
                    timeout_seconds=catalog_cfg.verify_timeout_seconds,
                )
                entry.verify_status = verify_status
                entry.auth_policy = auth_policy
                entry.tool_count_snapshot = tool_count
                entry.last_verified_at = crawled_at
                verify_budget -= 1
                if verify_status == MCPCatalogVerifyStatus.UNREACHABLE:
                    verify_failed += 1
                else:
                    verified += 1
            entry.catalog_snapshot_hash = entry.recompute_snapshot_hash()
            _ = await container.mcp_catalog_repository.set(entry)
            upserted += 1

        metadata = page.get("metadata")
        next_cursor: str | None = None
        if isinstance(metadata, dict):
            cursor_raw = metadata.get("nextCursor")
            if isinstance(cursor_raw, str) and cursor_raw.strip():
                next_cursor = cursor_raw.strip()
        if next_cursor is None:
            break
        cursor = next_cursor

    seed_upserted, seed_verified, seed_verify_failed, verify_budget = await _upsert_allowlist_seed_entries(
        container=container,
        allowlist=allowlist,
        crawled_at=crawled_at,
        seen_catalog_ids=seen_catalog_ids,
        verify_budget=verify_budget,
        verify_timeout_seconds=catalog_cfg.verify_timeout_seconds,
    )
    upserted += seed_upserted
    verified += seed_verified
    verify_failed += seed_verify_failed

    deprecated = 0
    existing_entries = await container.mcp_catalog_repository.list(limit=20_000)
    for existing in existing_entries:
        if existing.catalog_id in seen_catalog_ids:
            continue
        if existing.is_deprecated:
            continue
        deprecated_entry = existing.model_copy(
            update={
                "is_deprecated": True,
                "last_crawled_at": crawled_at,
            }
        )
        deprecated_entry.catalog_snapshot_hash = deprecated_entry.recompute_snapshot_hash()
        _ = await container.mcp_catalog_repository.set(deprecated_entry)
        deprecated += 1

    logger.info(
        "MCP catalog crawl done: fetched=%s upserted=%s deprecated=%s verified=%s verify_failed=%s",
        fetched,
        upserted,
        deprecated,
        verified,
        verify_failed,
    )
    return MCPCatalogCrawlStats(
        fetched=fetched,
        upserted=upserted,
        deprecated=deprecated,
        verified=verified,
        verify_failed=verify_failed,
    )


async def upsert_catalog_entry_for_tests(
    *,
    container: FlowRuntimeContainer,
    entry: MCPCatalogEntry,
) -> MCPCatalogEntry:
    """Тестовый helper: upsert catalog entry без registry crawl."""
    stored = entry.model_copy(
        update={"catalog_snapshot_hash": entry.recompute_snapshot_hash()}
    )
    _ = await container.mcp_catalog_repository.set(stored)
    return stored
