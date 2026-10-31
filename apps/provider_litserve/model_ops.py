"""Долговременный цикл операций над весами моделей provider_litserve.

Замена ``BackgroundTasks``: желаемое состояние живёт в ``provider_litserve_models``
(Postgres), под разбирает очередь статусов — ``pending`` → download →
``ready``/``failed``; ``deleting`` → очистка HF-кэша → ``deleted``. Операции
переживают REST-запрос и рестарт процесса: при старте недокачанные
``downloading``-строки возвращаются в ``pending``.

Скачивание и очистка кэша блокирующие — выполняются в ``asyncio.to_thread``.
Цикл один на под (строки claim-ятся через compare-and-set по статусу).
"""

from __future__ import annotations

import asyncio

from huggingface_hub import scan_cache_dir, snapshot_download

from core.config.models import ProviderLitserveInfraConfig
from core.logging import get_logger
from core.models.provider_litserve_model import ProviderLitserveModel

logger = get_logger(__name__)

OPS_POLL_SECONDS: float = 2.0


def _purge_hf_cache(hf_model_id: str) -> None:
    """Удалить все revision-ы HF-репозитория из локального кэша (blocking)."""
    cache_info = scan_cache_dir()
    revisions = [
        revision.commit_hash
        # huggingface_hub 2.x: pyright-стабы не экспонируют repos/revisions
        for repo in cache_info.repos  # pyright: ignore[reportAttributeAccessIssue]
        if repo.repo_id == hf_model_id
        for revision in repo.revisions
    ]
    if not revisions:
        return
    strategy = cache_info.delete_revisions(*revisions)
    _ = strategy.execute()


async def _process_download(cfg: ProviderLitserveInfraConfig, row: ProviderLitserveModel) -> None:
    logger.info(
        "provider_litserve.model_download_started",
        model_id=row.model_id,
        api_model_id=row.api_model_id,
        hf_model_id=row.hf_model_id,
    )
    revision_raw = row.params.get("revision")
    revision = revision_raw if isinstance(revision_raw, str) and revision_raw else None
    try:
        _ = await asyncio.to_thread(
            snapshot_download,
            repo_id=row.hf_model_id,
            revision=revision,  # pyright: ignore[reportCallIssue] — стабы huggingface_hub 2.x не экспонируют revision
            token=cfg.hf_token,
            local_files_only=False,
        )
    except Exception as exc:
        _ = await ProviderLitserveModel.mark_status(
            model_id=row.model_id,
            status="failed",
            error=str(exc),
        )
        logger.info(
            "provider_litserve.model_download_failed",
            model_id=row.model_id,
            api_model_id=row.api_model_id,
            error=str(exc),
        )
        return
    finished = await ProviderLitserveModel.mark_ready_if_downloading(model_id=row.model_id)
    if finished is not None:
        logger.info(
            "provider_litserve.model_ready",
            model_id=row.model_id,
            api_model_id=row.api_model_id,
        )


async def _process_delete(row: ProviderLitserveModel) -> None:
    logger.info(
        "provider_litserve.model_delete_started",
        model_id=row.model_id,
        api_model_id=row.api_model_id,
        hf_model_id=row.hf_model_id,
    )
    try:
        await asyncio.to_thread(_purge_hf_cache, row.hf_model_id)
    except Exception as exc:
        _ = await ProviderLitserveModel.mark_status(
            model_id=row.model_id,
            status="failed",
            error=str(exc),
        )
        logger.info(
            "provider_litserve.model_delete_failed",
            model_id=row.model_id,
            api_model_id=row.api_model_id,
            error=str(exc),
        )
        return
    _ = await ProviderLitserveModel.mark_status(
        model_id=row.model_id,
        status="deleted",
        error=None,
    )
    logger.info(
        "provider_litserve.model_deleted",
        model_id=row.model_id,
        api_model_id=row.api_model_id,
    )


async def _process_once(cfg: ProviderLitserveInfraConfig) -> bool:
    """Один шаг очереди. ``True`` — работа была, сразу следующий шаг без сна."""
    download = await ProviderLitserveModel.claim_next_pending_download_by_created_at_asc()
    if download is not None:
        await _process_download(cfg, download)
        return True
    deleting = await ProviderLitserveModel.claim_next_deleting_by_created_at_asc()
    if deleting is not None:
        await _process_delete(deleting)
        return True
    return False


async def run_model_ops_loop(cfg: ProviderLitserveInfraConfig) -> None:
    """Бесконечный цикл очереди операций (отменяется при shutdown пода)."""
    recovered = await ProviderLitserveModel.reset_downloading_to_pending()
    if recovered:
        logger.info(
            "provider_litserve.model_ops_recovered_downloads",
            recovered=recovered,
        )
    while True:
        try:
            did_work = await _process_once(cfg)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.info("provider_litserve.model_ops_loop_error", error=str(exc))
            did_work = False
        if not did_work:
            await asyncio.sleep(OPS_POLL_SECONDS)
