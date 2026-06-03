"""Integration-тесты PUT/GET/DELETE per-company voice providers.

Покрытие: model=null для litserve принимается (резолвер подставит default
из provider_litserve.infra), невалидная litserve-модель отвергается 400,
после PUT GET возвращает строку с тем же provider/model.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_company_voice_providers_put_litserve_null_model_accepted(
    frontend_client: AsyncClient,
    auth_headers_system,
):
    """`model=null` для litserve должен сохраняться (deployment-default)."""
    response = await frontend_client.put(
        "/frontend/api/companies/system/voice-providers/stt",
        headers=auth_headers_system,
        json={
            "provider": "litserve",
            "model": None,
            "voice": None,
            "language": None,
            "sample_rate": None,
            "threshold": None,
            "response_format": None,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["kind"] == "stt"
    assert body["provider"] == "litserve"
    assert body["model"] is None

    list_resp = await frontend_client.get(
        "/frontend/api/companies/system/voice-providers",
        headers=auth_headers_system,
    )
    assert list_resp.status_code == 200
    items = list_resp.json()["items"]
    stt_items = [it for it in items if it["kind"] == "stt"]
    assert len(stt_items) == 1
    assert stt_items[0]["provider"] == "litserve"
    assert stt_items[0]["model"] is None


@pytest.mark.asyncio
async def test_company_voice_providers_put_litserve_unknown_model_rejected(
    frontend_client: AsyncClient,
    auth_headers_system,
):
    """litserve с моделью, которой нет в каталоге, → 400."""
    response = await frontend_client.put(
        "/frontend/api/companies/system/voice-providers/stt",
        headers=auth_headers_system,
        json={
            "provider": "litserve",
            "model": "totally-not-a-real-model-id",
            "voice": None,
            "language": None,
            "sample_rate": None,
            "threshold": None,
            "response_format": None,
        },
    )
    assert response.status_code == 400, response.text
    detail = response.json()["detail"]
    assert "Humanitec Voice" in detail
    assert "litserve" not in detail.lower()
    assert "totally-not-a-real-model-id" in detail


@pytest.mark.asyncio
async def test_company_voice_providers_delete_clears_override(
    frontend_client: AsyncClient,
    auth_headers_system,
):
    """DELETE снимает override и в списке не остаётся записи для kind."""
    await frontend_client.put(
        "/frontend/api/companies/system/voice-providers/tts",
        headers=auth_headers_system,
        json={
            "provider": "litserve",
            "model": None,
            "voice": None,
            "language": None,
            "sample_rate": None,
            "threshold": None,
            "response_format": None,
        },
    )

    delete_resp = await frontend_client.delete(
        "/frontend/api/companies/system/voice-providers/tts",
        headers=auth_headers_system,
    )
    assert delete_resp.status_code == 200, delete_resp.text

    list_resp = await frontend_client.get(
        "/frontend/api/companies/system/voice-providers",
        headers=auth_headers_system,
    )
    assert list_resp.status_code == 200
    items = list_resp.json()["items"]
    tts_items = [it for it in items if it["kind"] == "tts"]
    assert tts_items == []


@pytest.mark.asyncio
async def test_company_voice_providers_put_vad_rejected(
    frontend_client: AsyncClient,
    auth_headers_system,
) -> None:
    """PUT для kind=vad — 410, per-company VAD отключён."""
    response = await frontend_client.put(
        "/frontend/api/companies/system/voice-providers/vad",
        headers=auth_headers_system,
        json={
            "provider": "litserve",
            "model": None,
            "voice": None,
            "language": None,
            "sample_rate": None,
            "threshold": None,
            "response_format": None,
        },
    )
    assert response.status_code == 410
    assert "развёртывания" in response.json()["detail"]


@pytest.mark.asyncio
async def test_company_voice_providers_delete_vad_rejected(
    frontend_client: AsyncClient,
    auth_headers_system,
) -> None:
    response = await frontend_client.delete(
        "/frontend/api/companies/system/voice-providers/vad",
        headers=auth_headers_system,
    )
    assert response.status_code == 410
    assert "развёртывания" in response.json()["detail"]
