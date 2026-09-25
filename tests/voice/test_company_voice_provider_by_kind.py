"""Чтение CompanyVoiceProvider по (company_id, kind)."""

from __future__ import annotations

import pytest

from core.models.voice_models import CompanyVoiceProvider


@pytest.mark.asyncio
async def test_by_kind_matches_company_and_kind(unique_id: str) -> None:
    company_id = f"voice_{unique_id}"
    other_company_id = f"voice_other_{unique_id}"
    created = await CompanyVoiceProvider.upsert_by_kind(
        company_id=company_id,
        kind="stt",
        provider="whisper",
        secrets={"api_key": "secret"},
    )
    _ = await CompanyVoiceProvider.upsert_by_kind(
        company_id=company_id,
        kind="tts",
        provider="piper",
    )

    found = await CompanyVoiceProvider.by_kind(company_id=company_id, kind="stt")
    assert found is not None
    assert found.provider == "whisper"
    assert await CompanyVoiceProvider.by_kind(company_id=other_company_id, kind="stt") is None
    assert await CompanyVoiceProvider.by_kind(company_id=company_id, kind="vad") is None
    with pytest.raises(ValueError, match="company_id cannot be empty"):
        _ = await CompanyVoiceProvider.by_kind(company_id="", kind="stt")

    kept_secrets = await CompanyVoiceProvider.upsert_by_kind(
        company_id=company_id,
        kind="stt",
        provider="faster-whisper",
    )
    assert kept_secrets.company_voice_provider_id == created.company_voice_provider_id
    assert kept_secrets.provider == "faster-whisper"
    assert kept_secrets.secrets == {"api_key": "secret"}
    cleared = await CompanyVoiceProvider.upsert_by_kind(
        company_id=company_id,
        kind="stt",
        provider="faster-whisper",
        secrets=None,
    )
    assert cleared.secrets is None
    assert await CompanyVoiceProvider.by_kind(company_id=other_company_id, kind="stt") is None
    with pytest.raises(ValueError, match="provider cannot be empty"):
        _ = await CompanyVoiceProvider.upsert_by_kind(
            company_id=company_id,
            kind="stt",
            provider="",
        )
