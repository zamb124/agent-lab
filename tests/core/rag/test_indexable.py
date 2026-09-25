"""Unit: whitelist категорий для RAG-индексации."""

from __future__ import annotations

import pytest

from core.documents.viewer.resolver import UNKNOWN_FILE_CATEGORY, resolve_file_category_for_upload
from core.files.types import FileCategory, ext_to_category
from core.rag.indexable import (
    RAG_INDEXABLE_FILE_CATEGORIES,
    effective_rag_file_category,
    is_rag_indexable_document_name,
    is_rag_indexable_file_category,
    rag_file_category_for_document_name,
)


def test_signature_extensions_in_registry() -> None:
    assert ext_to_category(".sig") == FileCategory.SIGNATURE
    assert ext_to_category(".p7s") == FileCategory.SIGNATURE
    assert ext_to_category(".sgn") == FileCategory.SIGNATURE
    assert resolve_file_category_for_upload("contract.pdf.sig", None) == FileCategory.SIGNATURE.value


def test_is_rag_indexable_file_category_whitelist() -> None:
    assert is_rag_indexable_file_category(FileCategory.PDF.value) is True
    assert is_rag_indexable_file_category(FileCategory.TEXT.value) is True
    assert is_rag_indexable_file_category(FileCategory.SIGNATURE.value) is False
    assert is_rag_indexable_file_category(FileCategory.ARCHIVE.value) is False
    assert is_rag_indexable_file_category(UNKNOWN_FILE_CATEGORY) is False
    assert FileCategory.SIGNATURE not in RAG_INDEXABLE_FILE_CATEGORIES
    assert FileCategory.DATA_TABLE not in RAG_INDEXABLE_FILE_CATEGORIES
    assert is_rag_indexable_file_category(FileCategory.DATA_TABLE.value) is False


def test_is_rag_indexable_file_category_rejects_empty() -> None:
    with pytest.raises(ValueError, match="file_category is required"):
        _ = is_rag_indexable_file_category("  ")


def test_rag_file_category_for_document_name() -> None:
    assert rag_file_category_for_document_name("a.pdf") == FileCategory.PDF.value
    assert rag_file_category_for_document_name("a.pdf.sig") == FileCategory.SIGNATURE.value
    assert is_rag_indexable_document_name("notes.md") is True
    assert is_rag_indexable_document_name("seal.p7s") is False


def test_effective_rag_file_category_resolves_legacy_unknown() -> None:
    assert (
        effective_rag_file_category(
            file_category=UNKNOWN_FILE_CATEGORY,
            document_name="Кредитный договор.pdf.sig",
        )
        == FileCategory.SIGNATURE.value
    )
    assert (
        effective_rag_file_category(
            file_category=FileCategory.PDF.value,
            document_name="anything.sig",
        )
        == FileCategory.PDF.value
    )
