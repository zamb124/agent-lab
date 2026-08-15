"""
Приватность страниц в общем индексе знаний.

Главный регресс-щит выбранной модели: страница по умолчанию попадает в общий
knowledge-namespace компании и находится обычным поиском, а ограниченная —
физически уезжает в служебный слой и не может всплыть у человека без доступа.

Проверка идёт по реальному RAG: индекс читается напрямую из pgvector, а не
через ответы сервиса, иначе тест подтверждал бы только намерение кода.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from apps.wiki.models.domain import WikiVisibility
from apps.wiki.services.rag_index import restricted_namespace_id
from apps.wiki.services.rag_metadata import WIKI_SOURCE_KIND
from core.config import get_settings
from core.db.models.rag import VectorDocument
from tests.wiki.conftest import API_PREFIX, PAGES_URL

pytestmark = pytest.mark.no_test_doubles


@pytest_asyncio.fixture
async def rag_index_session():
    """Прямое чтение индекса RAG.

    Приватность проверяется по содержимому pgvector, а не по ответам сервиса:
    только так видно, что текст действительно уехал из общего пространства.
    """
    rag_url = get_settings().database.rag_url
    assert rag_url, "database.rag_url обязателен для проверки индекса"
    engine = create_async_engine(rag_url, echo=False)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


async def _indexed_namespaces(session_factory, wiki_page_id: str) -> set[str]:
    """Пространства RAG, в которых сейчас лежат чанки страницы."""
    async with session_factory() as session:
        rows = await session.execute(
            select(VectorDocument.namespace_id)
            .where(VectorDocument.document_id == wiki_page_id)
            .distinct()
        )
        return set(rows.scalars().all())


async def _chunk_metadata(session_factory, wiki_page_id: str) -> dict[str, object]:
    async with session_factory() as session:
        row = await session.execute(
            select(VectorDocument.metadata_).where(VectorDocument.document_id == wiki_page_id)
        )
        metadata = row.scalars().first()
    assert metadata is not None, "чанки страницы не найдены в индексе"
    return dict(metadata)


async def test_new_page_lands_in_shared_company_namespace(
    wiki_client, create_page, rag_index_session, wiki_namespace, unique_id
):
    page = await create_page(f"Открытая {unique_id}", markdown="Общедоступный регламент.")

    namespaces = await _indexed_namespaces(rag_index_session, page["wiki_page_id"])

    # Общий knowledge-namespace — тот же, куда пишет Networkle: страницу
    # находит любой rag_search, отдельный инструмент не нужен.
    assert namespaces == {wiki_namespace}


async def test_indexed_chunk_carries_full_metadata(
    create_page, rag_index_session, wiki_namespace, unique_id
):
    page = await create_page(f"Метаданные {unique_id}", markdown="Текст для метаданных.")

    metadata = await _chunk_metadata(rag_index_session, page["wiki_page_id"])

    assert metadata["source_kind"] == WIKI_SOURCE_KIND
    assert metadata["wiki_namespace"] == wiki_namespace
    assert metadata["wiki_page_id"] == page["wiki_page_id"]
    assert metadata["wiki_root_page_id"] == page["wiki_page_id"]
    assert metadata["wiki_visibility"] == WikiVisibility.COMPANY.value
    assert metadata["ttl_seconds"] == 0


async def test_restricting_page_moves_it_out_of_shared_namespace(
    wiki_client, create_page, rag_index_session, wiki_namespace, unique_id
):
    page = await create_page(f"Закрываемая {unique_id}", markdown="Чувствительный текст.")
    page_id = page["wiki_page_id"]
    assert await _indexed_namespaces(rag_index_session, page_id) == {wiki_namespace}

    restricted = await wiki_client.patch(
        f"{PAGES_URL}/{page_id}/access/company-visible",
        json={"company_visible": False},
    )
    assert restricted.status_code == 200, restricted.text

    namespaces = await _indexed_namespaces(rag_index_session, page_id)
    assert namespaces == {restricted_namespace_id(wiki_namespace)}
    assert wiki_namespace not in namespaces


async def test_reopening_page_returns_it_to_shared_namespace(
    wiki_client, create_page, rag_index_session, wiki_namespace, unique_id
):
    page = await create_page(f"Возвращаемая {unique_id}", markdown="Текст возврата.")
    page_id = page["wiki_page_id"]

    _ = await wiki_client.patch(
        f"{PAGES_URL}/{page_id}/access/company-visible",
        json={"company_visible": False},
    )
    assert await _indexed_namespaces(rag_index_session, page_id) == {
        restricted_namespace_id(wiki_namespace)
    }

    reopened = await wiki_client.patch(
        f"{PAGES_URL}/{page_id}/access/company-visible",
        json={"company_visible": True},
    )
    assert reopened.status_code == 200, reopened.text

    assert await _indexed_namespaces(rag_index_session, page_id) == {wiki_namespace}


async def test_new_child_under_restricted_parent_lands_in_restricted_namespace(
    wiki_client, create_page, rag_index_session, wiki_namespace, unique_id
):
    """`company_visible` не каскадирует по существующему поддереву, но новый

    потомок наследует значение родителя в момент создания (см. `WikiService.create_page`).
    """
    parent = await create_page(f"Родитель {unique_id}", markdown="Текст родителя.")

    restricted = await wiki_client.patch(
        f"{PAGES_URL}/{parent['wiki_page_id']}/access/company-visible",
        json={"company_visible": False},
    )
    assert restricted.status_code == 200, restricted.text

    child = await create_page(
        f"Ребёнок {unique_id}",
        markdown="Текст ребёнка.",
        parent_page_id=parent["wiki_page_id"],
    )

    restricted_id = restricted_namespace_id(wiki_namespace)
    assert await _indexed_namespaces(rag_index_session, parent["wiki_page_id"]) == {restricted_id}
    assert await _indexed_namespaces(rag_index_session, child["wiki_page_id"]) == {restricted_id}


async def test_restricting_parent_does_not_move_already_indexed_children(
    wiki_client, create_page, rag_index_session, wiki_namespace, unique_id
):
    """Дети, созданные до ограничения родителя, свой tuple `company` не теряют."""
    parent = await create_page(f"Родитель {unique_id}", markdown="Текст родителя.")
    child = await create_page(
        f"Ребёнок {unique_id}",
        markdown="Текст ребёнка.",
        parent_page_id=parent["wiki_page_id"],
    )

    restricted = await wiki_client.patch(
        f"{PAGES_URL}/{parent['wiki_page_id']}/access/company-visible",
        json={"company_visible": False},
    )
    assert restricted.status_code == 200, restricted.text

    restricted_id = restricted_namespace_id(wiki_namespace)
    assert await _indexed_namespaces(rag_index_session, parent["wiki_page_id"]) == {restricted_id}
    assert await _indexed_namespaces(rag_index_session, child["wiki_page_id"]) == {wiki_namespace}


async def test_moving_page_between_namespaces_reindexes_it(
    wiki_client, create_page, rag_index_session, wiki_namespace, wiki_other_namespace, unique_id
):
    page = await create_page(f"Мигрирующая {unique_id}", markdown="Текст миграции.")
    page_id = page["wiki_page_id"]

    moved = await wiki_client.post(
        f"{PAGES_URL}/{page_id}/move-namespace",
        json={"target_namespace": wiki_other_namespace},
    )
    assert moved.status_code == 200, moved.text

    namespaces = await _indexed_namespaces(rag_index_session, page_id)
    assert namespaces == {wiki_other_namespace}
    assert wiki_namespace not in namespaces


async def test_deleting_page_removes_it_from_index(
    wiki_client, create_page, rag_index_session, unique_id
):
    page = await create_page(f"Удаляемая {unique_id}", markdown="Текст удаления.")
    page_id = page["wiki_page_id"]
    assert await _indexed_namespaces(rag_index_session, page_id)

    assert (await wiki_client.delete(f"{PAGES_URL}/{page_id}")).status_code == 204

    assert await _indexed_namespaces(rag_index_session, page_id) == set()


async def test_updating_page_replaces_indexed_text(
    wiki_client, create_page, rag_index_session, unique_id
):
    page = await create_page(f"Обновляемая {unique_id}", markdown="Старая формулировка.")
    page_id = page["wiki_page_id"]

    updated = await wiki_client.put(
        f"{PAGES_URL}/{page_id}/content", json={"markdown": "Новая формулировка."}
    )
    assert updated.status_code == 200, updated.text

    async with rag_index_session() as session:
        rows = await session.execute(
            select(VectorDocument.content).where(VectorDocument.document_id == page_id)
        )
        contents = " ".join(rows.scalars().all())

    assert "Новая формулировка" in contents
    assert "Старая формулировка" not in contents


async def test_restricted_page_is_hidden_from_colleague_search(
    wiki_client, wiki_client_member, create_page, unique_id
):
    marker = f"закрытыймаркер{unique_id}"
    page = await create_page(f"Секретная {unique_id}", markdown=f"Текст {marker}.")

    visible = await wiki_client_member.post(
        f"{API_PREFIX}/search", json={"query": marker, "mode": "lexical"}
    )
    assert {item["wiki_page_id"] for item in visible.json()["items"]} == {page["wiki_page_id"]}

    _ = await wiki_client.patch(
        f"{PAGES_URL}/{page['wiki_page_id']}/access/company-visible",
        json={"company_visible": False},
    )

    hidden = await wiki_client_member.post(
        f"{API_PREFIX}/search", json={"query": marker, "mode": "lexical"}
    )
    assert hidden.json()["items"] == []


async def test_owner_still_finds_restricted_page(wiki_client, create_page, unique_id):
    marker = f"мойзакрытый{unique_id}"
    page = await create_page(f"Моя закрытая {unique_id}", markdown=f"Текст {marker}.")

    _ = await wiki_client.patch(
        f"{PAGES_URL}/{page['wiki_page_id']}/access/company-visible",
        json={"company_visible": False},
    )

    found = await wiki_client.post(
        f"{API_PREFIX}/search", json={"query": marker, "mode": "lexical"}
    )

    assert {item["wiki_page_id"] for item in found.json()["items"]} == {page["wiki_page_id"]}


async def test_empty_page_is_not_indexed(create_page, rag_index_session, unique_id):
    page = await create_page(f"Пустая {unique_id}")

    assert await _indexed_namespaces(rag_index_session, page["wiki_page_id"]) == set()


async def test_index_has_single_copy_per_page(
    wiki_client, create_page, rag_index_session, unique_id
):
    page = await create_page(f"Единственная {unique_id}", markdown="Первый вариант текста.")
    page_id = page["wiki_page_id"]

    for text in ("Второй вариант.", "Третий вариант."):
        response = await wiki_client.put(
            f"{PAGES_URL}/{page_id}/content", json={"markdown": text}
        )
        assert response.status_code == 200, response.text

    async with rag_index_session() as session:
        total = await session.execute(
            select(func.count())
            .select_from(VectorDocument)
            .where(VectorDocument.document_id == page_id)
        )
        chunks = total.scalar_one()

    # Перезапись не должна оставлять предыдущие версии рядом с актуальной.
    assert chunks == 1
