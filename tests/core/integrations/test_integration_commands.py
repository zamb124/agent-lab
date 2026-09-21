"""Prod-like: integrations credentials — REST и `op_*` один handler."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient

from apps.flows.src.container import FlowContainer, get_container
from core.config import get_settings
from core.context import reset_context, set_context
from core.integrations.models import (
    IntegrationCredential,
    IntegrationCredentialRefPayload,
    IntegrationProvider,
)
from core.integrations.operations import (
    op_integrations_credentials_list,
    op_integrations_credentials_remove,
    op_integrations_workspace_company_get,
)
from core.integrations.repository import IntegrationCredentialRepository
from core.models.context_models import Context
from core.models.identity_models import User
from core.websocket import EmptyPayload, WsCommandError
from tests.fixtures.ai_provider_defaults import make_test_company

pytestmark = [pytest.mark.asyncio, pytest.mark.timeout(60)]


@pytest.fixture()
def credential_repository() -> IntegrationCredentialRepository:
    shared_url = get_settings().database.shared_url
    if shared_url is None:
        raise RuntimeError("DATABASE__SHARED_URL обязателен для тестов integrations")
    return IntegrationCredentialRepository(db_url=shared_url)


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


async def _insert_credential(
    repo: IntegrationCredentialRepository,
    *,
    credential_id: str,
    user_id: str,
    service: str,
) -> None:
    now = datetime.now(timezone.utc)
    await repo.upsert(
        IntegrationCredential(
            credential_id=credential_id,
            company_id="system",
            user_id=user_id,
            provider=IntegrationProvider.GOOGLE,
            service=service,
            access_token=f"token-{credential_id}",
            refresh_token=f"refresh-{credential_id}",
            created_at=now,
            updated_at=now,
        )
    )


async def test_credentials_list_rest_match_op(
    flows_client: AsyncClient,
    auth_headers_system: dict[str, str],
    credential_repository: IntegrationCredentialRepository,
    system_user_id: str,
    unique_id: str,
) -> None:
    container: FlowContainer = get_container()
    service = f"svc-cmd-{unique_id}"
    await _insert_credential(
        credential_repository,
        credential_id=f"cred-cmd-{unique_id}",
        user_id=system_user_id,
        service=service,
    )
    http = await flows_client.get(
        "/flows/api/v1/integrations/credentials",
        headers=auth_headers_system,
    )
    assert http.status_code == 200, http.text
    with _system_scope(system_user_id) as user:
        op_result = await op_integrations_credentials_list(
            EmptyPayload(),
            user=user,
            container=container,
        )
    assert op_result.model_dump(mode="json") == http.json()
    services = {item.service for item in op_result.items}
    assert service in services
    for item in op_result.items:
        assert "access_token" not in item.model_dump()


async def test_credentials_remove_missing_rest_match_op(
    flows_client: AsyncClient,
    auth_headers_system: dict[str, str],
    system_user_id: str,
) -> None:
    container: FlowContainer = get_container()
    http = await flows_client.delete(
        "/flows/api/v1/integrations/credentials/google/missing-cmd",
        headers=auth_headers_system,
    )
    assert http.status_code == 404, http.text
    assert http.json()["error_code"] == "not_found"
    with _system_scope(system_user_id) as user:
        with pytest.raises(WsCommandError) as exc_info:
            _ = await op_integrations_credentials_remove(
                IntegrationCredentialRefPayload(provider="google", service="missing-cmd"),
                user=user,
                container=container,
            )
    assert exc_info.value.code == "not_found"


async def test_workspace_company_get_rest_match_op(
    flows_client: AsyncClient,
    auth_headers_system: dict[str, str],
    system_user_id: str,
) -> None:
    container: FlowContainer = get_container()
    http = await flows_client.get(
        "/flows/api/v1/integrations/credentials/google/workspace/company",
        headers=auth_headers_system,
    )
    assert http.status_code == 200, http.text
    with _system_scope(system_user_id) as user:
        op_result = await op_integrations_workspace_company_get(
            EmptyPayload(),
            user=user,
            container=container,
        )
    assert op_result.model_dump(mode="json") == http.json()
