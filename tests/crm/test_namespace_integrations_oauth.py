"""CRM namespace integrations OAuth: redirect_uri host-aware (multi-brand)."""

from __future__ import annotations

import json
from urllib.parse import parse_qs, urlparse

import pytest

from core.integrations.oauth_service import OAUTH_STATE_PREFIX


@pytest.mark.parametrize("host,expected_apex", [
    ("linnex.io", "linnex.io"),
    ("linnex.io", "linnex.io"),
])
@pytest.mark.asyncio
async def test_amocrm_authorize_redirect_uri_uses_brand_host(
    crm_di,
    unique_id: str,
    host: str,
    expected_apex: str,
) -> None:
    connector = crm_di.integration_registry.get("amocrm")
    url = await connector.build_authorize_url(
        namespace_name=f"ns_{unique_id}",
        subdomain="testsub",
        return_path="/crm/namespaces",
        company_id="system",
        user_id=f"user_{unique_id}",
        brand_host=host,
    )
    state_token = parse_qs(urlparse(url).query)["state"][0]
    state_raw = await crm_di.oauth_service._storage.get(
        f"{OAUTH_STATE_PREFIX}:{state_token}",
        force_global=True,
    )
    assert isinstance(state_raw, str)
    state_payload = json.loads(state_raw)
    redirect_uri = state_payload["redirect_uri"]
    assert redirect_uri == f"https://{expected_apex}/crm/api/v1/integrations/oauth/callback"
