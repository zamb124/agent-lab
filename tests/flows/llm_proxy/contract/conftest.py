"""Contract tests for OpenAI-compatible LLM proxy (real HTTP + MockLLM)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import pytest
import pytest_asyncio

from core.clients.onlyoffice import sign_onlyoffice_jwt_hs256
from core.office.jwt_secret import resolve_onlyoffice_jwt_secret
from core.office.platform_ai_claims import OFFICE_AI_JWT_CLAIM_KEY, OfficePlatformAiClaims
from core.types import JsonObject
from tests.fixtures.e2e_scope import bind_static_e2e_scope
from tests.flows.llm_proxy._helpers import company_id_from_auth_token, user_id_from_auth_token


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if not str(item.nodeid).startswith("tests/flows/llm_proxy/contract/"):
            continue
        item.add_marker(pytest.mark.timeout(120))


@pytest.fixture(autouse=True)
def platform_test_scope() -> Any:
    with bind_static_e2e_scope() as scope:
        yield scope


@pytest_asyncio.fixture
async def mock_llm_with_queue(
    mock_llm_redis: Callable[[list[Any]], Awaitable[None]],
) -> Callable[[list[Any]], Awaitable[None]]:
    async def _factory(responses: list[Any]) -> None:
        await mock_llm_redis(responses)

    return _factory


def office_editor_bearer(*, auth_token: str) -> str:
    secret = resolve_onlyoffice_jwt_secret()
    claims = OfficePlatformAiClaims(
        company_id=company_id_from_auth_token(auth_token),
        user_id=user_id_from_auth_token(auth_token),
        namespace="docs",
        file_id="file_contract",
        viewer_scope="catalog",
    )
    payload: JsonObject = {
        "document": {"key": "k"},
        "editorConfig": {"mode": "edit"},
        OFFICE_AI_JWT_CLAIM_KEY: claims.model_dump(mode="json"),
    }
    return sign_onlyoffice_jwt_hs256(payload, secret)
