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

from core.http import get_httpx_client

_PRAVO_IPS_NETLOC = "ips.pravo.gov.ru"
_LEGISLATION_HASH_RE = re.compile(r"(?i)hash=([a-f0-9]{64})")
_STANDALONE_HASH_RE = re.compile(r"^[a-fA-F0-9]{64}$")
_DEFAULT_TIMEOUT_SECONDS = 60.0
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


class PravoClient:
    """Клиент IPS pravo.gov.ru для каталога и загрузки текстов НПА."""

    def __init__(self, timeout: float = _DEFAULT_TIMEOUT_SECONDS, headers: dict[str, str] | None = None) -> None:
        self._timeout = timeout
        self._headers = {**_DEFAULT_HEADERS, **(headers or {})}

    @staticmethod
    def extract_legislation_document_hash(ref: str) -> str:
        """Извлекает 64-символьный hash документа IPS из URL или строки-hash."""
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
            raise ValueError(f"Ожидается хост {_PRAVO_IPS_NETLOC}, получено: {parsed.netloc}")
        m = _LEGISLATION_HASH_RE.search(s)
        if not m:
            raise ValueError("В URL нет параметра hash= (64 hex) документа IPS")
        return m.group(1).lower()

    @staticmethod
    def legislation_document_api_url(document_hash: str) -> str:
        """Канонический URL API legislation/document."""
        h = document_hash.strip().lower()
        if not _STANDALONE_HASH_RE.match(h):
            raise ValueError("document_hash должен быть 64 hex-символа")
        return f"https://{_PRAVO_IPS_NETLOC}/api/ips/legislation/document?baseid=None&hash={h}"

    @staticmethod
    def rag_document_id(document_hash: str) -> str:
        """Стабильный id документа для RAG (идемпотентная перезапись по IPS hash)."""
        h = PravoClient.extract_legislation_document_hash(document_hash)
        return uuid.uuid5(uuid.NAMESPACE_URL, f"pravo:ips:legislation:{h}").hex

    async def fetch_legislation_document(
        self,
        *,
        document_hash: str | None = None,
        source_url: str | None = None,
    ) -> PravoLegislationDocument:
        """Загружает текст нормативного акта по hash или URL API legislation/document."""
        if document_hash is not None and source_url is not None:
            raise ValueError("Задайте ровно один из аргументов: document_hash или source_url")
        if document_hash is None and source_url is None:
            raise ValueError("Нужен document_hash или source_url")

        if source_url is not None:
            h = self.extract_legislation_document_hash(source_url)
            url = self.legislation_document_api_url(h)
        else:
            h = self.extract_legislation_document_hash(document_hash)
            url = self.legislation_document_api_url(h)

        response = await self._get(url)
        text, title = self._parse_legislation_response_body(
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

    async def search_catalog(self, *, keyword: str, page: int = 1) -> list[PravoCatalogHit]:
        """Ищет документы в каталоге IPS по ключевым словам."""
        url = self._build_catalog_search_url(keyword=keyword, page=page)
        response = await self._get(url)
        return self._parse_catalog_search_html(response.text, page_base_url=url)

    async def _get(self, url: str) -> httpx.Response:
        try:
            async with get_httpx_client(
                timeout=self._timeout,
                follow_redirects=True,
            ) as client:
                response = await client.get(url, headers=self._headers)
        except httpx.RequestError as exc:
            detail = str(exc).strip() or type(exc).__name__
            raise PravoClientError(f"Ошибка сетевого запроса IPS: {detail} ({url})") from exc

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise PravoClientError(f"HTTP {response.status_code} при запросе IPS: {url}") from exc
        return response

    @staticmethod
    def _build_catalog_search_url(*, keyword: str, page: int = 1) -> str:
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

    @staticmethod
    def _html_to_plain_text(html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        text = soup.get_text("\n", strip=True)
        lines = [ln for ln in (ln.strip() for ln in text.splitlines()) if ln]
        return "\n".join(lines)

    @classmethod
    def _text_from_pravo_json(cls, data: Any) -> tuple[str, str | None]:
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
            return cls._html_to_plain_text(html_val), title

        nested = data.get("document")
        if isinstance(nested, dict):
            return cls._text_from_pravo_json(nested)

        nested_data = data.get("data")
        if isinstance(nested_data, dict):
            try:
                return cls._text_from_pravo_json(nested_data)
            except PravoClientError:
                pass

        raise PravoClientError("Не удалось извлечь текст из JSON ответа IPS (нет ожидаемых полей)")

    @classmethod
    def _parse_legislation_response_body(cls, body: str, content_type: str | None) -> tuple[str, str | None]:
        ct = (content_type or "").lower().split(";")[0].strip()
        if "json" in ct or body.lstrip().startswith("{"):
            try:
                data = json.loads(body)
            except json.JSONDecodeError as exc:
                raise PravoClientError("Тело ответа IPS не является корректным JSON") from exc
            return cls._text_from_pravo_json(data)

        is_html = "html" in ct or body.lstrip().lower().startswith("<!doctype") or "<html" in body[:2000].lower()
        if is_html:
            plain = cls._html_to_plain_text(body)
            if not plain:
                raise PravoClientError("Пустой текст после разбора HTML ответа IPS")
            return plain, None

        plain = body.strip()
        if not plain:
            raise PravoClientError("Пустое тело ответа IPS")
        return plain, None

    @classmethod
    def _parse_catalog_search_html(cls, html: str, *, page_base_url: str | None = None) -> list[PravoCatalogHit]:
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
                dh = cls.extract_legislation_document_hash(abs_url)
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
                title = f"document {dh[:8]}..."
            out.append(
                PravoCatalogHit(
                    title=title,
                    url=cls.legislation_document_api_url(dh),
                    document_hash=dh,
                ),
            )
        return out
