"""
Оркестрация перевекторизации stale chunks `vector_documents` с группировкой по
``company_id``: единый ``execute_reembed_tick`` для CRM/RAG воркеров.

Биллинг: ``BillingService.company_may_incur_embedding_charge`` (без notify_user).
Контекст на каждую компанию: ``build_job_context`` + ``pick_company_billing_user``.
NULL ``company_id`` строки в reembed НЕ попадают (SQL-фильтр на стороне провайдера);
для них существует отдельный maintenance — ``rag_cleanup_orphan_company_chunks_tick``.
"""

from __future__ import annotations

from collections import defaultdict

from core.billing import get_billing_service
from core.config import get_settings
from core.container.base import BaseContainer
from core.context import clear_context, set_context
from core.context.job_context import build_job_context, pick_company_billing_user
from core.db.repositories.company_repository import CompanyRepository
from core.db.repositories.user_repository import UserRepository
from core.logging import get_logger
from core.rag.constants import RAG_IN_PROCESS_PROVIDER_ID
from core.rag.factory import get_rag_provider
from core.rag.models import RAGReembedTickResult
from core.rag.providers.pgvector_provider import PgVectorProvider

logger = get_logger(__name__)


async def execute_reembed_tick(
    *,
    container: BaseContainer,
    channel: str,
    schedule_task_id: str,
) -> RAGReembedTickResult:
    """
    Запускает один тик перевекторизации для воркера.

    Берёт in-process pgvector-провайдер из фабрики, репозитории — из ``container``.
    Возвращает унифицированный dict-результат для TaskIQ.
    """
    if not schedule_task_id or not schedule_task_id.strip():
        raise ValueError("execute_reembed_tick: schedule_task_id обязателен")
    if not channel or not channel.strip():
        raise ValueError("execute_reembed_tick: channel обязателен")

    settings = get_settings()
    reembed_cfg = settings.rag.ttl
    if not reembed_cfg.reembed_enabled:
        return {
            "skipped": True,
            "schedule_task_id": schedule_task_id,
            "reembedded": 0,
            "by_company_written": {},
        }

    provider_raw = get_rag_provider(RAG_IN_PROCESS_PROVIDER_ID)
    if not isinstance(provider_raw, PgVectorProvider):
        raise TypeError("execute_reembed_tick требует pgvector RAG provider")
    provider = provider_raw
    target_model = provider.embedding_model_name()
    batch_size = reembed_cfg.reembed_batch_size

    reembedded, by_company_written = await _run_reembed_round(
        provider=provider,
        company_repository=container.company_repository,
        user_repository=container.user_repository,
        batch_size=batch_size,
        target_embedding_model=target_model,
        schedule_task_id=schedule_task_id,
        channel=channel,
    )

    logger.info(
        "reembed_stale.tick_done",
        schedule_task_id=schedule_task_id,
        target_embedding_model=target_model,
        batch_size=batch_size,
        reembedded=reembedded,
        channel=channel,
    )

    return {
        "skipped": False,
        "schedule_task_id": schedule_task_id,
        "target_embedding_model": target_model,
        "batch_size": batch_size,
        "reembedded": reembedded,
        "by_company_written": by_company_written,
    }


async def _run_reembed_round(
    *,
    provider: PgVectorProvider,
    company_repository: CompanyRepository,
    user_repository: UserRepository,
    batch_size: int,
    target_embedding_model: str,
    schedule_task_id: str,
    channel: str,
) -> tuple[int, dict[str, int]]:
    """Один SELECT batch_size кандидатов + группировка по company_id + embed-write."""
    if batch_size <= 0:
        raise ValueError("_run_reembed_round: batch_size должен быть > 0")

    rows = await provider.fetch_stale_chunks_for_reembed(
        limit=batch_size,
        target_embedding_model=target_embedding_model,
    )
    if not rows:
        return 0, {}

    groups: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for doc_id, content, cid in rows:
        groups[cid].append((doc_id, content))

    billing = get_billing_service()
    embedding_service = provider.embedding_service
    total_written = 0
    by_company_written: dict[str, int] = defaultdict(int)

    for cid in sorted(groups.keys()):
        slice_pairs = groups[cid]
        company = await company_repository.get(cid)
        if company is None:
            logger.warning(
                "reembed_stale.company_missing_skip",
                company_id=cid,
                chunk_count=len(slice_pairs),
            )
            continue

        if not await billing.company_may_incur_embedding_charge(cid):
            logger.info(
                "reembed_stale.skipped_low_balance",
                company_id=cid,
                chunk_count=len(slice_pairs),
            )
            continue

        try:
            bill_user = await pick_company_billing_user(
                company=company,
                user_repository=user_repository,
            )
        except ValueError:
            logger.error(
                "reembed_stale.billing_user_missing_skip",
                company_id=cid,
                chunk_count=len(slice_pairs),
            )
            continue

        tid = f"reembed:{schedule_task_id}:{cid}"
        ctx = build_job_context(
            company=company,
            user=bill_user,
            host="reembed_job",
            trace_id=tid,
            session_id=tid,
            channel=channel,
        )
        set_context(ctx)
        try:
            embeddings = await embedding_service.generate_embeddings(
                [p[1] for p in slice_pairs]
            )
            if len(embeddings) != len(slice_pairs):
                raise ValueError(
                    f"reembed_stale: размер батча embedding {len(embeddings)} "
                    + f"не совпадает с числом чанков {len(slice_pairs)}",
                )
            doc_emb = [(slice_pairs[i][0], embeddings[i]) for i in range(len(slice_pairs))]
            written = await provider.write_reembed_chunk_embeddings(
                doc_emb,
                target_embedding_model,
            )
            total_written += written
            by_company_written[cid] += written
        finally:
            clear_context()

    return total_written, dict(by_company_written)
