"""Какие file_category допускаются в RAG-индексацию (FileReader → chunks → embeddings)."""

from __future__ import annotations

from core.documents.viewer.resolver import UNKNOWN_FILE_CATEGORY, resolve_file_category_for_upload
from core.files.types import FileCategory

RAG_INDEXABLE_FILE_CATEGORIES: frozenset[FileCategory] = frozenset(
    {
        FileCategory.TEXT,
        FileCategory.PDF,
        FileCategory.OFFICE_DOC,
        FileCategory.SPREADSHEET,
        FileCategory.PRESENTATION,
        FileCategory.IMAGE,
        FileCategory.AUDIO,
        FileCategory.VIDEO,
        FileCategory.EMAIL,
        FileCategory.EBOOK,
        FileCategory.VIZ,
    }
)

_RAG_INDEXABLE_CATEGORY_VALUES: frozenset[str] = frozenset(
    category.value for category in RAG_INDEXABLE_FILE_CATEGORIES
)


def is_rag_indexable_file_category(file_category: str) -> bool:
    """True если category из whitelist RAG (не archive/signature/unknown и т.п.)."""
    normalized = file_category.strip()
    if normalized == "":
        raise ValueError('file_category is required')
    return normalized in _RAG_INDEXABLE_CATEGORY_VALUES


def rag_file_category_for_document_name(document_name: str) -> str:
    """Категория для имени файла (как при upload binding); иначе unknown."""
    name = document_name.strip()
    if name == "":
        raise ValueError('document_name is required')
    return resolve_file_category_for_upload(name, None)


def effective_rag_file_category(*, file_category: str, document_name: str) -> str:
    """Категория binding; для ``unknown`` — повторный резолв по имени (реестр мог расшириться)."""
    normalized = file_category.strip()
    if normalized == "":
        raise ValueError('file_category is required')
    if normalized == UNKNOWN_FILE_CATEGORY:
        return rag_file_category_for_document_name(document_name)
    return normalized


def is_rag_indexable_document_name(document_name: str) -> bool:
    """True если расширение/имя относится к RAG-indexable категории."""
    return is_rag_indexable_file_category(rag_file_category_for_document_name(document_name))
