"""ASGI smoke: OnlyOffice editor JWT auth + model routing на LLM proxy.

Строгий OpenRouter-контракт (seeded ``lara``, MockLLM-only) — ``tests/flows/llm_proxy/contract/``.
Flow ``lara`` для компании токена материализуется ``ensure_company_public_flows``.
"""

from __future__ import annotations

import pytest
from httpx2 import AsyncClient

from apps.flows.di import FlowsDi
from core.ai.providers import LINNEX_LLM_AUTO_MODEL
from core.clients.onlyoffice import sign_onlyoffice_jwt_hs256
from core.office.ai_settings import IMAGE_AUTO_MODEL_ID, LARA_DOCUMENTS_MODEL_ID
from core.office.jwt_secret import resolve_onlyoffice_jwt_secret
from core.office.platform_ai_claims import OFFICE_AI_JWT_CLAIM_KEY, OfficePlatformAiClaims
from core.types import JsonObject
from tests.flows.llm_proxy._helpers import (
    LLM_CHAT_COMPLETIONS_PATH,
    LLM_MODELS_PATH,
    LLM_ONLYOFFICE_PROXY_PATH,
    company_id_from_auth_token,
    ensure_company_public_flows,
    user_id_from_auth_token,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
async def _seed_lara_for_office_proxy(auth_token: str, di: FlowsDi) -> None:
    await ensure_company_public_flows(company_id_from_auth_token(auth_token), di)


def _office_editor_bearer(*, user_id: str, company_id: str) -> str:
    secret = resolve_onlyoffice_jwt_secret()
    claims = OfficePlatformAiClaims(
        company_id=company_id,
        user_id=user_id,
        namespace="docs",
        file_id="file_e2e",
        viewer_scope="catalog",
    )
    payload: JsonObject = {
        "document": {"key": "k"},
        "editorConfig": {"mode": "edit"},
        OFFICE_AI_JWT_CLAIM_KEY: claims.model_dump(mode="json"),
    }
    return sign_onlyoffice_jwt_hs256(payload, secret)


async def test_llm_proxy_office_jwt_lists_models(
    flows_client: AsyncClient,
    auth_token: str,
) -> None:
    bearer = _office_editor_bearer(
        user_id=user_id_from_auth_token(auth_token),
        company_id=company_id_from_auth_token(auth_token),
    )
    response = await flows_client.get(
        LLM_MODELS_PATH,
        headers={"Authorization": f"Bearer {bearer}"},
    )
    assert response.status_code == 200
    model_ids = {item["id"] for item in response.json()["data"] if isinstance(item, dict)}
    assert LINNEX_LLM_AUTO_MODEL in model_ids
    assert IMAGE_AUTO_MODEL_ID in model_ids
    assert LARA_DOCUMENTS_MODEL_ID in model_ids


async def test_llm_proxy_unknown_lara_branch_400(
    flows_client: AsyncClient,
    auth_token: str,
) -> None:
    bearer = _office_editor_bearer(
        user_id=user_id_from_auth_token(auth_token),
        company_id=company_id_from_auth_token(auth_token),
    )
    response = await flows_client.post(
        LLM_CHAT_COMPLETIONS_PATH,
        headers={"Authorization": f"Bearer {bearer}"},
        json={
            "model": "lara:does_not_exist_branch",
            "messages": [{"role": "user", "content": "hi"}],
            "stream": False,
        },
    )
    assert response.status_code == 400


async def test_llm_proxy_invalid_token_401(flows_client: AsyncClient) -> None:
    response = await flows_client.get(
        LLM_MODELS_PATH,
        headers={"Authorization": "Bearer not-a-valid-token"},
    )
    assert response.status_code == 401


async def test_llm_proxy_onlyoffice_unwrap(
    flows_client: AsyncClient,
    auth_token: str,
) -> None:
    bearer = _office_editor_bearer(
        user_id=user_id_from_auth_token(auth_token),
        company_id=company_id_from_auth_token(auth_token),
    )
    response = await flows_client.post(
        LLM_ONLYOFFICE_PROXY_PATH,
        headers={"Authorization": f"Bearer {bearer}"},
        json={
            "target": "http://localhost/flows/api/v1/llm/v1/models",
            "method": "GET",
            "headers": {},
            "data": None,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["object"] == "list"
    model_ids = {item["id"] for item in body["data"] if isinstance(item, dict)}
    assert LARA_DOCUMENTS_MODEL_ID in model_ids
