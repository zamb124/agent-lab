"""
Бизнес-логика HumanitecAgent: pairing, devices, releases.
"""

import json
import secrets
import uuid
from datetime import datetime, timezone
from urllib.parse import urlparse, urlunparse

import httpx

from apps.agent.authz.tuples import agent_device_company_link, agent_device_owner_tuple
from apps.agent.desktop.build_contract import (
    load_default_distro_config,
    matches_release_asset_name,
)
from apps.agent.local_releases import (
    build_local_release_status,
    build_local_release_unavailable_status,
    detect_host_platform,
    local_release_artifact_route,
    resolve_local_release_artifact_path,
    use_local_release_artifact,
)
from apps.agent.models import (
    AgentAuditEvent,
    AgentAuditListResponse,
    AgentDeviceListItem,
    AgentDeviceRecord,
    AgentDiscoverResponse,
    AgentLlmBundle,
    AgentReleaseAssetChecksum,
    AgentReleaseStatusResponse,
    DevicePolicy,
    DeviceRegisterRequest,
    DeviceRegisterResponse,
    DeviceRegisterWithAuthRequest,
    PairingCodeResponse,
)
from apps.agent.tunnel_bus import publish_tunnel_disconnect
from apps.agent.tunnel_registry import push_device_policy_to_tunnel
from core.authz.errors import AuthzDenied
from core.authz.models import AuthzObject, AuthzSubject
from core.authz.types import AuthzObjectType, AuthzRelation
from core.clients.redis_client import RedisClient
from core.config import get_settings
from core.container.base import BaseContainer
from core.db.storage import Storage
from core.errors.boundary import (
    PlatformAccessDeniedError,
    PlatformConflictError,
    PlatformNotFoundError,
    PlatformUnavailableError,
)
from core.logging import get_logger
from core.platform_brand.resolver import (
    UnknownPlatformDomainError,
    platform_public_base_url,
    resolve_brand,
    resolve_oauth_brand_origin,
)
from core.types import JsonObject, parse_json_object
from core.utils.domain import (
    get_protocol,
    is_allowed_integration_return_origin,
    is_local,
    split_host_port,
)
from core.utils.tokens import TokenService
from core.websocket import WsCommandError

logger = get_logger(__name__)

PAIRING_CODE_PREFIX = "agent_pairing:"
DEVICE_KEY_PREFIX = "agent_device:"
TUNNEL_ONLINE_PREFIX = "agent_tunnel_online:"
TOKEN_DENY_PREFIX = "agent_token_deny:"
AUDIT_KEY_PREFIX = "agent_audit:"
PAIRING_RATE_PREFIX = "agent_pairing_rate:"
REGISTER_RATE_PREFIX = "agent_register_rate:"
JTI_DENY_PREFIX = "agent_token_jti_deny:"
DEVICE_TOKEN_EXPIRES = 30 * 86400
PAIRING_RATE_WINDOW_SECONDS = 3600


def _device_storage_key(device_id: str) -> str:
    return f"{DEVICE_KEY_PREFIX}{device_id}"


def _pairing_storage_key(pairing_code: str) -> str:
    return f"{PAIRING_CODE_PREFIX}{pairing_code}"


def _tunnel_online_key(device_id: str) -> str:
    return f"{TUNNEL_ONLINE_PREFIX}{device_id}"


def _token_deny_key(device_id: str) -> str:
    return f"{TOKEN_DENY_PREFIX}{device_id}"


def _audit_storage_key(company_id: str) -> str:
    return f"{AUDIT_KEY_PREFIX}{company_id}"


def _github_api_base() -> str:
    settings = get_settings().agent
    configured = settings.releases.github_api_base_url
    if configured is None:
        return "https://api.github.com"
    stripped = configured.strip()
    if not stripped:
        return "https://api.github.com"
    return stripped.rstrip("/")


def _github_api_headers() -> dict[str, str]:
    settings = get_settings().agent
    headers = {"Accept": "application/vnd.github+json"}
    token = settings.releases.github_token
    if token is not None:
        stripped = token.strip()
        if stripped:
            headers["Authorization"] = f"Bearer {stripped}"
    return headers


def _pairing_rate_key(user_id: str) -> str:
    return f"{PAIRING_RATE_PREFIX}{user_id}"


def _register_rate_key(client_key: str) -> str:
    return f"{REGISTER_RATE_PREFIX}{client_key}"


def _jti_deny_key(jti: str) -> str:
    return f"{JTI_DENY_PREFIX}{jti}"


async def is_device_token_denied_shared(
    shared_storage: Storage,
    device_id: str,
    *,
    device_jti: str | None = None,
) -> bool:
    deny_raw = await shared_storage.get(
        _token_deny_key(device_id),
        force_global=True,
    )
    if deny_raw is not None:
        return True
    if device_jti is None:
        return False
    jti_deny_raw = await shared_storage.get(
        _jti_deny_key(device_jti),
        force_global=True,
    )
    return jti_deny_raw is not None


async def is_device_token_denied(
    container: BaseContainer,
    device_id: str,
    *,
    device_jti: str | None = None,
) -> bool:
    return await is_device_token_denied_shared(
        container.shared_storage,
        device_id,
        device_jti=device_jti,
    )


async def record_agent_audit_event(
    container: BaseContainer,
    *,
    company_id: str,
    event_type: str,
    actor_user_id: str | None,
    device_id: str | None,
    detail: str,
    retention_days: int = 30,
) -> None:
    audit_key = _audit_storage_key(company_id)
    event_payload = json.dumps(
        {
            "event_type": event_type,
            "actor_user_id": actor_user_id,
            "device_id": device_id,
            "detail": detail,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    retention_seconds = retention_days * 86400
    _ = await container.redis_client.eval(
        """
redis.call('RPUSH', KEYS[1], ARGV[1])
redis.call('LTRIM', KEYS[1], -500, -1)
redis.call('EXPIRE', KEYS[1], ARGV[2])
return 1
""",
        1,
        audit_key,
        event_payload,
        str(retention_seconds),
    )


async def _enforce_pairing_rate_limit(container: BaseContainer, user_id: str) -> None:
    settings = get_settings().agent
    rate_key = _pairing_rate_key(user_id)
    count_raw = await container.redis_client.eval(
        """
local current = redis.call('INCR', KEYS[1])
if current == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return current
""",
        1,
        rate_key,
        str(PAIRING_RATE_WINDOW_SECONDS),
    )
    if not isinstance(count_raw, int):
        raise PlatformUnavailableError(
            "pairing rate limit unavailable",
            error_code="pairing_rate_limit_unavailable",
        )
    if count_raw > settings.pairing_rate_limit_per_hour:
        raise WsCommandError(
            "rate_limited",
            "pairing rate limit exceeded",
            error_code="pairing_rate_limit_exceeded",
        )


async def _enforce_register_rate_limit(container: BaseContainer, client_key: str) -> None:
    settings = get_settings().agent
    rate_key = _register_rate_key(client_key)
    count_raw = await container.redis_client.eval(
        """
local current = redis.call('INCR', KEYS[1])
if current == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return current
""",
        1,
        rate_key,
        str(PAIRING_RATE_WINDOW_SECONDS),
    )
    if not isinstance(count_raw, int):
        raise PlatformUnavailableError(
            "register rate limit unavailable",
            error_code="register_rate_limit_unavailable",
        )
    if count_raw > settings.register_rate_limit_per_hour:
        raise WsCommandError(
            "rate_limited",
            "register rate limit exceeded",
            error_code="register_rate_limit_exceeded",
        )


async def list_agent_audit_events(
    container: BaseContainer,
    *,
    company_id: str,
    limit: int = 50,
) -> AgentAuditListResponse:
    if limit < 1 or limit > 500:
        raise WsCommandError(
            "ws_invalid_payload",
            "limit must be between 1 and 500",
            error_code="audit_limit_invalid",
        )
    audit_key = _audit_storage_key(company_id)
    raw_items = await container.redis_client.lrange(audit_key, -limit, -1)
    events: list[AgentAuditEvent] = []
    for raw_item in raw_items:
        payload = parse_json_object(raw_item, "agent.audit_event")
        events.append(AgentAuditEvent.model_validate(payload))
    events.reverse()
    return AgentAuditListResponse(items=events)


async def record_agent_audit_event_redis(
    redis_client: RedisClient,
    *,
    company_id: str,
    event_type: str,
    actor_user_id: str | None,
    device_id: str | None,
    detail: str,
    retention_days: int = 30,
) -> None:
    audit_key = _audit_storage_key(company_id)
    event_payload = json.dumps(
        {
            "event_type": event_type,
            "actor_user_id": actor_user_id,
            "device_id": device_id,
            "detail": detail,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    retention_seconds = retention_days * 86400
    _ = await redis_client.eval(
        """
redis.call('RPUSH', KEYS[1], ARGV[1])
redis.call('LTRIM', KEYS[1], -500, -1)
redis.call('EXPIRE', KEYS[1], ARGV[2])
return 1
""",
        1,
        audit_key,
        event_payload,
        str(retention_seconds),
    )


def _platform_mcp_url(frontend_base_url: str | None = None) -> str:
    base = frontend_base_url if frontend_base_url is not None else platform_public_base_url()
    return f"{base.rstrip('/')}/flows/api/v1/agent/platform-mcp"


def build_toolkit_mcp_url_for_frontend(
    toolkit_id: str,
    frontend_base_url: str | None = None,
) -> str:
    base = frontend_base_url if frontend_base_url is not None else platform_public_base_url()
    return f"{base.rstrip('/')}/flows/api/v1/agent/platform-mcp/{toolkit_id}"


def build_toolkits_catalog_url_for_frontend(frontend_base_url: str | None = None) -> str:
    base = frontend_base_url if frontend_base_url is not None else platform_public_base_url()
    return f"{base.rstrip('/')}/flows/api/v1/agent/toolkits"


def _llm_api_url(frontend_base_url: str | None = None) -> str:
    base = frontend_base_url if frontend_base_url is not None else platform_public_base_url()
    return f"{base.rstrip('/')}/flows/api/v1/agent/llm/v1"


def build_agent_llm_bundle(frontend_base_url: str) -> AgentLlmBundle:
    return AgentLlmBundle(api_base_url=_llm_api_url(frontend_base_url))


def _frontend_origin_from_request_host(host: str, url_scheme: str) -> str:
    scheme = url_scheme if url_scheme in ("http", "https") else get_protocol(host)
    hostname, port = split_host_port(host)
    if not hostname:
        raise ValueError("request Host must include hostname")
    origin = f"{scheme}://{hostname}"
    if port is not None:
        origin = f"{origin}:{port}"
    return origin.rstrip("/")


def resolve_brand_frontend_base_url(request_host: str | None) -> str | None:
    """Public brand apex for catalog/MCP URLs from Host (not register/discover reachability)."""
    if request_host is None or not str(request_host).strip():
        return None
    host = str(request_host).strip()
    if is_local(host):
        return None
    try:
        _ = resolve_brand(host)
    except UnknownPlatformDomainError:
        return None
    return platform_public_base_url(host)


def resolve_frontend_base_url(
    origin_override: str | None = None,
    *,
    request_host: str | None = None,
    url_scheme: str | None = None,
) -> str:
    """Reachable frontend base for register/discover/tunnel (sandbox allowlist + platform public)."""
    public_base = platform_public_base_url()
    if origin_override is not None:
        ro = origin_override.rstrip("/")
        if not is_allowed_integration_return_origin(ro, public_base):
            raise WsCommandError(
                "ws_invalid_payload",
                "origin is not allowed for register/discover",
                error_code="origin_not_allowed",
            )
        return ro
    if request_host is not None and str(request_host).strip():
        host = str(request_host).strip()
        resolved_scheme = url_scheme if url_scheme in ("http", "https") else get_protocol(host)
        host_origin = _frontend_origin_from_request_host(host, resolved_scheme)
        if is_allowed_integration_return_origin(host_origin, public_base):
            return host_origin
    return public_base


def build_tunnel_ws_url(frontend_base_url: str) -> str:
    parsed = urlparse(frontend_base_url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("frontend_base_url must use http or https")
    ws_scheme = "wss" if parsed.scheme == "https" else "ws"
    if not parsed.netloc:
        raise ValueError("frontend_base_url must include host")
    return urlunparse((ws_scheme, parsed.netloc, "/frontend/api/agent/tunnel", "", "", ""))


def build_device_register_response(
    *,
    device_id: str,
    token: str,
    company_id: str,
    company_subdomain: str | None,
    frontend_base_url: str,
) -> DeviceRegisterResponse:
    base = frontend_base_url.rstrip("/")
    return DeviceRegisterResponse(
        device_id=device_id,
        token=token,
        platform_mcp_url=_platform_mcp_url(base),
        toolkits_url=build_toolkits_catalog_url_for_frontend(base),
        frontend_base_url=base,
        tunnel_ws_url=build_tunnel_ws_url(base),
        company_id=company_id,
        company_subdomain=company_subdomain,
        llm=build_agent_llm_bundle(base),
    )


async def fetch_agent_discover(
    container: BaseContainer,
    *,
    origin_override: str | None = None,
    request_host: str | None = None,
    url_scheme: str | None = None,
) -> AgentDiscoverResponse:
    _ = container
    frontend_base_url = resolve_frontend_base_url(
        origin_override,
        request_host=request_host,
        url_scheme=url_scheme,
    )
    releases = await fetch_latest_release_status()
    return AgentDiscoverResponse(
        frontend_base_url=frontend_base_url,
        platform_mcp_url=_platform_mcp_url(frontend_base_url),
        toolkits_url=build_toolkits_catalog_url_for_frontend(frontend_base_url),
        tunnel_ws_url=build_tunnel_ws_url(frontend_base_url),
        llm_api_url=_llm_api_url(frontend_base_url),
        releases=releases,
    )


async def _fetch_latest_github_release() -> JsonObject:
    settings = get_settings().agent
    owner = settings.releases.github_owner
    repo = settings.releases.github_repo
    github_api = _github_api_base()
    url = f"{github_api}/repos/{owner}/{repo}/releases/latest"
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(url, headers=_github_api_headers())
        _ = response.raise_for_status()
        return parse_json_object(response.text, "github.release")


def _resolve_asset_url_from_release(release_payload: JsonObject, platform: str) -> str:
    distro = load_default_distro_config()
    assets_raw = release_payload.get("assets")
    if not isinstance(assets_raw, list):
        raise PlatformNotFoundError(
            f"release asset for platform {platform!r} not found",
            error_code="release_asset_not_found",
            error_params={"platform": platform},
        )

    for asset in assets_raw:
        if not isinstance(asset, dict):
            continue
        name = asset.get("name")
        if not isinstance(name, str) or not matches_release_asset_name(platform, name, distro.bundle_name):
            continue
        download_url = asset.get("browser_download_url")
        if isinstance(download_url, str) and download_url:
            logger.info("agent.download.resolved", platform=platform, asset=name)
            return download_url

    raise PlatformNotFoundError(
        f"release asset for platform {platform!r} not found",
        error_code="release_asset_not_found",
        error_params={"platform": platform},
    )


async def fetch_latest_release_asset_url(
    platform: str,
    *,
    brand_host: str | None = None,
) -> str:
    if use_local_release_artifact():
        artifact = resolve_local_release_artifact_path(platform)
        base = resolve_oauth_brand_origin(brand_host=brand_host).rstrip("/")
        route = local_release_artifact_route(platform)
        logger.info(
            "agent.download.resolved_local",
            platform=platform,
            asset=artifact.name,
            route=route,
        )
        return f"{base}{route}"
    release_payload = await _fetch_latest_github_release()
    return _resolve_asset_url_from_release(release_payload, platform)


async def _load_asset_checksums(release_payload: JsonObject) -> list[AgentReleaseAssetChecksum]:
    assets_raw = release_payload.get("assets")
    if not isinstance(assets_raw, list):
        return []
    checksums_url: str | None = None
    for asset in assets_raw:
        if not isinstance(asset, dict):
            continue
        name = asset.get("name")
        if name != "checksums.txt":
            continue
        download_url = asset.get("browser_download_url")
        if isinstance(download_url, str) and download_url:
            checksums_url = download_url
            break
    if checksums_url is None:
        return []
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(checksums_url, headers=_github_api_headers())
        _ = response.raise_for_status()
        checksums_text = response.text
    checksums: list[AgentReleaseAssetChecksum] = []
    for line in checksums_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        parts = stripped.split(None, 1)
        if len(parts) != 2:
            continue
        sha256, asset_name = parts
        checksums.append(AgentReleaseAssetChecksum(asset_name=asset_name, sha256=sha256))
    return checksums


def _release_has_pending_macos_notarization(release_payload: JsonObject) -> bool:
    assets_raw = release_payload.get("assets")
    if not isinstance(assets_raw, list):
        return False
    for asset in assets_raw:
        if not isinstance(asset, dict):
            continue
        asset_name = asset.get("name")
        if not isinstance(asset_name, str):
            continue
        if asset_name.startswith("linnex-agent-macos-notarize-") and asset_name.endswith(".json"):
            return True
    return False


def build_agent_release_status_from_github_payload(
    release_payload: JsonObject,
    *,
    github_owner: str,
    github_repo: str,
    asset_checksums: list[AgentReleaseAssetChecksum],
) -> AgentReleaseStatusResponse:
    tag_name = release_payload.get("tag_name")
    latest_tag = tag_name if isinstance(tag_name, str) and tag_name else None
    draft_value = release_payload.get("draft")
    if draft_value is True:
        return AgentReleaseStatusResponse(
            ready=False,
            latest_tag=latest_tag,
            github_owner=github_owner,
            github_repo=github_repo,
            detail="Последний release помечен как draft — опубликуйте его в GitHub",
        )

    assets_raw = release_payload.get("assets")
    if not isinstance(assets_raw, list) or not assets_raw:
        return AgentReleaseStatusResponse(
            ready=False,
            latest_tag=latest_tag,
            github_owner=github_owner,
            github_repo=github_repo,
            detail="Release без assets",
        )

    return AgentReleaseStatusResponse(
        ready=True,
        latest_tag=latest_tag,
        github_owner=github_owner,
        github_repo=github_repo,
        asset_checksums=asset_checksums,
        macos_notarization_pending=_release_has_pending_macos_notarization(release_payload),
    )


async def fetch_latest_release_status() -> AgentReleaseStatusResponse:
    settings = get_settings().agent
    owner = settings.releases.github_owner
    repo = settings.releases.github_repo
    if use_local_release_artifact():
        platform_name = detect_host_platform()
        try:
            return build_local_release_status(platform_name)
        except (FileNotFoundError, ValueError) as exc:
            return build_local_release_unavailable_status(platform_name, str(exc))
    try:
        release_payload = await _fetch_latest_github_release()
    except httpx.HTTPStatusError as exc:
        detail = f"GitHub releases/latest вернул HTTP {exc.response.status_code}"
        if exc.response.status_code == 404 and not settings.releases.github_token:
            detail += (
                ". Репозиторий private — задайте AGENT__RELEASES__GITHUB_TOKEN "
                "(PAT с Contents: Read)"
            )
        logger.warning(
            "agent.releases.unavailable",
            github_owner=owner,
            github_repo=repo,
            status_code=exc.response.status_code,
        )
        return AgentReleaseStatusResponse(
            ready=False,
            latest_tag=None,
            github_owner=owner,
            github_repo=repo,
            detail=detail,
        )

    asset_checksums = await _load_asset_checksums(release_payload)
    return build_agent_release_status_from_github_payload(
        release_payload,
        github_owner=owner,
        github_repo=repo,
        asset_checksums=asset_checksums,
    )


def _generate_pairing_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


async def create_pairing_code(
    container: BaseContainer,
    *,
    user_id: str,
    company_id: str,
) -> PairingCodeResponse:
    settings = get_settings().agent
    await _enforce_pairing_rate_limit(container, user_id)
    pairing_code = _generate_pairing_code()
    storage_key = _pairing_storage_key(pairing_code)
    payload = json.dumps({"user_id": user_id, "company_id": company_id})
    _ = await container.shared_storage.set(
        storage_key,
        payload,
        ttl=settings.pairing_ttl_seconds,
        force_global=True,
    )
    await record_agent_audit_event(
        container,
        company_id=company_id,
        event_type="agent.pairing_created",
        actor_user_id=user_id,
        device_id=None,
        detail=f"pairing_code={pairing_code}",
    )
    logger.info(
        "agent.pairing_created",
        user_id=user_id,
        company_id=company_id,
        pairing_code=pairing_code,
    )
    return PairingCodeResponse(
        pairing_code=pairing_code,
        expires_in_seconds=settings.pairing_ttl_seconds,
    )


async def register_device(
    container: BaseContainer,
    request: DeviceRegisterRequest,
    *,
    client_key: str,
    origin_override: str | None = None,
    request_host: str | None = None,
    url_scheme: str | None = None,
) -> DeviceRegisterResponse:
    await _enforce_register_rate_limit(container, client_key)
    redis_key = _pairing_storage_key(request.pairing_code)
    pairing_data_raw = await container.shared_storage.get(redis_key, force_global=True)
    if pairing_data_raw is None:
        raise WsCommandError(
            "ws_invalid_payload",
            "pairing code is invalid or expired",
            error_code="pairing_code_invalid",
        )

    try:
        pairing_data = parse_json_object(pairing_data_raw, "pairing_code")
    except ValueError as exc:
        raise WsCommandError(
            "ws_invalid_payload",
            "pairing code payload is corrupt",
            error_code="pairing_code_corrupt",
        ) from exc

    user_id = pairing_data.get("user_id")
    company_id = pairing_data.get("company_id")
    if not isinstance(user_id, str) or not user_id:
        raise WsCommandError(
            "ws_invalid_payload",
            "pairing code payload is incomplete",
            error_code="pairing_code_incomplete",
        )
    if not isinstance(company_id, str) or not company_id:
        raise WsCommandError(
            "ws_invalid_payload",
            "pairing code payload is incomplete",
            error_code="pairing_code_incomplete",
        )

    _ = await container.shared_storage.delete(redis_key, force_global=True)

    device_record = AgentDeviceRecord(
        device_id=request.device_id,
        device_name=request.device_name,
        user_id=user_id,
        company_id=company_id,
        os=request.os,
        hostname=request.hostname,
        paired_at=datetime.now(timezone.utc),
        policy=DevicePolicy(),
        is_active=True,
    )
    device_key = _device_storage_key(request.device_id)
    _ = await container.shared_storage.set(
        device_key,
        device_record.model_dump_json(),
        force_global=True,
    )
    try:
        await container.authz_service.write(
            [
                agent_device_company_link(request.device_id, company_id),
                agent_device_owner_tuple(request.device_id, user_id),
            ]
        )
    except Exception:
        _ = await container.shared_storage.delete(device_key, force_global=True)
        raise

    token_service = TokenService()
    device_jti = str(uuid.uuid4())
    token = token_service.create_token(
        user_id=user_id,
        company_id=company_id,
        expires_in=DEVICE_TOKEN_EXPIRES,
        metadata={
            "token_purpose": "device",
            "device_id": request.device_id,
            "jti": device_jti,
        },
    )

    device_record.active_device_jti = device_jti
    _ = await container.shared_storage.set(
        device_key,
        device_record.model_dump_json(),
        force_global=True,
    )

    await record_agent_audit_event(
        container,
        company_id=company_id,
        event_type="agent.device_registered",
        actor_user_id=user_id,
        device_id=request.device_id,
        detail=request.device_name,
    )

    logger.info(
        "agent.device_registered",
        device_id=request.device_id,
        user_id=user_id,
        company_id=company_id,
        device_name=request.device_name,
        os=request.os,
    )

    company_record = await container.company_repository.get(company_id)
    if company_record is None:
        raise PlatformNotFoundError(
            f"company not found: {company_id}",
            error_code="company_not_found",
            error_params={"company_id": company_id},
        )

    frontend_base_url = resolve_frontend_base_url(
        origin_override,
        request_host=request_host,
        url_scheme=url_scheme,
    )
    return build_device_register_response(
        device_id=request.device_id,
        token=token,
        company_id=company_id,
        company_subdomain=company_record.subdomain,
        frontend_base_url=frontend_base_url,
    )


async def register_device_with_auth(
    container: BaseContainer,
    request: DeviceRegisterWithAuthRequest,
    *,
    user_id: str,
    company_id: str,
    origin_override: str | None = None,
    request_host: str | None = None,
    url_scheme: str | None = None,
) -> DeviceRegisterResponse:
    device_key = _device_storage_key(request.device_id)
    existing_raw = await container.shared_storage.get(device_key, force_global=True)
    if existing_raw is not None:
        existing = AgentDeviceRecord.model_validate_json(existing_raw)
        if existing.company_id != company_id:
            raise PlatformConflictError(
                "device_id is already registered in another company",
                error_code="device_registered_other_company",
            )
        if existing.user_id != user_id:
            raise PlatformConflictError(
                "device_id belongs to another user",
                error_code="device_registered_other_user",
            )
        if not existing.is_active:
            raise PlatformConflictError(
                "device_id is revoked",
                error_code="device_revoked",
            )

    device_record = AgentDeviceRecord(
        device_id=request.device_id,
        device_name=request.device_name,
        user_id=user_id,
        company_id=company_id,
        os=request.os,
        hostname=request.hostname,
        paired_at=datetime.now(timezone.utc),
        policy=DevicePolicy(),
        is_active=True,
    )
    _ = await container.shared_storage.set(
        device_key,
        device_record.model_dump_json(),
        force_global=True,
    )
    try:
        await container.authz_service.write(
            [
                agent_device_company_link(request.device_id, company_id),
                agent_device_owner_tuple(request.device_id, user_id),
            ]
        )
    except Exception:
        _ = await container.shared_storage.delete(device_key, force_global=True)
        raise

    token_service = TokenService()
    device_jti = str(uuid.uuid4())
    token = token_service.create_token(
        user_id=user_id,
        company_id=company_id,
        expires_in=DEVICE_TOKEN_EXPIRES,
        metadata={
            "token_purpose": "device",
            "device_id": request.device_id,
            "jti": device_jti,
        },
    )

    device_record.active_device_jti = device_jti
    _ = await container.shared_storage.set(
        device_key,
        device_record.model_dump_json(),
        force_global=True,
    )

    await record_agent_audit_event(
        container,
        company_id=company_id,
        event_type="agent.device_registered",
        actor_user_id=user_id,
        device_id=request.device_id,
        detail=f"{request.device_name} (auth)",
    )

    logger.info(
        "agent.device_registered",
        device_id=request.device_id,
        user_id=user_id,
        company_id=company_id,
        device_name=request.device_name,
        os=request.os,
        auth_flow=True,
    )

    company_record = await container.company_repository.get(company_id)
    if company_record is None:
        raise PlatformNotFoundError(
            f"company not found: {company_id}",
            error_code="company_not_found",
            error_params={"company_id": company_id},
        )

    frontend_base_url = resolve_frontend_base_url(
        origin_override,
        request_host=request_host,
        url_scheme=url_scheme,
    )
    return build_device_register_response(
        device_id=request.device_id,
        token=token,
        company_id=company_id,
        company_subdomain=company_record.subdomain,
        frontend_base_url=frontend_base_url,
    )


async def list_company_devices(
    container: BaseContainer,
    *,
    company_id: str,
    viewer_user_id: str,
    owner_user_id: str | None = None,
) -> list[AgentDeviceListItem]:
    allowed = await container.authz_service.list_objects(
        AuthzSubject.user(viewer_user_id),
        AuthzRelation.CAN_VIEW,
        AuthzObjectType.AGENT_DEVICE,
    )
    allowed_keys = {obj.object_key for obj in allowed}
    records = await container.shared_storage.get_all_by_prefix(
        DEVICE_KEY_PREFIX,
        limit=1000,
        force_global=True,
    )
    items: list[AgentDeviceListItem] = []
    for storage_key, raw_value in records.items():
        if not storage_key.startswith(DEVICE_KEY_PREFIX):
            continue
        device = AgentDeviceRecord.model_validate_json(raw_value)
        if device.company_id != company_id:
            continue
        if device.device_id not in allowed_keys:
            continue
        if owner_user_id is not None and device.user_id != owner_user_id:
            continue
        tunnel_online = await is_device_tunnel_online(container, device.device_id)
        items.append(
            AgentDeviceListItem(
                device_id=device.device_id,
                device_name=device.device_name,
                user_id=device.user_id,
                company_id=device.company_id,
                os=device.os,
                hostname=device.hostname,
                paired_at=device.paired_at,
                last_seen_at=device.last_seen_at,
                is_active=device.is_active,
                is_tunnel_online=tunnel_online,
                policy=device.policy,
            )
        )
    items.sort(key=lambda item: item.paired_at, reverse=True)
    return items


async def get_device_record(
    container: BaseContainer,
    device_id: str,
) -> AgentDeviceRecord:
    raw_value = await container.shared_storage.get(
        _device_storage_key(device_id),
        force_global=True,
    )
    if raw_value is None:
        raise PlatformNotFoundError("device not found", error_code="device_not_found")
    return AgentDeviceRecord.model_validate_json(raw_value)


async def mark_device_tunnel_online(
    container: BaseContainer,
    *,
    device_id: str,
) -> None:
    settings = get_settings().agent
    device = await get_device_record(container, device_id)
    if not device.is_active:
        raise PlatformAccessDeniedError(
            "device is deactivated",
            error_code="device_deactivated",
        )

    device.last_seen_at = datetime.now(timezone.utc)
    _ = await container.shared_storage.set(
        _device_storage_key(device_id),
        device.model_dump_json(),
        force_global=True,
    )
    _ = await container.shared_storage.set(
        _tunnel_online_key(device_id),
        json.dumps({"device_id": device_id, "online_at": device.last_seen_at.isoformat()}),
        ttl=settings.tunnel_online_ttl_seconds,
        force_global=True,
    )


async def mark_device_tunnel_offline(
    container: BaseContainer,
    *,
    device_id: str,
) -> None:
    _ = await container.shared_storage.delete(_tunnel_online_key(device_id), force_global=True)


async def device_tunnel_is_online(storage: Storage, device_id: str) -> bool:
    online_raw = await storage.get(
        _tunnel_online_key(device_id),
        force_global=True,
    )
    return online_raw is not None


async def is_device_tunnel_online(
    container: BaseContainer,
    device_id: str,
) -> bool:
    return await device_tunnel_is_online(container.shared_storage, device_id)


async def update_device_policy(
    container: BaseContainer,
    *,
    device_id: str,
    company_id: str,
    policy: DevicePolicy,
) -> AgentDeviceRecord:
    device = await get_device_record(container, device_id)
    if device.company_id != company_id:
        raise PlatformNotFoundError("device not found", error_code="device_not_found")
    device.policy = policy
    _ = await container.shared_storage.set(
        _device_storage_key(device_id),
        device.model_dump_json(),
        force_global=True,
    )
    await record_agent_audit_event(
        container,
        company_id=company_id,
        event_type="agent.device_policy_updated",
        actor_user_id=None,
        device_id=device_id,
        detail=policy.model_dump_json(),
    )
    await push_device_policy_to_tunnel(device_id, policy)
    return device


async def revoke_device(
    container: BaseContainer,
    *,
    device_id: str,
    company_id: str,
    actor_user_id: str,
) -> None:
    device = await get_device_record(container, device_id)
    if device.company_id != company_id:
        raise PlatformNotFoundError("device not found", error_code="device_not_found")
    try:
        await container.authz_service.require_can_admin(
            AuthzObject.agent_device(device_id),
            user_id=actor_user_id,
        )
    except AuthzDenied as exc:
        raise PlatformAccessDeniedError(
            "not allowed to revoke device",
            error_code="device_revoke_forbidden",
        ) from exc
    device.is_active = False
    _ = await container.shared_storage.set(
        _device_storage_key(device_id),
        device.model_dump_json(),
        force_global=True,
    )
    _ = await container.shared_storage.set(
        _token_deny_key(device_id),
        json.dumps({"revoked_at": datetime.now(timezone.utc).isoformat()}),
        ttl=DEVICE_TOKEN_EXPIRES,
        force_global=True,
    )
    if device.active_device_jti is not None:
        _ = await container.shared_storage.set(
            _jti_deny_key(device.active_device_jti),
            json.dumps({"revoked_at": datetime.now(timezone.utc).isoformat()}),
            ttl=DEVICE_TOKEN_EXPIRES,
            force_global=True,
        )
    _ = await container.shared_storage.delete(_tunnel_online_key(device_id), force_global=True)
    await publish_tunnel_disconnect(container.redis_client, device_id)
    await record_agent_audit_event(
        container,
        company_id=company_id,
        event_type="agent.device_revoked",
        actor_user_id=None,
        device_id=device_id,
        detail="revoked",
    )
    logger.info(
        "agent.device_revoked",
        device_id=device_id,
        company_id=company_id,
    )


def build_flow_mcp_tools(flows: list[JsonObject]) -> list[JsonObject]:
    tools: list[JsonObject] = []
    for flow_payload in flows:
        flow_id = flow_payload.get("flow_id")
        name = flow_payload.get("name")
        description = flow_payload.get("description")
        if not isinstance(flow_id, str) or not flow_id:
            continue
        if not isinstance(name, str) or not name:
            name = flow_id
        if not isinstance(description, str):
            description = f"Humanitec flow {flow_id}"
        tools.append(
            {
                "name": f"flow_{flow_id}",
                "description": description,
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "message": {
                            "type": "string",
                            "description": "User message for the flow",
                        },
                        "context_id": {
                            "type": "string",
                            "description": (
                                "Optional A2A context_id for session continuity. "
                                "Pass the context_id from the previous tool result to continue "
                                "the same conversation; omit to use the server sticky session."
                            ),
                        },
                    },
                    "required": ["message"],
                },
            }
        )
    return tools
