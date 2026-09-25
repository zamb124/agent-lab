"""Shared fixtures for RAG tests."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from fastapi import FastAPI

from apps.rag.di import RagDi
from core.di import require_di


@pytest_asyncio.fixture
async def rag_di(rag_app: FastAPI) -> AsyncIterator[RagDi]:
    """Тот же ``RagDi``, что собирает lifespan ``rag_app``."""
    yield require_di(rag_app, RagDi)


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
