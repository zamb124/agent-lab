"""
Интеграция: ``execute_reembed_tick`` и orphan-cleanup на живом стеке
(Postgres+pgvector+AIEmbeddingClient через ``rag_provider_pgvector``).
"""


from __future__ import annotations

from tests.fixtures.auth import set_test_company_member_roles  # noqa: F401
import pytest
from sqlalchemy import select

from core.db.models import VectorDocument
from core.models.identity_models import Company, User
from core.rag.reembed_stale_documents import _run_reembed_round, execute_reembed_tick


async def _seed_solvent_company(frontend_container, *, cid: str, balance: float = 50.0) -> str:
    """Создаёт пользователя и компанию с этим пользователем как owner. Возвращает user_id."""
    uid = f"u_{cid}"
    await frontend_container.user_repository.set(
        User(user_id=uid, name="Owner", companies={cid: ["owner"]})
    )
    await frontend_container.company_repository.set(
        Company(
            company_id=cid,
            name=cid,
            owner_user_id=uid,
            members={uid: ["owner"]},
            balance=balance,
        )
    )
    return uid


async def _insert_stale_chunk(
    session_factory,
    *,
    chunk_id: str,
    namespace_id: str,
    company_id: str | None,
    content: str,
) -> None:
    async with session_factory() as session:
        session.add(
            VectorDocument(
                id=chunk_id,
                namespace_id=namespace_id,
                company_id=company_id,
                document_id=f"doc_{chunk_id}",
                document_name=f"{chunk_id}.txt",
                content=content,
                embedding=None,
                embedding_model=None,
                chunk_index=0,
                total_chunks=1,
            )
        )
        await session.commit()


async def _chunk_state(session_factory, chunk_id: str) -> tuple[str | None, bool, bool]:
    """Возвращает ``(embedding_model, has_embedding, exists)``."""
    async with session_factory() as session:
        row = (
            await session.execute(
                select(VectorDocument).where(VectorDocument.id == chunk_id)
            )
        ).scalar_one_or_none()
    if row is None:
        return None, False, False
    return row.embedding_model, row.embedding is not None, True


async def _run_rounds_until_chunk_embedded(
    *,
    frontend_container,
    provider,
    chunk_id: str,
    target: str,
    schedule_task_id: str,
) -> None:
    """Гоняет reembed-раунды до эмбеддинга собственного чанка.

    Раунд глобальный (batch по всем stale-чанкам shared таблицы): параллельный
    воркер может заэмбеддить наш чанк раньше нас — written нашего раунда тогда 0.
    Parallel-safe контракт: сходимость состояния собственного чанка.
    """
    sf = provider._session_factory
    for _ in range(20):
        model, has_emb, exists = await _chunk_state(sf, chunk_id)
        assert exists is True
        if model == target and has_emb:
            return
        _, _ = await _run_reembed_round(
            provider=provider,
            company_repository=frontend_container.company_repository,
            user_repository=frontend_container.user_repository,
            batch_size=2000,
            target_embedding_model=target,
            schedule_task_id=schedule_task_id,
            channel="test_worker",
        )
    model, has_emb, _ = await _chunk_state(sf, chunk_id)
    raise AssertionError(
        f"chunk {chunk_id} not reembedded after 20 rounds: model={model}, has_embedding={has_emb}"
    )


@pytest.mark.asyncio
async def test_run_reembed_round_embeds_chunk_for_solvent_company(
    frontend_container, rag_provider_pgvector, unique_id
) -> None:
    cid = f"co_reembed_ok_{unique_id}"
    chunk_id = f"reembed_ok_chunk_{unique_id}"
    ns = f"ns_reembed_ok_{unique_id}"
    await _seed_solvent_company(frontend_container, cid=cid, balance=50.0)
    sf = rag_provider_pgvector._session_factory
    await _insert_stale_chunk(
        sf, chunk_id=chunk_id, namespace_id=ns, company_id=cid, content="reembed me",
    )
    target = rag_provider_pgvector.embedding_model_name()

    await _run_rounds_until_chunk_embedded(
        frontend_container=frontend_container,
        provider=rag_provider_pgvector,
        chunk_id=chunk_id,
        target=target,
        schedule_task_id=f"t_{unique_id}",
    )
    model, has_emb, exists = await _chunk_state(sf, chunk_id)
    assert exists is True
    assert model == target
    assert has_emb is True


@pytest.mark.asyncio
async def test_run_reembed_round_skips_low_balance_company(
    frontend_container, rag_provider_pgvector, unique_id
) -> None:
    cid = f"co_reembed_zero_{unique_id}"
    chunk_id = f"reembed_zero_chunk_{unique_id}"
    ns = f"ns_reembed_zero_{unique_id}"
    await _seed_solvent_company(frontend_container, cid=cid, balance=0.0)
    sf = rag_provider_pgvector._session_factory
    await _insert_stale_chunk(
        sf, chunk_id=chunk_id, namespace_id=ns, company_id=cid, content="stays stale",
    )
    target = rag_provider_pgvector.embedding_model_name()
    _, _ = await _run_reembed_round(
        provider=rag_provider_pgvector,
        company_repository=frontend_container.company_repository,
        user_repository=frontend_container.user_repository,
        batch_size=2000,
        target_embedding_model=target,
        schedule_task_id=f"t_{unique_id}",
        channel="test_worker",
    )
    model, _, exists = await _chunk_state(sf, chunk_id)
    assert exists is True
    assert model is None


@pytest.mark.asyncio
async def test_run_reembed_round_skips_company_without_billing_owner(
    frontend_container, rag_provider_pgvector, unique_id
) -> None:
    cid = f"co_reembed_no_owner_{unique_id}"
    chunk_id = f"reembed_no_owner_chunk_{unique_id}"
    ns = f"ns_reembed_no_owner_{unique_id}"
    await frontend_container.company_repository.set(
        Company(
            company_id=cid,
            name="NoOwner",
            owner_user_id=None,
            members={f"u_admin_{unique_id}": ["admin"]},
            balance=20.0,
        )
    )
    sf = rag_provider_pgvector._session_factory
    await _insert_stale_chunk(
        sf, chunk_id=chunk_id, namespace_id=ns, company_id=cid, content="no owner stale",
    )
    target = rag_provider_pgvector.embedding_model_name()
    _, _ = await _run_reembed_round(
        provider=rag_provider_pgvector,
        company_repository=frontend_container.company_repository,
        user_repository=frontend_container.user_repository,
        batch_size=2000,
        target_embedding_model=target,
        schedule_task_id=f"t_{unique_id}",
        channel="test_worker",
    )
    model, _, exists = await _chunk_state(sf, chunk_id)
    assert exists is True
    assert model is None


@pytest.mark.asyncio
async def test_run_reembed_round_skips_chunk_with_missing_company(
    frontend_container, rag_provider_pgvector, unique_id
) -> None:
    """Чанк указывает на несуществующую компанию — skip, чанк остаётся stale."""
    cid_missing = f"co_missing_{unique_id}"
    chunk_id = f"missing_co_chunk_{unique_id}"
    ns = f"ns_missing_co_{unique_id}"
    sf = rag_provider_pgvector._session_factory
    await _insert_stale_chunk(
        sf, chunk_id=chunk_id, namespace_id=ns, company_id=cid_missing,
        content="dangling company stale",
    )
    target = rag_provider_pgvector.embedding_model_name()
    _, _ = await _run_reembed_round(
        provider=rag_provider_pgvector,
        company_repository=frontend_container.company_repository,
        user_repository=frontend_container.user_repository,
        batch_size=2000,
        target_embedding_model=target,
        schedule_task_id=f"t_{unique_id}",
        channel="test_worker",
    )
    model, _, exists = await _chunk_state(sf, chunk_id)
    assert exists is True
    assert model is None


@pytest.mark.asyncio
async def test_run_reembed_round_one_bad_company_does_not_fail_others(
    frontend_container, rag_provider_pgvector, unique_id
) -> None:
    """Группа без owner не валит обработку соседних компаний."""
    cid_bad = f"co_mix_bad_{unique_id}"
    cid_good = f"co_mix_good_{unique_id}"
    ns = f"ns_mix_{unique_id}"
    await frontend_container.company_repository.set(
        Company(
            company_id=cid_bad, name="MixBad", owner_user_id=None,
            members={f"u_admin_{unique_id}": ["admin"]}, balance=20.0,
        )
    )
    await _seed_solvent_company(frontend_container, cid=cid_good, balance=20.0)
    sf = rag_provider_pgvector._session_factory
    chunk_bad = f"mix_bad_chunk_{unique_id}"
    chunk_good = f"mix_good_chunk_{unique_id}"
    await _insert_stale_chunk(sf, chunk_id=chunk_bad, namespace_id=ns,
                              company_id=cid_bad, content="bad group")
    await _insert_stale_chunk(sf, chunk_id=chunk_good, namespace_id=ns,
                              company_id=cid_good, content="good group")
    target = rag_provider_pgvector.embedding_model_name()
    await _run_rounds_until_chunk_embedded(
        frontend_container=frontend_container,
        provider=rag_provider_pgvector,
        chunk_id=chunk_good,
        target=target,
        schedule_task_id=f"t_{unique_id}",
    )
    bad_model, _, _ = await _chunk_state(sf, chunk_bad)
    good_model, good_has_emb, _ = await _chunk_state(sf, chunk_good)
    assert bad_model is None
    assert good_model == target
    assert good_has_emb is True


@pytest.mark.asyncio
async def test_execute_reembed_tick_requires_schedule_task_id(frontend_container) -> None:
    with pytest.raises(ValueError, match="schedule_task_id"):
        await execute_reembed_tick(
            container=frontend_container, channel="t", schedule_task_id="  ",
        )
    with pytest.raises(ValueError, match="schedule_task_id"):
        await execute_reembed_tick(
            container=frontend_container, channel="t", schedule_task_id="",
        )


@pytest.mark.asyncio
async def test_execute_reembed_tick_requires_channel(frontend_container) -> None:
    with pytest.raises(ValueError, match="channel"):
        await execute_reembed_tick(
            container=frontend_container, channel="  ", schedule_task_id="t",
        )


@pytest.mark.asyncio
async def test_execute_reembed_tick_full_run_embeds_chunk(
    frontend_container, rag_provider_pgvector, unique_id
) -> None:
    """End-to-end: execute_reembed_tick через настоящий контейнер и фабрику pgvector."""
    from core.config import get_settings
    from core.rag.constants import RAG_IN_PROCESS_PROVIDER_ID
    from core.rag.factory import get_rag_provider
    from core.rag.providers.pgvector_provider import PgVectorProvider

    settings = get_settings()
    assert settings.rag.ttl.reembed_enabled is True, (
        "reembed_enabled must be true; set RAG__TTL__REEMBED_ENABLED=true"
    )

    cid = f"co_e2e_{unique_id}"
    chunk_id = f"e2e_chunk_{unique_id}"
    ns = f"ns_e2e_{unique_id}"
    await _seed_solvent_company(frontend_container, cid=cid, balance=50.0)

    company = await frontend_container.company_repository.get(cid)
    assert company is not None
    assert company.balance > 0

    sf = rag_provider_pgvector._session_factory
    await _insert_stale_chunk(
        sf, chunk_id=chunk_id, namespace_id=ns, company_id=cid, content="e2e content",
    )
    stale_model, stale_has_emb, stale_exists = await _chunk_state(sf, chunk_id)
    assert stale_exists is True
    assert stale_has_emb is False
    assert stale_model is None

    provider_raw = get_rag_provider(RAG_IN_PROCESS_PROVIDER_ID)
    assert isinstance(provider_raw, PgVectorProvider)
    assert provider_raw.embedding_model_name() == rag_provider_pgvector.embedding_model_name()

    # Тик глобальный: параллельный воркер может заэмбеддить наш чанк раньше —
    # тогда reembedded нашего тика 0. Parallel-safe контракт: сходимость
    # состояния собственного чанка за ограниченное число тиков.
    target = rag_provider_pgvector.embedding_model_name()
    for _ in range(20):
        result = await execute_reembed_tick(
            container=frontend_container,
            channel="test_worker_e2e",
            schedule_task_id=f"e2e_{unique_id}",
        )
        if result["skipped"]:
            pytest.fail(f"execute_reembed_tick skipped unexpectedly: {result}")
        assert isinstance(result.get("by_company_written"), dict)
        assert result.get("target_embedding_model") == target
        model, has_emb, _ = await _chunk_state(sf, chunk_id)
        if model == target and has_emb:
            break
    model, has_emb, _ = await _chunk_state(sf, chunk_id)
    assert model == target
    assert has_emb is True


@pytest.mark.asyncio
async def test_orphan_cleanup_tick_removes_orphan_company_chunks(
    rag_provider_pgvector, unique_id
) -> None:
    from apps.rag_worker.tasks.maintenance_tasks import rag_cleanup_orphan_company_chunks_tick

    sf = rag_provider_pgvector._session_factory
    chunk_null = f"orphan_null_{unique_id}"
    chunk_empty = f"orphan_empty_{unique_id}"
    ns = f"ns_orphan_e2e_{unique_id}"
    await _insert_stale_chunk(sf, chunk_id=chunk_null, namespace_id=ns,
                              company_id=None, content="null")
    await _insert_stale_chunk(sf, chunk_id=chunk_empty, namespace_id=ns,
                              company_id="", content="empty")

    # Cleanup глобальный: чужой параллельный batch может удалить наши строки
    # раньше нас (deleted нашего тика тогда < 2). Сходимость собственных строк.
    for _ in range(50):
        result = await rag_cleanup_orphan_company_chunks_tick(
            schedule_task_id=f"orph_{unique_id}",
        )
        assert result["skipped"] is False
        _, _, exists_null = await _chunk_state(sf, chunk_null)
        _, _, exists_empty = await _chunk_state(sf, chunk_empty)
        if not exists_null and not exists_empty:
            break

    _, _, exists_null = await _chunk_state(sf, chunk_null)
    _, _, exists_empty = await _chunk_state(sf, chunk_empty)
    assert exists_null is False
    assert exists_empty is False


@pytest.mark.asyncio
async def test_orphan_cleanup_tick_requires_schedule_task_id() -> None:
    from apps.rag_worker.tasks.maintenance_tasks import rag_cleanup_orphan_company_chunks_tick

    with pytest.raises(ValueError, match="schedule_task_id"):
        await rag_cleanup_orphan_company_chunks_tick(schedule_task_id="  ")
