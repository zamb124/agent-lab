"""Shared fixtures for RAG tests."""

from __future__ import annotations

import uuid

import pytest

pytest_plugins = ["tests.core.files.conftest"]


@pytest.fixture
def rag_company_id() -> str:
    """Изоляция строк vector_documents по company_id в рамках теста."""
    return f"test_co_{uuid.uuid4().hex[:8]}"


@pytest.fixture
def ns_name() -> str:
    """Уникальное имя namespace для каждого теста."""
    return f"test_ns_{uuid.uuid4().hex[:8]}"


@pytest.fixture
def ns_name_2() -> str:
    return f"test_ns_{uuid.uuid4().hex[:8]}"
