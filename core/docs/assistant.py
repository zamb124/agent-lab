"""Общие константы и хелперы публичного ассистента документации."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from pydantic import Field

from core.models import StrictBaseModel
from core.types import JsonObject, JsonValue

DOCS_ASSISTANT_EMBED_ID = "docs_assistant"
DOCS_ASSISTANT_FLOW_ID = "lara"
DOCS_ASSISTANT_BRANCH_ID = "docs"
DOCS_ASSISTANT_SESSION_ISSUER = "frontend.docs_assistant"

DOCS_RAG_NAMESPACE_ID = "humanitec_documentation"
DOCS_RAG_NAMESPACE_DESCRIPTION = "Humanitec public documentation for Lara docs assistant"
DOCS_COLLECTION_RU = "documentation-ru"
DOCS_COLLECTION_EN = "documentation-en"

DOCS_MANIFEST_STORAGE_KEY = "docs_assistant_manifest:v1"


class DocsRagManifestPage(StrictBaseModel):
    """Сохранённые метаданные RAG-документа для одной страницы документации."""

    content_hash: str
    provider_document_id: str
    language: str
    source_url: str
    page_title: str
    updated_at: datetime


class DocsRagManifest(StrictBaseModel):
    """Сохранённый манифест RAG-индекса публичного ассистента документации."""

    build_hash: str | None = None
    updated_at: datetime | None = None
    namespace_id: str = DOCS_RAG_NAMESPACE_ID
    pages: dict[str, DocsRagManifestPage] = Field(default_factory=dict)


@dataclass(frozen=True)
class DocsPage:
    language: str
    collection_id: str
    title: str
    source_url: str
    page_path: str
    content: str
    content_hash: str

    @property
    def document_id(self) -> str:
        digest = hashlib.sha1(self.source_url.encode("utf-8")).hexdigest()[:20]
        return f"docs:{self.language}:{digest}"

    @property
    def text_for_rag(self) -> str:
        return "\n\n".join(
            part
            for part in (
                f"# {self.title}",
                f"Source: {self.source_url}",
                self.content.strip(),
            )
            if part.strip()
        )

    def metadata(self, *, build_hash: str) -> JsonObject:
        return {
            "collection_id": self.collection_id,
            "docs_language": self.language,
            "source_url": self.source_url,
            "page_url": self.source_url,
            "page_title": self.title,
            "page_path": self.page_path,
            "content_hash": self.content_hash,
            "build_hash": build_hash,
            "canonical_document_id": self.document_id,
        }


def docs_collection_for_language(language: str) -> str:
    return DOCS_COLLECTION_EN if normalize_docs_language(language) == "en" else DOCS_COLLECTION_RU


def normalize_docs_language(*values: JsonValue | None) -> str:
    for raw in values:
        if raw is None:
            continue
        text = str(raw).strip().lower()
        if not text:
            continue
        if text.startswith("en") or "/documentation/en/" in text or "/frontend/documentation/en/" in text:
            return "en"
        if text.startswith("ru"):
            return "ru"
    return "ru"


def docs_page_path_from_url(source_url: str, language: str) -> str:
    parsed = urlparse(source_url)
    path = parsed.path or ""
    prefix = "/documentation/en/" if normalize_docs_language(language) == "en" else "/documentation/"
    if path.startswith(prefix):
        return path[len(prefix) :].strip("/")
    if path.startswith("/documentation/"):
        rest = path[len("/documentation/") :].strip("/")
        if rest.startswith("en/"):
            return rest[3:].strip("/")
        return rest
    return path.strip("/")


def docs_url_for_page(
    *,
    page_path: str,
    language: str,
    current_page_url: str | None,
    fallback_url: str,
) -> str:
    parsed_current = urlparse((current_page_url or "").strip())
    if parsed_current.scheme in {"http", "https"} and parsed_current.netloc:
        origin = f"{parsed_current.scheme}://{parsed_current.netloc}"
        current_path = parsed_current.path or ""
        root = "/frontend/documentation/" if current_path.startswith("/frontend/documentation") else "/documentation/"
        if normalize_docs_language(language) == "en":
            root = f"{root.rstrip('/')}/en/"
        clean_path = page_path.strip("/")
        return f"{origin}{root}{clean_path + '/' if clean_path else ''}"
    return fallback_url


def plain_text_excerpt(markdown: str, *, limit: int = 220) -> str:
    text = re.sub(r"```.*?```", " ", markdown, flags=re.S)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"!\[[^\]]*]\([^)]+\)", " ", text)
    text = re.sub(r"\[([^\]]+)]\([^)]+\)", r"\1", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"^[#>*\-\s]+", "", text, flags=re.M)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def docs_search_card_blocks(results: list[JsonObject], *, language: str) -> list[JsonObject]:
    is_en = normalize_docs_language(language) == "en"
    subtitle = "Open this documentation page" if is_en else "Открыть страницу документации"
    blocks: list[JsonObject] = []
    for item in results[:5]:
        title = str(item.get("title") or item.get("document_name") or "").strip()
        url = str(item.get("url") or "").strip()
        if not title or not url:
            continue
        content = str(item.get("content") or "").strip()
        blocks.append(
            {
                "type": "card",
                "title": title,
                "subtitle": subtitle,
                "description": plain_text_excerpt(content, limit=180),
                "url": url,
            }
        )
    return blocks


def parse_llms_full(text: str, *, language: str) -> list[DocsPage]:
    lang = normalize_docs_language(language)
    collection_id = docs_collection_for_language(lang)
    lines = text.splitlines()

    def next_nonempty_index(start: int) -> int | None:
        for index in range(start, len(lines)):
            if lines[index].strip():
                return index
        return None

    def is_page_header(index: int) -> bool:
        if not lines[index].startswith("## "):
            return False
        source_index = next_nonempty_index(index + 1)
        if source_index is None:
            return False
        return lines[source_index].strip().startswith("Source:")

    header_indexes = [index for index in range(len(lines)) if is_page_header(index)]
    pages: list[DocsPage] = []
    for position, header_index in enumerate(header_indexes):
        source_index = next_nonempty_index(header_index + 1)
        if source_index is None:
            continue
        title = lines[header_index][3:].strip()
        source_url = lines[source_index].strip()[len("Source:") :].strip()
        if not title or not source_url:
            continue
        content_start = source_index + 1
        while content_start < len(lines) and not lines[content_start].strip():
            content_start += 1
        content_end = header_indexes[position + 1] if position + 1 < len(header_indexes) else len(lines)
        content = "\n".join(lines[content_start:content_end]).strip()
        raw_hash = "\n".join((lang, title, source_url, content))
        content_hash = hashlib.sha256(raw_hash.encode("utf-8")).hexdigest()
        pages.append(
            DocsPage(
                language=lang,
                collection_id=collection_id,
                title=title,
                source_url=source_url,
                page_path=docs_page_path_from_url(source_url, lang),
                content=content,
                content_hash=content_hash,
            )
        )
    return pages


def load_llms_full_pages(paths_by_language: dict[str, Path]) -> list[DocsPage]:
    pages: list[DocsPage] = []
    for language, path in paths_by_language.items():
        if not path.is_file():
            continue
        pages.extend(parse_llms_full(path.read_text(encoding="utf-8"), language=language))
    return pages


def docs_build_hash(pages: list[DocsPage]) -> str:
    raw = "\n".join(f"{page.document_id}:{page.content_hash}" for page in sorted(pages, key=lambda p: p.document_id))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
