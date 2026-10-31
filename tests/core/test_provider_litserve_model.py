"""ProviderLitserveModel: desired-state каталог в Postgres (shared).

Реальная БД тестового стека (``make test-up``): seed, tombstone ``deleted``,
статусная машина download/delete, ``to_entry`` round-trip.
"""

from __future__ import annotations

import pytest

from core.config.models import (
    ProviderLitserveSTTModelEntry,
    ProviderLitserveTTSModelEntry,
)
from core.models.provider_litserve_model import (
    ProviderLitserveModel,
    ProviderLitserveModelPair,
)

pytestmark = pytest.mark.timeout(30)


async def _cleanup(api_model_id: str) -> None:
    row = await ProviderLitserveModel.by_api_model_id(api_model_id)
    if row is not None:
        await row.delete()


async def test_upsert_seed_creates_ready_and_is_idempotent(unique_id):
    api_id = f"emb-{unique_id}"
    await _cleanup(api_id)
    try:
        pair = ProviderLitserveModelPair(api_model_id=api_id, hf_model_id="x/y-emb")
        row = await ProviderLitserveModel.upsert_seed(kind="embedding", entry=pair)
        assert row is not None
        assert row.status == "ready"
        assert row.kind == "embedding"
        assert row.hf_model_id == "x/y-emb"

        again = await ProviderLitserveModel.upsert_seed(kind="embedding", entry=pair)
        assert again is not None
        assert again.model_id == row.model_id
    finally:
        await _cleanup(api_id)


async def test_upsert_seed_does_not_resurrect_deleted_tombstone(unique_id):
    api_id = f"tomb-{unique_id}"
    await _cleanup(api_id)
    try:
        pair = ProviderLitserveModelPair(api_model_id=api_id, hf_model_id="x/y")
        row = await ProviderLitserveModel.upsert_seed(kind="embedding", entry=pair)
        assert row is not None
        row = await ProviderLitserveModel.mark_status(
            model_id=row.model_id, status="deleted"
        )
        assert row.status == "deleted"

        skipped = await ProviderLitserveModel.upsert_seed(kind="embedding", entry=pair)
        assert skipped is None
        still = await ProviderLitserveModel.by_api_model_id(api_id)
        assert still is not None and still.status == "deleted"
        ready_ids = {r.api_model_id for r in await ProviderLitserveModel.list_ready_by_created_at_asc()}
        assert api_id not in ready_ids
    finally:
        await _cleanup(api_id)


async def test_create_or_replace_pending_and_download_claim(unique_id):
    api_id = f"dl-{unique_id}"
    await _cleanup(api_id)
    try:
        pair = ProviderLitserveModelPair(api_model_id=api_id, hf_model_id="x/y-dl")
        row = await ProviderLitserveModel.create_or_replace(
            kind="rerank", entry=pair
        )
        assert row.status == "pending"
        ready_ids = {r.api_model_id for r in await ProviderLitserveModel.list_ready_by_created_at_asc()}
        assert api_id not in ready_ids

        claimed = await ProviderLitserveModel.claim_next_pending_download_by_created_at_asc()
        if claimed is not None and claimed.model_id != row.model_id:
            # чужая старая pending-строка тоже может быть забрана — помечаем обратно
            await ProviderLitserveModel.mark_status(
                model_id=claimed.model_id, status="pending"
            )
            claimed = await ProviderLitserveModel.claim_next_pending_download_by_created_at_asc()
        assert claimed is not None and claimed.model_id == row.model_id
        assert claimed.status == "downloading"

        done = await ProviderLitserveModel.mark_ready_if_downloading(
            model_id=row.model_id
        )
        assert done is not None and done.status == "ready"
        ready_ids = {r.api_model_id for r in await ProviderLitserveModel.list_ready_by_created_at_asc()}
        assert api_id in ready_ids
    finally:
        await _cleanup(api_id)


async def test_reset_downloading_to_pending_recovers_queue(unique_id):
    api_id = f"crash-{unique_id}"
    await _cleanup(api_id)
    try:
        pair = ProviderLitserveModelPair(api_model_id=api_id, hf_model_id="x/y-c")
        row = await ProviderLitserveModel.create_or_replace(
            kind="embedding", entry=pair
        )
        row = await ProviderLitserveModel.mark_status(
            model_id=row.model_id, status="downloading"
        )
        moved = await ProviderLitserveModel.reset_downloading_to_pending()
        assert moved >= 1
        after = await ProviderLitserveModel.require(row.model_id)
        assert after.status == "pending"
    finally:
        await _cleanup(api_id)


async def test_deleting_claim_and_tombstone(unique_id):
    api_id = f"del-{unique_id}"
    await _cleanup(api_id)
    try:
        pair = ProviderLitserveModelPair(api_model_id=api_id, hf_model_id="x/y-del")
        row = await ProviderLitserveModel.create_or_replace(
            kind="embedding", entry=pair
        )
        row = await ProviderLitserveModel.mark_status(
            model_id=row.model_id, status="deleting"
        )
        claimed = await ProviderLitserveModel.claim_next_deleting_by_created_at_asc()
        assert claimed is not None
        tombstone = await ProviderLitserveModel.mark_status(
            model_id=claimed.model_id, status="deleted"
        )
        assert tombstone.status == "deleted"
    finally:
        await _cleanup(api_id)


async def test_to_entry_round_trip_typed_speech_params(unique_id):
    api_id = f"stt-{unique_id}"
    await _cleanup(api_id)
    try:
        stt = ProviderLitserveSTTModelEntry(
            api_model_id=api_id,
            hf_model_id="ai-sage/GigaAM-v3",
            revision="e2e_rnnt",
            backend="gigaam",
        )
        row = await ProviderLitserveModel.upsert_seed(kind="stt", entry=stt)
        assert row is not None
        entry = row.to_entry()
        assert isinstance(entry, ProviderLitserveSTTModelEntry)
        assert entry.revision == "e2e_rnnt"
        assert entry.backend == "gigaam"
    finally:
        await _cleanup(api_id)


async def test_to_entry_tts_keeps_synthesis_locale(unique_id):
    api_id = f"tts-{unique_id}"
    await _cleanup(api_id)
    try:
        tts = ProviderLitserveTTSModelEntry(
            api_model_id=api_id,
            hf_model_id="snakers4/silero-models",
            silero_bundle="v5_5_ru",
            voice="xenia",
            sample_rate=24000,
            synthesis_locale="ru",
        )
        row = await ProviderLitserveModel.upsert_seed(kind="tts", entry=tts)
        assert row is not None
        entry = row.to_entry()
        assert isinstance(entry, ProviderLitserveTTSModelEntry)
        assert entry.synthesis_locale == "ru"
        assert entry.voice == "xenia"
    finally:
        await _cleanup(api_id)
