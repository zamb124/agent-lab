"""
Интеграция: ``execute_reembed_tick`` и orphan-cleanup на живом стеке
(Postgres+pgvector+AIEmbeddingClient через ``rag_provider_pgvector``).
"""


from __future__ import annotations

from datetime import datetime, timezone

import pytest
from oxyde import execute_raw

from core.models.identity_models import Company, User
from core.rag.reembed_stale_documents import _run_reembed_round, execute_reembed_tick
from core.types import require_json_object
from tests.fixtures.auth import set_test_company_member_roles  # noqa: F401
from tests.fixtures.billing import make_test_billing_service


async def _seed_solvent_company(frontend_di, *, cid: str, balance: float = 50.0) -> str:
    """Создаёт пользователя и компанию с этим пользователем как owner. Возвращает user_id."""
    uid = f"u_{cid}"
    await User.set(
        User(user_id=uid, name="Owner", companies={cid: ["owner"]})
    )
    await Company.set(
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
    *,
    chunk_id: str,
    namespace_id: str,
    company_id: str | None,
    content: str,
) -> None:
    now = datetime.now(timezone.utc)
    _ = await execute_raw(
        """
        INSERT INTO vector_documents (
            id, namespace_id, company_id, document_id, document_name, content,
            chunk_index, total_chunks, metadata, created_at, updated_at
        ) VALUES ($1, $2, $3, $4, $5, $6, 0, 1, '{}'::jsonb, $7, $7)
        """,
        [
            chunk_id,
            namespace_id,
            company_id,
            f"doc_{chunk_id}",
            f"{chunk_id}.txt",
            content,
            now,
        ],
        using="rag",
    )


async def _chunk_state(chunk_id: str) -> tuple[str | None, bool, bool]:
    """Возвращает ``(embedding_model, has_embedding, exists)``."""
    rows = await execute_raw(
        """
        SELECT embedding_model, embedding IS NOT NULL AS has_embedding
        FROM vector_documents
        WHERE id = $1
        """,
        [chunk_id],
        using="rag",
    )
    if not rows:
        return None, False, False
    parsed = require_json_object(rows[0], "stale_chunk")
    embedding_model = parsed["embedding_model"]
    has_embedding = parsed["has_embedding"]
    if embedding_model is not None and not isinstance(embedding_model, str):
        raise TypeError("embedding_model must be a string")
    if not isinstance(has_embedding, bool):
        raise TypeError("has_embedding must be a boolean")
    return embedding_model, has_embedding, True


async def _run_rounds_until_chunk_embedded(
    *,
    frontend_di,
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
    for _ in range(20):
        model, has_emb, exists = await _chunk_state(chunk_id)
        assert exists is True
        if model == target and has_emb:
            return
        _, _ = await _run_reembed_round(
            provider=provider,
            batch_size=2000,
            target_embedding_model=target,
            schedule_task_id=schedule_task_id,
            channel="test_worker",
            billing_service=make_test_billing_service(balance_enforcement_enabled=True),
        )
    model, has_emb, _ = await _chunk_state(chunk_id)
    raise AssertionError(
        f"chunk {chunk_id} not reembedded after 20 rounds: model={model}, has_embedding={has_emb}"
    )


@pytest.mark.asyncio
async def test_run_reembed_round_embeds_chunk_for_solvent_company(
    frontend_di, rag_provider_pgvector, unique_id
) -> None:
    cid = f"co_reembed_ok_{unique_id}"
    chunk_id = f"reembed_ok_chunk_{unique_id}"
    ns = f"ns_reembed_ok_{unique_id}"
    await _seed_solvent_company(frontend_di, cid=cid, balance=50.0)
    await _insert_stale_chunk(
        chunk_id=chunk_id, namespace_id=ns, company_id=cid, content="reembed me",
    )
    target = rag_provider_pgvector.embedding_model_name()

    await _run_rounds_until_chunk_embedded(
        frontend_di=frontend_di,
        provider=rag_provider_pgvector,
        chunk_id=chunk_id,
        target=target,
        schedule_task_id=f"t_{unique_id}",
    )
    model, has_emb, exists = await _chunk_state(chunk_id)
    assert exists is True
    assert model == target
    assert has_emb is True


@pytest.mark.asyncio
async def test_run_reembed_round_skips_low_balance_company(
    frontend_di, rag_provider_pgvector, unique_id
) -> None:
    cid = f"co_reembed_zero_{unique_id}"
    chunk_id = f"reembed_zero_chunk_{unique_id}"
    ns = f"ns_reembed_zero_{unique_id}"
    await _seed_solvent_company(frontend_di, cid=cid, balance=0.0)
    await _insert_stale_chunk(
        chunk_id=chunk_id, namespace_id=ns, company_id=cid, content="stays stale",
    )
    target = rag_provider_pgvector.embedding_model_name()
    _, _ = await _run_reembed_round(
        provider=rag_provider_pgvector,
        batch_size=2000,
        target_embedding_model=target,
        schedule_task_id=f"t_{unique_id}",
        channel="test_worker",
            billing_service=make_test_billing_service(balance_enforcement_enabled=True),
        )
    model, _, exists = await _chunk_state(chunk_id)
    assert exists is True
    assert model is None


@pytest.mark.asyncio
async def test_run_reembed_round_skips_company_without_billing_owner(
    frontend_di, rag_provider_pgvector, unique_id
) -> None:
    cid = f"co_reembed_no_owner_{unique_id}"
    chunk_id = f"reembed_no_owner_chunk_{unique_id}"
    ns = f"ns_reembed_no_owner_{unique_id}"
    await Company.set(
        Company(
            company_id=cid,
            name="NoOwner",
            owner_user_id=None,
            members={f"u_admin_{unique_id}": ["admin"]},
            balance=20.0,
        )
    )
    await _insert_stale_chunk(
        chunk_id=chunk_id, namespace_id=ns, company_id=cid, content="no owner stale",
    )
    target = rag_provider_pgvector.embedding_model_name()
    _, _ = await _run_reembed_round(
        provider=rag_provider_pgvector,
        batch_size=2000,
        target_embedding_model=target,
        schedule_task_id=f"t_{unique_id}",
        channel="test_worker",
            billing_service=make_test_billing_service(balance_enforcement_enabled=True),
        )
    model, _, exists = await _chunk_state(chunk_id)
    assert exists is True
    assert model is None


@pytest.mark.asyncio
async def test_run_reembed_round_skips_chunk_with_missing_company(
    frontend_di, rag_provider_pgvector, unique_id
) -> None:
    """Чанк указывает на несуществующую компанию — skip, чанк остаётся stale."""
    cid_missing = f"co_missing_{unique_id}"
    chunk_id = f"missing_co_chunk_{unique_id}"
    ns = f"ns_missing_co_{unique_id}"
    await _insert_stale_chunk(
        chunk_id=chunk_id, namespace_id=ns, company_id=cid_missing,
        content="dangling company stale",
    )
    target = rag_provider_pgvector.embedding_model_name()
    _, _ = await _run_reembed_round(
        provider=rag_provider_pgvector,
        batch_size=2000,
        target_embedding_model=target,
        schedule_task_id=f"t_{unique_id}",
        channel="test_worker",
            billing_service=make_test_billing_service(balance_enforcement_enabled=True),
        )
    model, _, exists = await _chunk_state(chunk_id)
    assert exists is True
    assert model is None


@pytest.mark.asyncio
async def test_run_reembed_round_one_bad_company_does_not_fail_others(
    frontend_di, rag_provider_pgvector, unique_id
) -> None:
    """Группа без owner не валит обработку соседних компаний."""
    cid_bad = f"co_mix_bad_{unique_id}"
    cid_good = f"co_mix_good_{unique_id}"
    ns = f"ns_mix_{unique_id}"
    await Company.set(
        Company(
            company_id=cid_bad, name="MixBad", owner_user_id=None,
            members={f"u_admin_{unique_id}": ["admin"]}, balance=20.0,
        )
    )
    await _seed_solvent_company(frontend_di, cid=cid_good, balance=20.0)
    chunk_bad = f"mix_bad_chunk_{unique_id}"
    chunk_good = f"mix_good_chunk_{unique_id}"
    await _insert_stale_chunk(chunk_id=chunk_bad, namespace_id=ns,
                              company_id=cid_bad, content="bad group")
    await _insert_stale_chunk(chunk_id=chunk_good, namespace_id=ns,
                              company_id=cid_good, content="good group")
    target = rag_provider_pgvector.embedding_model_name()
    await _run_rounds_until_chunk_embedded(
        frontend_di=frontend_di,
        provider=rag_provider_pgvector,
        chunk_id=chunk_good,
        target=target,
        schedule_task_id=f"t_{unique_id}",
    )
    bad_model, _, _ = await _chunk_state(chunk_bad)
    good_model, good_has_emb, _ = await _chunk_state(chunk_good)
    assert bad_model is None
    assert good_model == target
    assert good_has_emb is True


@pytest.mark.asyncio
async def test_execute_reembed_tick_requires_schedule_task_id(frontend_di) -> None:
    with pytest.raises(ValueError, match="schedule_task_id"):
        await execute_reembed_tick(
            channel="t", schedule_task_id="  ",
            billing_service=make_test_billing_service(),
        )
    with pytest.raises(ValueError, match="schedule_task_id"):
        await execute_reembed_tick(
            channel="t", schedule_task_id="",
            billing_service=make_test_billing_service(),
        )


@pytest.mark.asyncio
async def test_execute_reembed_tick_requires_channel(frontend_di) -> None:
    with pytest.raises(ValueError, match="channel"):
        await execute_reembed_tick(
            channel="  ", schedule_task_id="t",
            billing_service=make_test_billing_service(),
        )


@pytest.mark.asyncio
async def test_execute_reembed_tick_full_run_embeds_chunk(
    frontend_di, rag_provider_pgvector, unique_id
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
    await _seed_solvent_company(frontend_di, cid=cid, balance=50.0)

    company = await Company.get(cid)
    assert company is not None
    assert company.balance > 0

    await _insert_stale_chunk(
        chunk_id=chunk_id, namespace_id=ns, company_id=cid, content="e2e content",
    )
    stale_model, stale_has_emb, stale_exists = await _chunk_state(chunk_id)
    assert stale_exists is True
    assert stale_has_emb is False
    assert stale_model is None

    provider_raw = get_rag_provider(RAG_IN_PROCESS_PROVIDER_ID, billing_service=make_test_billing_service())
    assert isinstance(provider_raw, PgVectorProvider)
    assert provider_raw.embedding_model_name() == rag_provider_pgvector.embedding_model_name()

    # Тик глобальный: параллельный воркер может заэмбеддить наш чанк раньше —
    # тогда reembedded нашего тика 0. Parallel-safe контракт: сходимость
    # состояния собственного чанка за ограниченное число тиков.
    target = rag_provider_pgvector.embedding_model_name()
    for _ in range(20):
        result = await execute_reembed_tick(
            channel="test_worker_e2e",
            schedule_task_id=f"e2e_{unique_id}",
            billing_service=make_test_billing_service(),
        )
        if result["skipped"]:
            pytest.fail(f"execute_reembed_tick skipped unexpectedly: {result}")
        assert isinstance(result.get("by_company_written"), dict)
        assert result.get("target_embedding_model") == target
        model, has_emb, _ = await _chunk_state(chunk_id)
        if model == target and has_emb:
            break
    model, has_emb, _ = await _chunk_state(chunk_id)
    assert model == target
    assert has_emb is True


@pytest.mark.asyncio
async def test_orphan_cleanup_tick_removes_orphan_company_chunks(
    rag_provider_pgvector, unique_id, rag_worker_di
) -> None:
    from apps.rag.tasks.maintenance_tasks import rag_cleanup_orphan_company_chunks_tick

    chunk_null = f"orphan_null_{unique_id}"
    chunk_empty = f"orphan_empty_{unique_id}"
    ns = f"ns_orphan_e2e_{unique_id}"
    await _insert_stale_chunk(chunk_id=chunk_null, namespace_id=ns,
                              company_id=None, content="null")
    await _insert_stale_chunk(chunk_id=chunk_empty, namespace_id=ns,
                              company_id="", content="empty")

    # Cleanup глобальный: чужой параллельный batch может удалить наши строки
    # раньше нас (deleted нашего тика тогда < 2). Сходимость собственных строк.
    for _ in range(50):
        result = await rag_cleanup_orphan_company_chunks_tick(
            schedule_task_id=f"orph_{unique_id}",
            di=rag_worker_di,
        )
        assert result["skipped"] is False
        _, _, exists_null = await _chunk_state(chunk_null)
        _, _, exists_empty = await _chunk_state(chunk_empty)
        if not exists_null and not exists_empty:
            break

    _, _, exists_null = await _chunk_state(chunk_null)
    _, _, exists_empty = await _chunk_state(chunk_empty)
    assert exists_null is False
    assert exists_empty is False


@pytest.mark.asyncio
async def test_orphan_cleanup_tick_requires_schedule_task_id(rag_worker_di) -> None:
    from apps.rag.tasks.maintenance_tasks import rag_cleanup_orphan_company_chunks_tick

    with pytest.raises(ValueError, match="schedule_task_id"):
        await rag_cleanup_orphan_company_chunks_tick(schedule_task_id="  ", di=rag_worker_di)
    with pytest.raises(ValueError, match="schedule_task_id"):
        await rag_cleanup_orphan_company_chunks_tick(schedule_task_id="", di=rag_worker_di)
