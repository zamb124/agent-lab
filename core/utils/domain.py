"""
Утилиты для работы с доменами.
Поддержка нескольких доменов (humanitec.ru, agents-lab.ru) и localhost.
"""

from __future__ import annotations

import ipaddress
from urllib.parse import urlparse

PRIMARY_DOMAIN = "humanitec.ru"
SUPPORTED_DOMAINS = ["humanitec.ru", "agents-lab.ru"]


def split_host_port(host: str) -> tuple[str, str | None]:
    """
    Разбор Host header: имя и опциональный порт.

    Не использовать host.split(':')[0]: для 127.0.0.1:8002 это даёт «127».
    """
    host = host.strip()
    if not host:
        return "", None
    if host.startswith("["):
        end = host.find("]")
        if end <= 0:
            return host.lower(), None
        inner = host[1:end].lower()
        after = host[end + 1 :]
        if after.startswith(":") and after[1:].isdigit():
            return inner, after[1:]
        return inner, None
    if ":" in host:
        name, tail = host.rsplit(":", 1)
        if tail.isdigit():
            return name.lower(), tail
    return host.lower(), None


def _ip_dev_base(hostname: str) -> str | None:
    """Loopback / private / link-local IP для локальной разработки и LAN."""
    try:
        ip = ipaddress.ip_address(hostname)
    except ValueError:
        return None
    if ip.is_loopback or ip.is_private or ip.is_link_local:
        return str(ip)
    return None


def extract_base_domain(host: str) -> str:
    """
    Извлекает базовый домен из Host header.

    Примеры:
        humanitec.ru → humanitec.ru
        www.humanitec.ru → humanitec.ru
        company.humanitec.ru → humanitec.ru
        agents-lab.ru → agents-lab.ru
        company.agents-lab.ru → agents-lab.ru
        localhost:8002 → localhost
        company.localhost:8002 → localhost
        lvh.me:8002 → lvh.me
        company.lvh.me:8002 → lvh.me
        127.0.0.1:8002 → 127.0.0.1
        192.168.1.10:8002 → 192.168.1.10
    """
    hostname, _ = split_host_port(host)
    if not hostname:
        return PRIMARY_DOMAIN

    ip_base = _ip_dev_base(hostname)
    if ip_base is not None:
        return ip_base

    if hostname == "localhost" or hostname.endswith(".localhost"):
        return "localhost"

    if hostname == "lvh.me" or hostname.endswith(".lvh.me"):
        return "lvh.me"

    for domain in SUPPORTED_DOMAINS:
        if hostname == domain or hostname.endswith(f".{domain}"):
            return domain

    return PRIMARY_DOMAIN


def extract_subdomain(host: str) -> str | None:
    """
    Извлекает subdomain из Host header.

    Примеры:
        humanitec.ru → None
        www.humanitec.ru → None
        company.humanitec.ru → company
        my-company.agents-lab.ru → my-company
        localhost → None
        company.localhost:8002 → company
    """
    base = extract_base_domain(host)
    hostname, _ = split_host_port(host)

    if hostname == base or hostname == f"www.{base}":
        return None

    if hostname.endswith(f".{base}"):
        return hostname.removesuffix(f".{base}")

    return None


INFRA_NON_COMPANY_SUBDOMAINS: frozenset[str] = frozenset({"grafana"})


def extract_company_subdomain(host: str) -> str | None:
    """
    Субдомен для привязки Host к компании.

    Хосты вида grafana.<base_domain> — инфраструктурные Ingress, не компании:
    для них возвращается None, чтобы JWT/X-Company-Id определяли компанию.
    """
    label = extract_subdomain(host)
    if label and label in INFRA_NON_COMPANY_SUBDOMAINS:
        return None
    return label


def is_local(host: str) -> bool:
    """Локальная разработка: localhost, lvh.me, loopback/private/link-local IP."""
    base = extract_base_domain(host)
    if base == "localhost" or base == "lvh.me":
        return True
    if _ip_dev_base(base) is not None:
        return True
    return False


def is_supported_domain(host: str) -> bool:
    """Поддерживаемый прод-домен, localhost, lvh.me или dev IP."""
    base = extract_base_domain(host)
    if base == "localhost" or base == "lvh.me" or base in SUPPORTED_DOMAINS:
        return True
    if _ip_dev_base(base) is not None:
        return True
    return False


def _default_port_for_scheme(scheme: str) -> str:
    return "443" if scheme == "https" else "80"


def _hosts_same_company_host_cluster(o_host: str, p_host: str) -> bool:
    """Один кластер company-hosts: apex, поддомен того же base, localhost/*.localhost, один dev-IP."""
    if o_host == p_host:
        return True
    base = extract_base_domain(p_host)
    if base == "localhost":
        return o_host == "localhost" or o_host.endswith(".localhost")
    if _ip_dev_base(base) is not None:
        return o_host == p_host
    if o_host.endswith(f".{base}") and len(o_host) > len(base) + 1:
        return extract_base_domain(o_host) == base
    return False


def is_allowed_integration_return_origin(origin: str, platform_public_base_url: str | None) -> bool:
    """
    Разрешённый origin вкладки после OAuth: тот же scheme, хост в том же company-host кластере,
    что и server.platform_public_base_url, и совпадающий порт (или локальный dev: lvh.me,
    localhost, dev-IP — разный порт допустим при том же кластере хостов).

    Исключает open-redirect на чужие хосты в проде.
    """
    if not origin or not str(origin).strip():
        return False
    if not platform_public_base_url or not str(platform_public_base_url).strip():
        return False
    o = urlparse(str(origin).strip())
    p = urlparse(str(platform_public_base_url).strip())
    if o.scheme not in ("http", "https") or p.scheme not in ("http", "https"):
        return False
    if o.scheme != p.scheme:
        return False
    o_host, o_port = split_host_port(o.netloc)
    p_host, p_port = split_host_port(p.netloc)
    if not o_host or not p_host:
        return False
    o_effective = o_port if o_port else _default_port_for_scheme(o.scheme)
    p_effective = p_port if p_port else _default_port_for_scheme(p.scheme)
    if o_effective != p_effective:
        if not (
            is_local(o_host)
            and is_local(p_host)
            and _hosts_same_company_host_cluster(o_host, p_host)
        ):
            return False
    return _hosts_same_company_host_cluster(o_host, p_host)


def get_protocol(host: str) -> str:
    """Протокол: http для локальной разработки, https для остального."""
    return "http" if is_local(host) else "https"


def build_company_subdomain_absolute_url(
    *,
    host_header: str,
    url_scheme: str,
    path: str,
    query: str,
    company_subdomain: str,
) -> str:
    """
    Полный URL с тем же path/query и портом Host, на DNS-субдомене company_subdomain.
    Согласовано с core/frontend/static/lib/utils/company-url.js (buildCompanySubdomainUrl).

    Raises:
        ValueError: пустой company_subdomain или базовый хост — IP (нет foo.<IP> в DNS).
    """
    if not company_subdomain or not str(company_subdomain).strip():
        raise ValueError("company_subdomain must be non-empty")
    company_subdomain = str(company_subdomain).strip()
    base = extract_base_domain(host_header)
    if _ip_dev_base(base) is not None:
        raise ValueError("company subdomain URL cannot be built for IP-only base host")
    _, port_part = split_host_port(host_header)
    scheme = url_scheme if url_scheme in ("http", "https") else get_protocol(host_header)
    normalized_path = path if path.startswith("/") else f"/{path}"
    netloc = f"{company_subdomain}.{base}"
    if port_part:
        netloc = f"{netloc}:{port_part}"
    qs = f"?{query}" if query else ""
    return f"{scheme}://{netloc}{normalized_path}{qs}"


def get_host_with_port(host: str) -> str:
    """
    Базовый хост с портом для локальных origin (OAuth redirect_uri, ссылки).

    Примеры:
        localhost:8002 → localhost:8002
        company.localhost:8002 → localhost:8002
        lvh.me:8002 → lvh.me:8002
        company.lvh.me:8002 → lvh.me:8002
        127.0.0.1:8002 → 127.0.0.1:8002
        humanitec.ru → humanitec.ru
        company.humanitec.ru → humanitec.ru
    """
    base = extract_base_domain(host)
    _, port_part = split_host_port(host)
    port = port_part if port_part else "8002"

    if base == "localhost" or base == "lvh.me":
        return f"{base}:{port}"
    if _ip_dev_base(base) is not None:
        return f"{base}:{port}"

    return base


def get_cookie_domain(host: str) -> str | None:
    """
    Домен для cookie (с точкой в начале для субдоменов на проде).

    Примеры:
        localhost:8002 → localhost
        company.localhost:8002 → localhost
        lvh.me:8002 → .lvh.me
        company.lvh.me:8002 → .lvh.me
        humanitec.ru → .humanitec.ru
        company.humanitec.ru → .humanitec.ru

    Note:
        Для *.localhost задаём Domain=localhost, иначе кука host-only привязана к
        конкретному поддомену и после смены компании (редирект на другой slug)
        браузер не шлёт auth_token — повторный вход.
        Для IP не задаём domain (нет общего суффикса под подсети).
    """
    base = extract_base_domain(host)

    if base == "localhost":
        return "localhost"
    if _ip_dev_base(base) is not None:
        return None

    return f".{base}"


def build_url(host: str, path: str = "", subdomain: str | None = None) -> str:
    """
    Полный URL с учётом текущего домена.

    Args:
        host: Host header из запроса
        path: Путь (начинается с /)
        subdomain: Поддомен (опционально)

    Returns:
        Полный URL (http для локальной разработки, https для production)
    """
    protocol = get_protocol(host)
    base = get_host_with_port(host)

    if subdomain:
        return f"{protocol}://{subdomain}.{base}{path}"

    return f"{protocol}://{base}{path}"
