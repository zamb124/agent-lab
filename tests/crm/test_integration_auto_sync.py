"""Автосинхронизация интеграций namespace: валидация cron и PATCH auto-sync."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from apps.crm.services.integration_auto_sync_service import validate_cron_for_timezone

pytestmark = pytest.mark.timeout(30, func_only=True)


def test_validate_cron_rejects_empty() -> None:
    with pytest.raises(ValueError, match="cron"):
        validate_cron_for_timezone("", "UTC")


def test_validate_cron_rejects_bad_expression() -> None:
    with pytest.raises(ValueError, match="cron"):
        validate_cron_for_timezone("not a cron", "UTC")


def test_validate_cron_rejects_unknown_tz() -> None:
    with pytest.raises(ValueError, match="timezone"):
        validate_cron_for_timezone("0 * * * *", "NotAZone_Xyz")


def test_validate_cron_accepts_standard() -> None:
    validate_cron_for_timezone("0 * * * *", "UTC")
    validate_cron_for_timezone("15 3 * * *", "Europe/Moscow")


@pytest.mark.asyncio
async def test_integration_auto_sync_patch_unknown_namespace_404(
    crm_client: AsyncClient,
    auth_headers_system: dict,
    unique_id: str,
) -> None:
    ns = f"missing_{unique_id}"
    resp = await crm_client.patch(
        f"/crm/api/v1/namespaces/{ns}/integrations/amocrm/auto-sync",
        headers=auth_headers_system,
        json={
            "auto_sync_enabled": False,
        },
    )
    assert resp.status_code == 404, resp.text


@pytest.mark.asyncio
async def test_integration_auto_sync_patch_invalid_cron_422(
    crm_client: AsyncClient,
    auth_headers_system: dict,
    unique_id: str,
) -> None:
    ns = f"g_{unique_id}"
    resp = await crm_client.patch(
        f"/crm/api/v1/namespaces/{ns}/integrations/amocrm/auto-sync",
        headers=auth_headers_system,
        json={
            "auto_sync_enabled": True,
            "auto_sync_cron": "this is invalid",
            "auto_sync_timezone": "UTC",
        },
    )
    assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_integration_auto_sync_patch_enable_without_oauth_422(
    crm_client: AsyncClient,
    auth_headers_system: dict,
    unique_id: str,
) -> None:
    ns = f"g_{unique_id}"
    resp = await crm_client.patch(
        f"/crm/api/v1/namespaces/{ns}/integrations/amocrm/auto-sync",
        headers=auth_headers_system,
        json={
            "auto_sync_enabled": True,
            "auto_sync_cron": "0 * * * *",
            "auto_sync_timezone": "UTC",
        },
    )
    assert resp.status_code == 422, resp.text
    detail = resp.json().get("detail")
    assert isinstance(detail, str)
    assert len(detail) > 0


@pytest.mark.asyncio
async def test_integration_auto_sync_patch_disable_200(
    crm_client: AsyncClient,
    auth_headers_system: dict,
    unique_id: str,
) -> None:
    ns = f"g_{unique_id}"
    resp = await crm_client.patch(
        f"/crm/api/v1/namespaces/{ns}/integrations/amocrm/auto-sync",
        headers=auth_headers_system,
        json={
            "auto_sync_enabled": False,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data.get("provider_id") == "amocrm"
    assert data.get("auto_sync_enabled") is False


@pytest.mark.asyncio
async def test_integration_auto_note_ai_patch_unknown_namespace_404(
    crm_client: AsyncClient,
    auth_headers_system: dict,
    unique_id: str,
) -> None:
    ns = f"missing_ai_{unique_id}"
    resp = await crm_client.patch(
        f"/crm/api/v1/namespaces/{ns}/integrations/amocrm/auto-note-ai-analyze",
        headers=auth_headers_system,
        json={"auto_note_ai_analyze": True},
    )
    assert resp.status_code == 404, resp.text


@pytest.mark.asyncio
async def test_integration_auto_note_ai_patch_200(
    crm_client: AsyncClient,
    auth_headers_system: dict,
    unique_id: str,
) -> None:
    ns = f"g_{unique_id}"
    resp = await crm_client.patch(
        f"/crm/api/v1/namespaces/{ns}/integrations/amocrm/auto-note-ai-analyze",
        headers=auth_headers_system,
        json={"auto_note_ai_analyze": True},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data.get("provider_id") == "amocrm"
    assert data.get("auto_note_ai_analyze") is True
    resp2 = await crm_client.patch(
        f"/crm/api/v1/namespaces/{ns}/integrations/amocrm/auto-note-ai-analyze",
        headers=auth_headers_system,
        json={"auto_note_ai_analyze": False},
    )
    assert resp2.status_code == 200, resp2.text
    assert resp2.json().get("auto_note_ai_analyze") is False
