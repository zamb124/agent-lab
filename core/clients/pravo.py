"""
HTTP-клиент для Официального интернет-портала правовой информации (ips.pravo.gov.ru).

Загрузка нормативных текстов по API legislation/document и разбор HTML-страниц
расширенного поиска (BeautifulSoup). Без использования сервиса browser.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, unquote, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

_PRAVO_IPS_NETLOC = "ips.pravo.gov.ru"
_LEGISLATION_HASH_RE = re.compile(r"(?i)hash=([a-f0-9]{64})")
_STANDALONE_HASH_RE = re.compile(r"^[a-fA-F0-9]{64}$")
_DEFAULT_TIMEOUT = httpx.Timeout(60.0, connect=20.0)
_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; HumanitecPravoClient/1.0; +https://humanitec.ru); "
        "lang=ru"
    ),
    "Accept": "application/json, text/html, text/plain;q=0.9, */*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9",
}


class PravoClientError(Exception):
    """Ошибка запроса или разбора ответа IPS."""


@dataclass(frozen=True)
class PravoLegislationDocument:
    """Текст нормативного акта, полученный с ips.pravo.gov.ru."""

    text: str
    source_url: str
    document_hash: str
    title: str | None


@dataclass(frozen=True)
class PravoCatalogHit:
    """Элемент списка выдачи расширенного поиска (ссылка на документ)."""

    title: str
    url: str
    document_hash: str


def extract_legislation_document_hash(ref: str) -> str:
    """
    Извлекает 64-символьный hash документа IPS из полного URL или из строки-hash.
    """
    s = ref.strip()
    if not s:
        raise ValueError("Пустая ссылка на документ IPS")
    if _STANDALONE_HASH_RE.match(s):
        return s.lower()
    if s.startswith("//"):
        s = f"https:{s}"
    parsed = urlparse(s)
    host = (parsed.netloc or "").lower().split(":")[0]
    if host and host != _PRAVO_IPS_NETLOC:
        raise ValueError(
            f"Ожидается хост {_PRAVO_IPS_NETLOC}, получено: {parsed.netloc}",
        )
    m = _LEGISLATION_HASH_RE.search(s)
    if not m:
        raise ValueError("В URL нет параметра hash= (64 hex) документа IPS")
    return m.group(1).lower()


def legislation_document_api_url(document_hash: str) -> str:
    """Канонический HTTPS URL API ведомственной подсистемы legislation/document."""
    h = document_hash.strip().lower()
    if not _STANDALONE_HASH_RE.match(h):
        raise ValueError("document_hash должен быть 64 hex-символа")
    return f"https://{_PRAVO_IPS_NETLOC}/api/ips/legislation/document?baseid=None&hash={h}"


def rag_document_id_for_pravo_legislation(document_hash: str) -> str:
    """Стабильный document_id для RAG (идемпотентная перезапись по hash IPS)."""
    h = extract_legislation_document_hash(document_hash)
    return uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"pravo:ips:legislation:{h}",
    ).hex


def build_catalog_search_url(*, keyword: str, page: int = 1) -> str:
    """
    URL расширенного поиска IPS (search[oneof_lexemes]).

    Разметка страницы может меняться; при пустой выдаче возможен SPA-скелет без данных.
    """
    if page < 1:
        raise ValueError("page должен быть >= 1")
    kw = keyword.strip()
    if not kw:
        raise ValueError("keyword не должен быть пустым")
    enc = quote(kw, safe="")
    return (
        f"https://{_PRAVO_IPS_NETLOC}/?"
        f"advanced_search%5Bactual%5D=1&page={page}&search%5Boneof_lexemes%5D={enc}"
    )


def _html_to_plain_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text("\n", strip=True)
    lines = [ln for ln in (ln.strip() for ln in text.splitlines()) if ln]
    return "\n".join(lines)


def _text_from_pravo_json(data: Any) -> tuple[str, str | None]:
    if isinstance(data, str) and data.strip():
        return data.strip(), None
    if not isinstance(data, dict):
        raise PravoClientError("Ответ IPS JSON: ожидался объект или строка с текстом")

    title = data.get("title")
    if title is not None and not isinstance(title, str):
        title = None
    elif isinstance(title, str):
        title = title.strip() or None

    for key in ("text", "content", "body"):
        val = data.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip(), title

    html_val = data.get("html")
    if isinstance(html_val, str) and html_val.strip():
        return _html_to_plain_text(html_val), title

    nested = data.get("document")
    if isinstance(nested, dict):
        return _text_from_pravo_json(nested)

    nested_data = data.get("data")
    if isinstance(nested_data, dict):
        try:
            return _text_from_pravo_json(nested_data)
        except PravoClientError:
            pass

    raise PravoClientError(
        "Не удалось извлечь текст из JSON ответа IPS (нет ожидаемых полей)",
    )


def _parse_legislation_response_body(body: str, content_type: str | None) -> tuple[str, str | None]:
    ct = (content_type or "").lower().split(";")[0].strip()
    if "json" in ct or body.lstrip().startswith("{"):
        try:
            data = json.loads(body)
        except json.JSONDecodeError as exc:
            raise PravoClientError("Тело ответа IPS не является корректным JSON") from exc
        return _text_from_pravo_json(data)

    if "html" in ct or body.lstrip().lower().startswith("<!doctype") or "<html" in body[:2000].lower():
        plain = _html_to_plain_text(body)
        if not plain:
            raise PravoClientError("Пустой текст после разбора HTML ответа IPS")
        return plain, None

    plain = body.strip()
    if not plain:
        raise PravoClientError("Пустое тело ответа IPS")
    return plain, None


async def fetch_legislation_document(
    *,
    document_hash: str | None = None,
    source_url: str | None = None,
    headers: dict[str, str] | None = None,
) -> PravoLegislationDocument:
    """
    Загружает текст нормативного акта по hash или по полному URL API legislation/document.
    """
    if document_hash is not None and source_url is not None:
        raise ValueError("Задайте ровно один из аргументов: document_hash или source_url")
    if document_hash is None and source_url is None:
        raise ValueError("Нужен document_hash или source_url")

    if source_url is not None:
        h = extract_legislation_document_hash(source_url)
        url = legislation_document_api_url(h)
    else:
        h = extract_legislation_document_hash(document_hash)
        url = legislation_document_api_url(h)

    hdrs = {**_DEFAULT_HEADERS, **(headers or {})}
    async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT, follow_redirects=True) as client:
        response = await client.get(url, headers=hdrs)
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise PravoClientError(
            f"HTTP {response.status_code} при загрузке документа IPS: {url}",
        ) from exc

    text, title = _parse_legislation_response_body(
        response.text,
        response.headers.get("content-type"),
    )
    if not text:
        raise PravoClientError("Из ответа IPS получен пустой текст")
    return PravoLegislationDocument(
        text=text,
        source_url=url,
        document_hash=h,
        title=title,
    )


def parse_catalog_search_html(html: str, *, page_base_url: str | None = None) -> list[PravoCatalogHit]:
    """
    Разбирает HTML выдачи расширенного поиска IPS: ссылки на /api/ips/legislation/document.

    page_base_url — для относительных href (например URL страницы поиска).
    """
    soup = BeautifulSoup(html, "html.parser")
    base = page_base_url or f"https://{_PRAVO_IPS_NETLOC}/"
    seen: set[str] = set()
    out: list[PravoCatalogHit] = []

    for a in soup.find_all("a", href=True):
        href_raw = a.get("href")
        if not isinstance(href_raw, str) or "legislation/document" not in href_raw:
            continue
        abs_url = urljoin(base, href_raw)
        try:
            dh = extract_legislation_document_hash(abs_url)
        except ValueError:
            m = _LEGISLATION_HASH_RE.search(unquote(abs_url))
            if not m:
                continue
            dh = m.group(1).lower()
        if dh in seen:
            continue
        seen.add(dh)
        title = a.get_text(" ", strip=True)
        if not title:
            title = f"document {dh[:8]}…"
        canon = legislation_document_api_url(dh)
        out.append(PravoCatalogHit(title=title, url=canon, document_hash=dh))

    return out


async def fetch_catalog_search_html(
    *,
    keyword: str,
    page: int = 1,
    headers: dict[str, str] | None = None,
) -> str:
    """Сырой HTML страницы расширенного поиска (для последующего parse_catalog_search_html)."""
    url = build_catalog_search_url(keyword=keyword, page=page)
    hdrs = {**_DEFAULT_HEADERS, **(headers or {})}
    async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT, follow_redirects=True) as client:
        response = await client.get(url, headers=hdrs)
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise PravoClientError(
            f"HTTP {response.status_code} при поиске IPS: {url}",
        ) from exc
    return response.text
