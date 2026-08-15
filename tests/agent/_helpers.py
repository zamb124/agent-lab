"""
HTTP helpers для HumanitecAgent тестов.
"""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

from httpx import AsyncClient

from apps.agent.models import AgentDeviceRecord
from apps.agent.service import (
    DEVICE_KEY_PREFIX,
    TUNNEL_ONLINE_PREFIX,
    _audit_storage_key,
)
from apps.flows.src.container import get_container as get_flows_container
from apps.flows.src.services.flows_loader import FlowsLoader, load_tools_to_db
from core.context import Context, clear_context, set_context
from core.models.i18n_models import Language
from core.utils.tokens import get_token_service

_FLOWS_ROOT = Path(__file__).resolve().parents[2] / "apps" / "flows"
_FLOWS_REGISTRY_PATH = _FLOWS_ROOT / "registry.yaml"
_FLOWS_BUNDLES_DIR = _FLOWS_ROOT / "bundles"

AGENT_API_PREFIX = "/frontend/api/agent"
AGENT_TEST_PUBLIC_ORIGIN = "http://system.lvh.me:9004"
FRONTEND_HTTP_BASE = AGENT_TEST_PUBLIC_ORIGIN
FRONTEND_TUNNEL_POD_ID = "frontend-e2e-pod"
FLOWS_HTTP_BASE = "http://127.0.0.1:9001"
PLATFORM_MCP_PATH = "/flows/api/v1/agent/platform-mcp"
LLM_MODELS_PATH = "/flows/api/v1/agent/llm/v1/models"
LLM_CHAT_COMPLETIONS_PATH = "/flows/api/v1/agent/llm/v1/chat/completions"
LLM_IMAGES_GENERATIONS_PATH = "/flows/api/v1/agent/llm/v1/images/generations"
LLM_ONLYOFFICE_PROXY_PATH = "/flows/api/v1/agent/llm/v1/proxy"


async def agent_base_url_from_token(auth_token: str, frontend_container) -> str:
    company_id = company_id_from_auth_token(auth_token)
    company = await frontend_container.company_repository.get(company_id)
    if company is None:
        raise AssertionError(f"company {company_id} not found")
    if not company.subdomain:
        raise AssertionError(f"company {company_id} has no subdomain")
    return f"http://{company.subdomain}.lvh.me:9004"


def loopback_frontend_http_target(public_origin: str) -> tuple[str, dict[str, str]]:
    """HTTP к granian 127.0.0.1 + Host компании. Без публичного DNS `*.lvh.me`."""
    parsed = urlparse(public_origin)
    if parsed.scheme != "http":
        raise AssertionError(f"agent test origin must be http: {public_origin}")
    if parsed.hostname is None:
        raise AssertionError(f"agent test origin missing host: {public_origin}")
    if parsed.port is None:
        raise AssertionError(f"agent test origin missing port: {public_origin}")
    return f"http://127.0.0.1:{parsed.port}", {"Host": parsed.netloc}


async def create_pairing_via_http(
    client: AsyncClient,
    *,
    auth_cookie: str | None = None,
) -> dict[str, object]:
    headers: dict[str, str] = {}
    if auth_cookie is not None:
        headers["Cookie"] = f"auth_token={auth_cookie}"
    response = await client.post(f"{AGENT_API_PREFIX}/pairing", headers=headers)
    response.raise_for_status()
    body = response.json()
    if not isinstance(body, dict):
        raise AssertionError("pairing response must be object")
    return body


async def register_device_via_http(
    client: AsyncClient,
    *,
    pairing_code: str,
    device_id: str,
    device_name: str,
    os_name: str,
    hostname: str,
) -> dict[str, object]:
    response = await client.post(
        f"{AGENT_API_PREFIX}/register",
        json={
            "pairing_code": pairing_code,
            "device_id": device_id,
            "device_name": device_name,
            "os": os_name,
            "hostname": hostname,
        },
    )
    response.raise_for_status()
    body = response.json()
    if not isinstance(body, dict):
        raise AssertionError("register response must be object")
    return body


async def pair_and_register_device(
    client: AsyncClient,
    *,
    auth_cookie: str,
    unique_id: str,
) -> tuple[str, str]:
    pairing_body = await create_pairing_via_http(client, auth_cookie=auth_cookie)
    pairing_code = pairing_body.get("pairing_code")
    if not isinstance(pairing_code, str) or len(pairing_code) != 6:
        raise AssertionError("pairing_code invalid")
    device_id = f"device-{unique_id}"
    register_body = await register_device_via_http(
        client,
        pairing_code=pairing_code,
        device_id=device_id,
        device_name=f"Device {unique_id}",
        os_name="darwin",
        hostname=f"host-{unique_id}",
    )
    token = register_body.get("token")
    if not isinstance(token, str) or not token:
        raise AssertionError("device token missing")
    return device_id, token


def user_id_from_auth_token(auth_token: str) -> str:
    token_data = get_token_service().validate_token(auth_token)
    if token_data is None:
        raise AssertionError("invalid auth token")
    return token_data.user_id


def company_id_from_auth_token(auth_token: str) -> str:
    token_data = get_token_service().validate_token(auth_token)
    if token_data is None:
        raise AssertionError("invalid auth token")
    return token_data.company_id


async def ensure_company_public_flows(company_id: str) -> None:
    """
    Материализует public flow ``lara`` в namespace компании.

    Без чтения/фолбека на company ``system``: seed и runtime — только эта company.
    """
    if not company_id.strip():
        raise AssertionError("company_id обязателен")
    if company_id == "system":
        raise AssertionError("seed lara в company system запрещён в agent LLM proxy тестах")
    container = get_flows_container()
    company = await container.company_repository.get(company_id)
    if company is None:
        raise AssertionError(f"company {company_id} not found")
    if company.owner_user_id is None or not company.owner_user_id.strip():
        raise AssertionError(f"company {company_id} без owner_user_id")
    owner = await container.user_repository.get(company.owner_user_id)
    if owner is None:
        raise AssertionError(
            f"owner {company.owner_user_id!r} компании {company_id} не найден"
        )
    if company_id not in owner.companies:
        raise AssertionError(
            f"owner {owner.user_id} не состоит в company {company_id}"
        )

    set_context(
        Context(
            user=owner,
            host="test",
            session_id=f"ensure_public_flows_{company_id}",
            channel="test",
            language=Language.RU,
            active_company=company,
            user_companies=[company],
            trace_id=f"test:ensure_public_flows:{company_id}",
        )
    )
    try:
        existing_lara = await container.flow_repository.get("lara")
        if existing_lara is not None:
            return
        _ = await load_tools_to_db(
        container.tool_repository,
        flow_access_service=container.flow_access_service,
    )
        loader = FlowsLoader(
            bundles_dir=_FLOWS_BUNDLES_DIR,
            flow_repository=container.flow_repository,
            node_repository=container.node_repository,
            tool_repository=container.tool_repository,
            registry_path=_FLOWS_REGISTRY_PATH,
            flow_access_service=container.flow_access_service,
        )
        loaded_flow_id = await loader.reload_flow_bundle("lara")
        if loaded_flow_id != "lara":
            raise AssertionError(
                f"ожидали reload lara, получили {loaded_flow_id!r} для company {company_id}"
            )
        lara_after = await container.flow_repository.get("lara")
        if lara_after is None:
            raise AssertionError(f"flow lara отсутствует в company {company_id} после seed")
    finally:
        clear_context()


async def seed_pairing_in_storage(
    frontend_container,
    *,
    pairing_code: str,
    user_id: str,
    company_id: str,
    ttl_seconds: int | None = None,
) -> None:
    key = f"agent_pairing:{pairing_code}"
    payload = json.dumps({"user_id": user_id, "company_id": company_id})
    await frontend_container.shared_storage.set(
        key,
        payload,
        ttl=ttl_seconds,
        force_global=True,
    )


async def assert_audit_event_in_redis(
    frontend_container,
    *,
    company_id: str,
    event_type: str,
) -> None:
    from apps.agent.service import AUDIT_KEY_PREFIX

    audit_key = f"{AUDIT_KEY_PREFIX}{company_id}"
    raw_items = await frontend_container.redis_client.lrange(audit_key, 0, -1)
    for raw_item in raw_items:
        payload = json.loads(raw_item)
        if isinstance(payload, dict) and payload.get("event_type") == event_type:
            return
    raise AssertionError(f"audit event {event_type!r} not found for company {company_id}")


async def ensure_agent_test_toolkit(
    flows_client: AsyncClient,
    auth_headers: dict[str, str],
    unique_id: str,
) -> str:
    toolkit_id = f"agent_test_{unique_id}"
    response = await flows_client.post(
        "/flows/api/v1/agent/toolkits/manage",
        headers=auth_headers,
        json={
            "toolkit_id": toolkit_id,
            "name": f"Agent test {unique_id}",
            "description": "Temporary toolkit for agent MCP tests",
            "default_enabled": True,
            "position": 999,
            "flow_ids": [],
            "tool_ids": ["calculator"],
        },
    )
    if response.status_code == 409:
        return toolkit_id
    assert response.status_code == 200, response.text
    return toolkit_id


async def ensure_example_react_flow(
    flows_client_http: AsyncClient,
    auth_headers: dict[str, str],
    unique_id: str,
) -> str:
    flow_id = f"agent_mcp_{unique_id}"
    toolkit_id = await ensure_agent_test_toolkit(flows_client_http, auth_headers, unique_id)
    response = await flows_client_http.post(
        "/flows/api/v1/flows/",
        headers=auth_headers,
        json={
            "flow_id": flow_id,
            "name": f"Agent MCP {unique_id}",
            "entry": "main",
            "agent_toolkit_ids": [toolkit_id],
            "nodes": {
                "main": {
                    "type": "llm_node",
                    "prompt": "Reply briefly to the user.",
                    "llm": {"provider": "mock", "model": "mock-gpt-4"},
                }
            },
            "edges": [{"from_node": "main", "to_node": None}],
        },
    )
    assert response.status_code == 200, response.text
    return flow_id


async def reset_company_agent_ui_state(frontend_container, *, company_id: str) -> None:
    """Очистить devices и audit компании перед UI-сценариями с пустым состоянием."""
    records = await frontend_container.shared_storage.get_all_by_prefix(
        DEVICE_KEY_PREFIX,
        limit=1000,
        force_global=True,
    )
    for storage_key, raw_value in records.items():
        device = AgentDeviceRecord.model_validate_json(raw_value)
        if device.company_id != company_id:
            continue
        await frontend_container.shared_storage.delete(storage_key, force_global=True)
        tunnel_key = f"{TUNNEL_ONLINE_PREFIX}{device.device_id}"
        await frontend_container.shared_storage.delete(tunnel_key, force_global=True)
    await frontend_container.redis_client.delete(_audit_storage_key(company_id))
