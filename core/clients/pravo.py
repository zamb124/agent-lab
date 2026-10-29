"""
HTTP-клиент для Официального интернет-портала правовой информации (ips.pravo.gov.ru).

Загрузка нормативных текстов по API legislation/document; каталог — POST
/api/ips/legislation/search.json (гибридный поиск, как в веб-интерфейсе IPS).
Разбор HTML legislation при необходимости (BeautifulSoup). Без сервиса browser.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx2
from bs4 import BeautifulSoup

from core.clients.rag_client import RagClient
from core.config import get_settings
from core.http import get_httpx_client
from core.http.client import ProxyStrategy
from core.rag.models import RAGMetadata, RAGMetadataFilter
from core.types import (
    JsonArray,
    JsonObject,
    JsonValue,
    parse_json_object,
    parse_json_value,
    require_json_array,
    require_json_object,
)

_PRAVO_IPS_NETLOC = "ips.pravo.gov.ru"
_PRAVO_IPS_SCHEME = "http"
_IPS_ORIGIN = f"{_PRAVO_IPS_SCHEME}://{_PRAVO_IPS_NETLOC}"
_IPS_SEARCH_JSON_PATH = "/api/ips/legislation/search.json"
_IPS_DEFAULT_BPAS = "c000000000"
_IPS_SEARCH_ALLOWED_LIMITS: frozenset[int] = frozenset({10, 20, 50, 100, 200})
_IPS_SEARCH_BASIC_AUTHORIZATION = "Basic aXBzOm5ld3Bhc3N3b3JkMjAyMA=="
_LEGISLATION_HASH_RE = re.compile(r"(?i)hash=([a-f0-9]{64})")
_STANDALONE_HASH_RE = re.compile(r"^[a-fA-F0-9]{64}$")
_DEFAULT_TIMEOUT_SECONDS = 60.0


def _default_pravo_headers() -> dict[str, str]:
    settings = get_settings()
    primary_domain = settings.primary_platform_domain
    brand = settings.platform_brands[primary_domain]
    apex = primary_domain
    return {
        "User-Agent": (
            f"Mozilla/5.0 (compatible; {brand.platform_name}PravoClient/1.0; +https://{apex}); "
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


def _json_parse_error(field_name: str) -> PravoClientError:
    return PravoClientError(f"Ответ IPS: поле {field_name} не соответствует JSON-контракту")


def _json_object(value: JsonValue | None, field_name: str) -> JsonObject:
    try:
        return require_json_object(value, field_name)
    except ValueError as exc:
        raise _json_parse_error(field_name) from exc


def _json_array(value: JsonValue | None, field_name: str) -> JsonArray:
    try:
        return require_json_array(value, field_name)
    except ValueError as exc:
        raise _json_parse_error(field_name) from exc


def _non_empty_json_string(value: JsonValue | None, field_name: str) -> str:
    if not isinstance(value, str):
        raise PravoClientError(f"IPS response: field {field_name} must be a non-empty string")
    result = value.strip()
    if result == "":
        raise PravoClientError(f"IPS response: field {field_name} must be a non-empty string")
    return result


def _optional_json_string(value: JsonValue | None, field_name: str) -> str | None:
    if value is None:
        return None
    return _non_empty_json_string(value, field_name)


class PravoClient:
    """Клиент IPS pravo.gov.ru для каталога и загрузки текстов НПА."""

    def __init__(self, timeout: float = _DEFAULT_TIMEOUT_SECONDS, headers: dict[str, str] | None = None) -> None:
        extra_headers = headers if headers is not None else {}
        self._timeout: float = timeout
        self._headers: dict[str, str] = {**_default_pravo_headers(), **extra_headers}

    @staticmethod
    def extract_legislation_document_hash(ref: str) -> str:
        """Извлекает 64-символьный hash документа IPS из URL или строки-hash."""
        s = ref.strip()
        if not s:
            raise ValueError("Empty IPS document reference")
        if _STANDALONE_HASH_RE.match(s):
            return s.lower()
        if s.startswith("//"):
            s = f"https:{s}"
        parsed = urlparse(s)
        host = (parsed.netloc or "").lower().split(":")[0]
        if host and host != _PRAVO_IPS_NETLOC:
            raise ValueError(f"Expected host {_PRAVO_IPS_NETLOC}, got: {parsed.netloc}")
        m = _LEGISLATION_HASH_RE.search(s)
        if not m:
            raise ValueError("URL has no hash= (64 hex) IPS document parameter")
        return m.group(1).lower()

    @staticmethod
    def legislation_document_api_url(document_hash: str) -> str:
        """Канонический URL API legislation/document."""
        h = document_hash.strip().lower()
        if not _STANDALONE_HASH_RE.match(h):
            raise ValueError("document_hash must be 64 hex characters")
        return f"{_PRAVO_IPS_SCHEME}://{_PRAVO_IPS_NETLOC}/api/ips/legislation/document?baseid=None&hash={h}"

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
            raise ValueError("Provide exactly one of: document_hash or source_url")
        if document_hash is None and source_url is None:
            raise ValueError("document_hash or source_url is required")

        if source_url is not None:
            h = self.extract_legislation_document_hash(source_url)
            url = self.legislation_document_api_url(h)
        else:
            if document_hash is None:
                raise ValueError("document_hash or source_url is required")
            h = self.extract_legislation_document_hash(document_hash)
            url = self.legislation_document_api_url(h)

        response = await self._get(url)
        content_type = response.headers["content-type"] if "content-type" in response.headers else None
        text, title = self._parse_legislation_response_body(
            response.text,
            content_type,
        )
        if not text:
            raise PravoClientError("IPS response text is empty")
        return PravoLegislationDocument(
            text=text,
            source_url=url,
            document_hash=h,
            title=title,
        )

    async def search_catalog(
        self,
        *,
        keyword: str,
        page: int = 1,
        limit: int = 20,
        bpas: str = _IPS_DEFAULT_BPAS,
    ) -> list[PravoCatalogHit]:
        """Ищет документы в каталоге IPS через POST search.json (гибридный поиск)."""
        if page < 1:
            raise ValueError("page must be >= 1")
        query_lexemes = self._format_hybrid_search_query(keyword)
        page_size = self._coerce_ips_search_limit(limit)
        url = f"{_IPS_ORIGIN}{_IPS_SEARCH_JSON_PATH}"
        headers = {
            **self._headers,
            "Authorization": _IPS_SEARCH_BASIC_AUTHORIZATION,
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "Origin": _IPS_ORIGIN,
        }
        form = {
            "query": query_lexemes,
            "in_all_redactions": "true",
            "case_sensitive": "false",
            "bpas": bpas,
            "page": str(page),
            "sort": "relevance",
            "limit": str(page_size),
        }
        response = await self._post_form(url, headers=headers, data=form)
        try:
            body = parse_json_object(response.text, "pravo.search.response")
        except ValueError as exc:
            raise PravoClientError("IPS search response is not a JSON object") from exc
        return self._hits_from_search_json(body)

    async def document_rag_search(
        self,
        *,
        namespace_id: str,
        collection_id: str,
        document_ref: str,
        query: str,
        limit: int = 5,
        force_refresh: bool = False,
    ) -> JsonObject:
        """Семантический поиск по одному НПА: при отсутствии чанков — fetch IPS → ingest → search."""
        doc_hash = self.extract_legislation_document_hash(document_ref)
        source_url = self.legislation_document_api_url(doc_hash)
        rag_document_id = self.rag_document_id(doc_hash)
        filters: RAGMetadataFilter = {
            "$and": [
                {"collection_id": collection_id},
                {"document_id": rag_document_id},
            ],
        }
        rag = RagClient()

        if not force_refresh:
            raw_first = await rag.search(
                namespace_id,
                query,
                limit=limit,
                filters=filters,
            )
            results_first = require_json_array(raw_first["results"], "rag.search.results")
            if results_first:
                return {
                    "document_ingested": False,
                    "pravo_document_hash": doc_hash,
                    "source_url": source_url,
                    "rag_document_id": rag_document_id,
                    "documents": [
                        {
                            "document_hash": doc_hash,
                            "source_url": source_url,
                            "rag_document_id": rag_document_id,
                            "title": None,
                            "indexed_into_rag_this_call": False,
                        },
                    ],
                    **raw_first,
                }

        doc = await self.fetch_legislation_document(document_hash=doc_hash)
        merged_meta: RAGMetadata = {
            "collection_id": collection_id,
            "pravo_ips": True,
            "pravo_document_hash": doc_hash,
            "pravo_source_url": doc.source_url,
        }
        if doc.title:
            merged_meta["pravo_title"] = doc.title
        document_name = doc.title if doc.title else f"IPS {doc_hash[:16]}…"
        _ = await rag.ingest_text(
            namespace_id,
            doc.text,
            document_name=document_name,
            metadata=merged_meta,
            document_id=rag_document_id,
        )
        raw_second = await rag.search(
            namespace_id,
            query,
            limit=limit,
            filters=filters,
        )
        return {
            "document_ingested": True,
            "pravo_document_hash": doc_hash,
            "source_url": source_url,
            "rag_document_id": rag_document_id,
            "documents": [
                {
                    "document_hash": doc_hash,
                    "source_url": source_url,
                    "rag_document_id": rag_document_id,
                    "title": doc.title,
                    "indexed_into_rag_this_call": True,
                    "text_character_count": len(doc.text),
                },
            ],
            **raw_second,
        }

    async def _get(self, url: str) -> httpx2.Response:
        try:
            async with get_httpx_client(
                timeout=self._timeout,
                strategy=ProxyStrategy.DIRECT_ONLY,
                follow_redirects=True,
            ) as client:
                response = await client.get(url, headers=self._headers)
        except httpx2.RequestError as exc:
            detail = str(exc).strip() or type(exc).__name__
            raise PravoClientError(f"IPS network request error: {detail} ({url})") from exc

        try:
            _ = response.raise_for_status()
        except httpx2.HTTPStatusError as exc:
            raise PravoClientError(f"HTTP {response.status_code} while requesting IPS: {url}") from exc
        return response

    async def _post_form(self, url: str, *, headers: dict[str, str], data: dict[str, str]) -> httpx2.Response:
        try:
            async with get_httpx_client(
                timeout=self._timeout,
                strategy=ProxyStrategy.DIRECT_ONLY,
                follow_redirects=True,
            ) as client:
                response = await client.post(url, headers=headers, data=data)
        except httpx2.RequestError as exc:
            detail = str(exc).strip() or type(exc).__name__
            raise PravoClientError(f"IPS network request error: {detail} ({url})") from exc

        try:
            _ = response.raise_for_status()
        except httpx2.HTTPStatusError as exc:
            raise PravoClientError(f"HTTP {response.status_code} while requesting IPS: {url}") from exc
        return response

    @staticmethod
    def _format_hybrid_search_query(keyword: str) -> str:
        """Строка query для IPS: лексемы через ``&`` (как в форме hybridSearch)."""
        parts = [p for p in keyword.strip().split() if p]
        if not parts:
            raise ValueError("keyword must not be empty")
        return "&".join(parts)

    @staticmethod
    def _coerce_ips_search_limit(limit: int) -> int:
        if limit in _IPS_SEARCH_ALLOWED_LIMITS:
            return limit
        return 20

    @classmethod
    def _hits_from_search_json(cls, body: JsonObject) -> list[PravoCatalogHit]:
        if body.get("status") == 400:
            err = _non_empty_json_string(body.get("error"), "error")
            raise PravoClientError(f"IPS search: {err}")
        docs = body.get("docs")
        if docs is None and "error" in body:
            err = _non_empty_json_string(body.get("error"), "error")
            raise PravoClientError(f"IPS search: {err}")
        docs_array = _json_array(docs, "docs")

        out: list[PravoCatalogHit] = []
        for idx, doc_value in enumerate(docs_array):
            doc = _json_object(doc_value, f"docs[{idx}]")
            raw_hash = doc.get("hash")
            if not isinstance(raw_hash, str) or not _STANDALONE_HASH_RE.match(raw_hash):
                raise PravoClientError(f"IPS search response: docs[{idx}].hash must be 64 hex")
            dh = raw_hash.lower()
            name = _optional_json_string(doc.get("name"), f"docs[{idx}].name")
            adoption = _optional_json_string(doc.get("adoption"), f"docs[{idx}].adoption")
            if name is not None:
                title = name
            elif adoption is not None:
                title = adoption
            else:
                raise PravoClientError(
                    f"IPS search response: docs[{idx}] must contain name or adoption"
                )
            out.append(
                PravoCatalogHit(
                    title=title,
                    url=cls.legislation_document_api_url(dh),
                    document_hash=dh,
                ),
            )
        return out

    @staticmethod
    def _html_to_plain_text(html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        text = soup.get_text("\n", strip=True)
        lines = [ln for ln in (ln.strip() for ln in text.splitlines()) if ln]
        return "\n".join(lines)

    @classmethod
    def _text_from_pravo_json(cls, data: JsonValue) -> tuple[str, str | None]:
        if isinstance(data, str) and data.strip():
            return data.strip(), None
        document = _json_object(data, "document")

        title = _optional_json_string(document.get("title"), "document.title")

        for key in ("text", "content", "body"):
            val = document.get(key)
            if val is not None:
                return _non_empty_json_string(val, f"document.{key}"), title

        html_val = document.get("html")
        if html_val is not None:
            return cls._html_to_plain_text(
                _non_empty_json_string(html_val, "document.html")
            ), title

        nested = document.get("document")
        if nested is not None:
            return cls._text_from_pravo_json(nested)

        nested_data = document.get("data")
        if nested_data is not None:
            return cls._text_from_pravo_json(nested_data)

        raise PravoClientError("Failed to extract text from IPS JSON response (expected fields are missing)")

    @classmethod
    def _parse_legislation_response_body(cls, body: str, content_type: str | None) -> tuple[str, str | None]:
        ct = (content_type or "").lower().split(";")[0].strip()
        if "json" in ct or body.lstrip().startswith("{"):
            try:
                data = parse_json_value(body, "pravo.document.response")
            except ValueError as exc:
                raise PravoClientError("IPS response body is not valid JSON") from exc
            return cls._text_from_pravo_json(data)

        is_html = "html" in ct or body.lstrip().lower().startswith("<!doctype") or "<html" in body[:2000].lower()
        if is_html:
            plain = cls._html_to_plain_text(body)
            if not plain:
                raise PravoClientError("Empty text after parsing IPS HTML response")
            return plain, None

        plain = body.strip()
        if not plain:
            raise PravoClientError("IPS response body is empty")
        return plain, None
