"""Разрешение бренда платформы по Host header."""

from __future__ import annotations

from urllib.parse import urlparse

from core.config import get_settings
from core.config.models import PlatformBrandConfig
from core.context import get_context
from core.logging import get_logger
from core.utils.domain import extract_base_domain, get_protocol, is_local, split_host_port

logger = get_logger(__name__)


class UnknownPlatformDomainError(ValueError):
    """Host не принадлежит ни одному настроенному platform brand apex."""


def supported_domains() -> tuple[str, ...]:
    return tuple(get_settings().platform_brands.keys())


def resolve_brand_domain(host: str) -> str:
    return extract_base_domain(host)


def resolve_brand(host: str) -> PlatformBrandConfig:
    try:
        base_domain = extract_base_domain(host)
    except ValueError as exc:
        raise UnknownPlatformDomainError(str(exc)) from exc
    brands = get_settings().platform_brands
    brand = brands.get(base_domain)
    if brand is None:
        raise UnknownPlatformDomainError(f"unsupported platform domain: {base_domain}")
    return brand


def resolve_brand_or_primary(host: str | None) -> PlatformBrandConfig:
    """Бренд Host. Пустой или неизвестный Host — primary_platform_domain."""
    settings = get_settings()
    primary = settings.platform_brands[settings.primary_platform_domain]
    if host is None or host.strip() == "":
        return primary
    normalized = host.strip()
    try:
        return resolve_brand(normalized)
    except UnknownPlatformDomainError as exc:
        logger.info(
            "platform_brand_unknown_host",
            host=normalized,
            error=str(exc),
        )
        return primary


def resolve_public_base_url(host: str) -> str:
    base_domain = extract_base_domain(host)
    protocol = get_protocol(host)
    return f"{protocol}://{base_domain}"


def resolve_brand_apex_origin(host: str, *, url_scheme: str) -> str:
    """Публичный origin бренда для bootstrap: dev host сохраняет subdomain и порт."""
    if is_local(host):
        hostname, port = split_host_port(host)
        origin = f"{url_scheme}://{hostname}"
        if port is not None:
            origin = f"{origin}:{port}"
        return origin.rstrip("/") + "/"
    return resolve_public_base_url(host).rstrip("/") + "/"


def resolve_infrastructure_service_url(host: str, service_subdomain: str) -> str:
    """Публичный URL инфраструктурного поддомена (onlyoffice, grafana, …) на apex запроса."""
    base_domain = extract_base_domain(host)
    protocol = get_protocol(host)
    return f"{protocol}://{service_subdomain}.{base_domain}"


def resolve_livekit_public_url(host: str) -> str:
    """WebSocket URL LiveKit для браузера на apex запроса (wss://livekit.<apex>)."""
    base_domain = extract_base_domain(host)
    protocol = get_protocol(host)
    ws_scheme = "wss" if protocol == "https" else "ws"
    return f"{ws_scheme}://livekit.{base_domain}"


def resolve_flows_webhook_public_base_url(host: str) -> str:
    """Публичный origin flows для Telegram/webhook: https://<apex>/flows."""
    return f"{resolve_public_base_url(host).rstrip('/')}/flows"


def resolve_flows_webhook_public_base_url_from_context() -> str | None:
    """flows webhook base из Context.host; None если host недоступен."""
    host = resolve_context_host()
    if host is None:
        return None
    try:
        return resolve_flows_webhook_public_base_url(host)
    except ValueError:
        return None


def resolve_auth_apple_client_id(host: str) -> str:
    """Apple Services ID (client_id) для OAuth на apex запроса."""
    brand = resolve_brand(host)
    if brand.auth_apple_client_id is not None and str(brand.auth_apple_client_id).strip():
        return str(brand.auth_apple_client_id).strip()
    settings = get_settings()
    apple_config = settings.auth.providers.get("apple")
    if apple_config is None or not apple_config.client_id:
        raise ValueError("apple client_id is not configured")
    return apple_config.client_id


def resolve_vapid_email(host: str | None = None) -> str:
    """VAPID sub email для push: per-brand или deployment default."""
    settings = get_settings()
    if host is not None and host.strip() != "":
        normalized = host.strip()
        try:
            brand = resolve_brand(normalized)
        except UnknownPlatformDomainError as exc:
            logger.info(
                "platform_brand_unknown_host",
                host=normalized,
                error=str(exc),
            )
        else:
            if brand.vapid_email is not None and brand.vapid_email.strip() != "":
                return brand.vapid_email.strip()
    return settings.push.vapid_email


def resolve_embed_origins(host: str) -> tuple[str, str]:
    brand = resolve_brand(host)
    base_domain = extract_base_domain(host)
    protocol = get_protocol(host)
    script_url = (
        f"{protocol}://{brand.embed_cdn_subdomain}.{base_domain}{brand.embed_script_path}"
    )
    api_base_url = f"{protocol}://{brand.embed_api_subdomain}.{base_domain}"
    return script_url, api_base_url


def resolve_context_host() -> str | None:
    """Host из request Context (после AuthMiddleware)."""
    context = get_context()
    if context is None:
        return None
    host = str(context.host).strip()
    if not host:
        return None
    return host


def resolve_oauth_brand_origin(
    *,
    brand_host: str | None = None,
    return_origin: str | None = None,
) -> str:
    """Публичный apex origin для OAuth redirect_uri по Host вкладки или контекста."""
    host: str | None = None
    if brand_host is not None and str(brand_host).strip():
        host = str(brand_host).strip()
    elif return_origin is not None and str(return_origin).strip():
        parsed = urlparse(str(return_origin).strip().rstrip("/"))
        if parsed.scheme in ("http", "https") and parsed.netloc:
            host = parsed.netloc
    if host is None:
        host = resolve_context_host()
    if host is not None:
        base_domain = extract_base_domain(host)
        protocol = get_protocol(host)
        return f"{protocol}://{base_domain}"
    settings = get_settings()
    public_base = settings.server.platform_public_base_url
    if public_base is not None and str(public_base).strip():
        return str(public_base).strip().rstrip("/")
    service_url = settings.server.get_service_url()
    parsed = urlparse(service_url)
    if parsed.scheme in ("http", "https") and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"
    raise ValueError("cannot resolve OAuth brand origin: host and platform_public_base_url missing")


def platform_public_base_url(host: str | None = None) -> str:
    """Публичный origin платформы: из Host запроса или `server.platform_public_base_url`."""
    if host is not None and host.strip():
        return resolve_public_base_url(host.strip()).rstrip("/")
    base_url = get_settings().server.platform_public_base_url
    if base_url is None or base_url.strip() == "":
        raise ValueError("server.platform_public_base_url must be configured for public URLs")
    return base_url.rstrip("/")
