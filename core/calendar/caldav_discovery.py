"""
Определение CalDAV-эндпоинта для почтового ящика.

Порядок разрешения: пресет по домену адреса -> пресет по IMAP-хосту ->
RFC 6764 проба /.well-known/caldav на почтовом домене.
"""

from __future__ import annotations

from enum import StrEnum

import httpx2

from core.config import get_settings
from core.http import get_httpx_client
from core.logging import get_logger
from core.models import CalendarProvider
from core.models.base import StrictBaseModel

logger = get_logger(__name__)


# Единый протокол CalDAV: разные провайдеры = разные base_url, один клиент.
CALDAV_PROVIDERS: frozenset[CalendarProvider] = frozenset(
    {CalendarProvider.YANDEX, CalendarProvider.MAILRU, CalendarProvider.CALDAV}
)

# Preset base_url для известных парольных провайдеров. CALDAV (custom) требует
# явного caldav_base_url в payload/settings.
CALDAV_PRESET_BASE_URLS: dict[CalendarProvider, str] = {
    CalendarProvider.YANDEX: "https://caldav.yandex.ru",
    CalendarProvider.MAILRU: "https://calendar.mail.ru",
}

# Провайдеры, у которых календарь доступен только по OAuth: парольный CalDAV
# для них не существует, авто-подъём по app password невозможен.
_OAUTH_ONLY_DOMAINS: frozenset[str] = frozenset({"gmail.com", "googlemail.com"})

# Домен адреса -> парольный CalDAV-провайдер. Домены-алиасы одного провайдера
# перечислены явно: у них общий CalDAV-эндпоинт.
CALDAV_DOMAIN_PRESETS: dict[str, CalendarProvider] = {
    "mail.ru": CalendarProvider.MAILRU,
    "inbox.ru": CalendarProvider.MAILRU,
    "list.ru": CalendarProvider.MAILRU,
    "bk.ru": CalendarProvider.MAILRU,
    "internet.ru": CalendarProvider.MAILRU,
    "yandex.ru": CalendarProvider.YANDEX,
    "yandex.com": CalendarProvider.YANDEX,
    "yandex.by": CalendarProvider.YANDEX,
    "yandex.kz": CalendarProvider.YANDEX,
    "yandex.uz": CalendarProvider.YANDEX,
    "ya.ru": CalendarProvider.YANDEX,
    "narod.ru": CalendarProvider.YANDEX,
}

# IMAP-хост как вторичный сигнал: адрес может быть на своём домене, а ящик
# физически обслуживаться известным провайдером.
CALDAV_IMAP_HOST_PRESETS: dict[str, CalendarProvider] = {
    "imap.yandex.com": CalendarProvider.YANDEX,
    "imap.yandex.ru": CalendarProvider.YANDEX,
    "imap.mail.ru": CalendarProvider.MAILRU,
}


class CaldavAutolinkKind(StrEnum):
    CALDAV = "caldav"
    NEEDS_OAUTH = "needs_oauth"
    UNSUPPORTED = "unsupported"


class CaldavAutolinkResolution(StrictBaseModel):
    """Результат разрешения CalDAV-эндпоинта для ящика."""

    kind: CaldavAutolinkKind
    provider: CalendarProvider | None = None
    base_url: str | None = None
    detail: str

    def require_target(self) -> tuple[CalendarProvider, str]:
        if self.kind != CaldavAutolinkKind.CALDAV:
            raise ValueError(f"CalDAV target is not resolved: kind={self.kind}")
        if self.provider is None or self.base_url is None:
            raise ValueError("Resolved CalDAV target must have provider and base_url")
        return self.provider, self.base_url


def caldav_provider_for_imap_host(imap_host: str) -> CalendarProvider | None:
    return CALDAV_IMAP_HOST_PRESETS.get(imap_host.strip().lower())


def caldav_provider_for_mail_domain(mail_domain: str) -> CalendarProvider | None:
    return CALDAV_DOMAIN_PRESETS.get(mail_domain.strip().lower())


def resolve_caldav_base_url(provider: CalendarProvider, explicit_base_url: str | None) -> str:
    """base_url приоритет: явный (settings/payload) -> preset. Fail-closed для custom."""
    if explicit_base_url and explicit_base_url.strip():
        return explicit_base_url.strip().rstrip("/")
    preset = CALDAV_PRESET_BASE_URLS.get(provider)
    if preset is None:
        raise ValueError(f"CalDAV provider {provider} requires explicit caldav_base_url")
    return preset


def caldav_probe_decision(status_code: int) -> bool:
    """
    Есть ли CalDAV по адресу пробы. 401 значит "эндпоинт есть, нужна авторизация",
    поэтому считается успехом наравне с 2xx/3xx.
    """
    if 200 <= status_code < 400:
        return True
    return status_code == 401


def well_known_caldav_url(mail_domain: str) -> str:
    normalized = mail_domain.strip().lower().rstrip(".")
    if not normalized:
        raise ValueError("mail_domain must not be empty")
    return f"https://{normalized}/.well-known/caldav"


def caldav_base_url_from_probe(probe_url: str, final_url: str) -> str:
    """
    base_url для клиента: origin конечного адреса после редиректов. Путь
    /.well-known/caldav отбрасывается, дальше работает RFC 4791 discovery.
    """
    parsed = httpx2.URL(final_url if final_url else probe_url)
    if not parsed.scheme or not parsed.host:
        raise ValueError(f"CalDAV probe returned unusable URL: {final_url!r}")
    port = f":{parsed.port}" if parsed.port is not None else ""
    return f"{parsed.scheme}://{parsed.host}{port}"


async def probe_well_known_caldav(mail_domain: str, *, timeout_seconds: float) -> str | None:
    """
    RFC 6764: GET https://<mail_domain>/.well-known/caldav. Возвращает base_url
    найденного сервера или None, если по домену CalDAV нет.
    """
    probe_url = well_known_caldav_url(mail_domain)
    async with get_httpx_client(timeout=timeout_seconds, follow_redirects=True) as client:
        response = await client.get(probe_url)
    if not caldav_probe_decision(response.status_code):
        return None
    return caldav_base_url_from_probe(probe_url, str(response.url))


async def resolve_caldav_target(
    *,
    mail_domain: str,
    imap_host: str,
) -> CaldavAutolinkResolution:
    """
    Где CalDAV этого ящика: домен-пресет -> IMAP-host-пресет -> well-known проба.
    """
    normalized_domain = mail_domain.strip().lower()
    if not normalized_domain:
        raise ValueError("mail_domain is required to resolve CalDAV target")

    if normalized_domain in _OAUTH_ONLY_DOMAINS:
        return CaldavAutolinkResolution(
            kind=CaldavAutolinkKind.NEEDS_OAUTH,
            provider=CalendarProvider.GOOGLE,
            detail=f"{normalized_domain} calendar requires OAuth, password CalDAV is unavailable",
        )

    domain_provider = caldav_provider_for_mail_domain(normalized_domain)
    if domain_provider is not None:
        return CaldavAutolinkResolution(
            kind=CaldavAutolinkKind.CALDAV,
            provider=domain_provider,
            base_url=resolve_caldav_base_url(domain_provider, None),
            detail=f"domain preset {normalized_domain}",
        )

    host_provider = caldav_provider_for_imap_host(imap_host)
    if host_provider is not None:
        return CaldavAutolinkResolution(
            kind=CaldavAutolinkKind.CALDAV,
            provider=host_provider,
            base_url=resolve_caldav_base_url(host_provider, None),
            detail=f"imap host preset {imap_host.strip().lower()}",
        )

    config = get_settings().calendar_sync
    if not config.autolink_well_known_probe_enabled:
        return CaldavAutolinkResolution(
            kind=CaldavAutolinkKind.UNSUPPORTED,
            detail=f"no CalDAV preset for {normalized_domain}, well-known probe is disabled",
        )

    probed_base_url = await probe_well_known_caldav(
        normalized_domain,
        timeout_seconds=config.autolink_probe_timeout_seconds,
    )
    if probed_base_url is None:
        return CaldavAutolinkResolution(
            kind=CaldavAutolinkKind.UNSUPPORTED,
            detail=f"no CalDAV endpoint at {well_known_caldav_url(normalized_domain)}",
        )
    return CaldavAutolinkResolution(
        kind=CaldavAutolinkKind.CALDAV,
        provider=CalendarProvider.CALDAV,
        base_url=probed_base_url,
        detail=f"well-known discovery {probed_base_url}",
    )
