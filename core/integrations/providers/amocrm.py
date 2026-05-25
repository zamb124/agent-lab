"""
AmoCRM / Kommo: поддомен в URL OAuth, разбор referer, query авторизации.
"""

from __future__ import annotations

from urllib.parse import urlencode, urlparse


def normalize_amocrm_subdomain_query(value: str) -> str:
    """
    Параметр subdomain из query: допускается короткий slug (mycompany) или полный URL/хост
    (https://mycompany.amocrm.ru/, mycompany.kommo.com).
    """
    s = value.strip()
    if not s:
        raise ValueError("Поддомен Amo пустой")
    if "://" in s:
        parsed = urlparse(s)
        host = (parsed.hostname or "").strip().lower()
    else:
        host = s.split("/")[0].strip().lower()
    if not host:
        raise ValueError("Не удалось разобрать хост поддомена Amo")
    for suffix in (".amocrm.ru", ".kommo.com", ".amocrm.com"):
        if host.endswith(suffix) and len(host) > len(suffix):
            sub = host[: -len(suffix)].strip(".")
            if not sub:
                raise ValueError("Пустая метка поддомена Amo")
            return sub
    if "." in host:
        return host.split(".")[0]
    return host


def interpolate_subdomain_in_url(url: str, subdomain: str) -> str:
    if "{subdomain}" in url:
        if not subdomain.strip():
            raise ValueError("amocrm: пустой subdomain для URL с {subdomain}")
        return url.replace("{subdomain}", subdomain.strip().strip("/"))
    return url


def parse_amocrm_subdomain_from_referer(referer: str | None) -> str | None:
    """
    Параметр referer в callback amo (домен аккаунта), например foo.amocrm.ru или https://bar.kommo.com
    """
    if referer is None or not referer.strip():
        return None
    r = referer.strip()
    for prefix in ("https://", "http://"):
        if r.startswith(prefix):
            r = r[len(prefix) :]
    host = r.split("/")[0]
    for suffix in (".amocrm.ru", ".kommo.com", ".amocrm.com"):
        if host.endswith(suffix) and len(host) > len(suffix):
            return host[: -len(suffix)]
    if "." in host and not host.startswith("."):
        return host.split(".")[0]
    return None


def build_amocrm_auth_query(*, client_id: str, state_token: str) -> str:
    return urlencode(
        {
            "client_id": client_id,
            "state": state_token,
            "mode": "post_message",
        }
    )
