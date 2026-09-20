"""Prod-like: каталог провайдеров речи — REST и `op_*` один handler."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

import pytest
from httpx import AsyncClient

from apps.flows.src.container import FlowContainer, get_container
from apps.voice.container import VoiceContainer, get_voice_container
from core.context import reset_context, set_context
from core.models.context_models import Context
from core.models.identity_models import User
from core.models.voice_providers_catalog import (
    VoiceProvidersCatalogPayload,
    op_voice_providers_catalog,
)
from tests.fixtures.ai_provider_defaults import make_test_company

pytestmark = [pytest.mark.asyncio, pytest.mark.timeout(60)]


@contextmanager
def _system_scope(system_user_id: str) -> Generator[User]:
    user = User(user_id=system_user_id, name="System")
    token = set_context(
        Context(
            user=user,
            active_company=make_test_company(company_id="system", name="System"),
            channel="api",
            active_namespace="default",
        )
    )
    try:
        yield user
    finally:
        reset_context(token)


async def test_flows_voice_providers_catalog_rest_match_op(
    client: AsyncClient,
    system_user_id: str,
    auth_headers_system: dict[str, str],
) -> None:
    container: FlowContainer = get_container()
    http = await client.get(
        "/flows/api/v1/voice-providers/catalog",
        headers=auth_headers_system,
    )
    assert http.status_code == 200, http.text
    with _system_scope(system_user_id) as user:
        op_result = await op_voice_providers_catalog(
            VoiceProvidersCatalogPayload(),
            user=user,
            container=container,
        )
    assert http.json() == op_result.model_dump(mode="json")


async def test_voice_providers_catalog_rest_match_op(
    voice_client: AsyncClient,
    system_user_id: str,
    auth_headers_system: dict[str, str],
) -> None:
    container: VoiceContainer = get_voice_container()
    http = await voice_client.get(
        "/voice/api/v1/voice-providers/catalog",
        headers=auth_headers_system,
    )
    assert http.status_code == 200, http.text
    with _system_scope(system_user_id) as user:
        op_result = await op_voice_providers_catalog(
            VoiceProvidersCatalogPayload(),
            user=user,
            container=container,
        )
    assert http.json() == op_result.model_dump(mode="json")
