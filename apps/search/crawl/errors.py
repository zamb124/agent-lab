"""Crawl pipeline errors."""

from typing import Literal

import httpx2

from core.clients.service_client import ServiceClientError

CrawlErrorKind = Literal["domain", "platform"]


def crawl_error_kind(exc: BaseException) -> CrawlErrorKind:
    """Кто виноват в фейле fetch: сайт-цель (`domain`) или платформа.

    `domain`: сайт отдал ошибочный статус, недоступен, ушёл в таймаут
    или browser-service классифицировал исход как upstream/rate-limit —
    это исход краула, а не отказ платформы. Всё прочее — `platform`.
    """
    if isinstance(exc, CrawlExtractTooShortError | CrawlNoExtractableContentError):
        return "domain"
    if isinstance(exc, httpx2.HTTPStatusError | httpx2.TransportError):
        return "domain"
    if isinstance(exc, ServiceClientError) and exc.status_code in (429, 502, 504):
        return "domain"
    return "platform"


class CrawlExtractTooShortError(ValueError):
    """Extracted page text is below configured min_extract_chars."""

    url: str

    def __init__(self, url: str) -> None:
        super().__init__(f"extracted text too short for url: {url}")
        self.url = url


class CrawlNoExtractableContentError(ValueError):
    """HTML-страница не содержит извлекаемого текста."""

    url: str

    def __init__(self, url: str) -> None:
        super().__init__(f"no extractable content for url: {url}")
        self.url = url
