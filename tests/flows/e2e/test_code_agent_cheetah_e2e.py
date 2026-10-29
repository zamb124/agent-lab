from __future__ import annotations

import asyncio
import json
import os
import shutil
from collections.abc import Awaitable, Callable, Sequence

import pytest
from httpx2 import AsyncClient

from apps.guest_runtime.services.slots import require_docker
from core.clients.flow_ui_client import FlowUIClient
from core.config import get_settings
from tests.fixtures.s3 import require_s3_configured
from tests.guest_runtime.http_helpers import (
    code_agent_headers,
    ensure_code_agent_catalog,
    import_code_agent_git,
    rebuild_code_agent,
)

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.real_taskiq,
    pytest.mark.network,
    pytest.mark.timeout(600, func_only=True),
]

MockLlmQueue = Callable[[Sequence[object]], Awaitable[None]]

FLOWS_BASE_URL = "http://localhost:9001/flows"

CHEETAH_WEB_URL = "https://github.com/zub123123123/cheetah-agent/tree/main"
CHEETAH_SOURCE_SHA = "70eb6c3c6909d1f975d9c7e6c723bae5db897478"

INTERFACE = {
    "start_page_id": "main",
    "pages": [
        {
            "page_id": "main",
            "title": "Code agent",
            "blocks": [
                {"type": "conversation", "block_id": "conversation"},
            ],
        }
    ],
}

CHEETAH_NODE = {
    "type": "code_agent",
    "language": "python",
    "invoke_kind": "cli",
    "invoke_argv": ["python3", "main.py"],
    "guest_env": {
        "API_KEY": "@platform:OPENAI_API_KEY",
        "BASE_URL": "@platform:OPENAI_BASE_URL",
        "MODEL_NAME": "auto",
    },
    "git_url": CHEETAH_WEB_URL,
    "source_sha": CHEETAH_SOURCE_SHA,
}

CHEETAH_MOCK_LLM: list[dict[str, str]] = [
    {
        "type": "text",
        "content": json.dumps(
            {
                "queries": [
                    {"query": "Cheetah", "lang": "en"},
                    {"query": "Гепард", "lang": "ru"},
                ]
            },
            ensure_ascii=False,
        ),
    },
    {
        "type": "text",
        "content": json.dumps(
            {
                "facts": [
                    {
                        "entity": "Cheetah",
                        "property": "max speed",
                        "value": "120",
                        "unit": "km/h",
                        "source_text": "The cheetah can run at 120 km/h.",
                        "confidence": 0.9,
                    }
                ]
            },
            ensure_ascii=False,
        ),
    },
    {
        "type": "text",
        "content": json.dumps(
            {
                "cot": "From the extracted facts the cheetah reaches 120 km/h.",
                "answer": "120 km/h",
            },
            ensure_ascii=False,
        ),
    },
    {
        "type": "text",
        "content": json.dumps(
            {
                "reason": "The facts support 120 km/h as the modern cheetah top speed.",
                "status": "VALID",
            },
            ensure_ascii=False,
        ),
    },
]


async def _require_cheetah_git() -> None:
    git = shutil.which("git")
    if git is None:
        pytest.skip("git is required for cheetah import-git")
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"
    process = await asyncio.create_subprocess_exec(
        git,
        "ls-remote",
        "https://github.com/zub123123123/cheetah-agent.git",
        CHEETAH_SOURCE_SHA,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    out, _ = await process.communicate()
    if process.returncode != 0:
        pytest.skip(f"github cheetah ls-remote failed: {out.decode('utf-8', errors='replace')}")


async def _skip_unless_docker_farm() -> None:
    if get_settings().guest_runtime.executor != "docker":
        pytest.skip("guest_runtime executor is not docker")
    try:
        await require_docker()
    except RuntimeError as exc:
        pytest.skip(str(exc))


async def _create_cheetah_flow(
    flows_client: AsyncClient,
    headers: dict[str, str],
    *,
    flow_id: str,
    node_id: str,
) -> None:
    create = await flows_client.post(
        "/flows/api/v1/flows/",
        headers=headers,
        json={
            "flow_id": flow_id,
            "name": flow_id,
            "entry": node_id,
            "nodes": {node_id: CHEETAH_NODE},
            "edges": [{"from_node": node_id, "to_node": None}],
            "interface": INTERFACE,
        },
    )
    assert create.status_code == 200, create.text


async def _import_cheetah(
    flows_client: AsyncClient,
    headers: dict[str, str],
    *,
    flow_id: str,
    node_id: str,
) -> None:
    _ = await ensure_code_agent_catalog(flows_client, headers, flow_id=flow_id, node_id=node_id)
    status = await import_code_agent_git(
        flows_client,
        headers,
        flow_id=flow_id,
        node_id=node_id,
        git_url=CHEETAH_WEB_URL,
        source_sha=CHEETAH_SOURCE_SHA,
    )
    assert status.git_url == CHEETAH_WEB_URL
    assert status.source_sha == CHEETAH_SOURCE_SHA
    names = {item.relative_path for item in status.files}
    for required in ("main.py", "pyproject.toml", "uv.lock"):
        if required not in names:
            raise AssertionError(f"cheetah catalog missing {required}: {sorted(names)}")


@pytest.mark.asyncio
async def test_code_agent_cheetah_import_git_product_path(
    flows_client_http: AsyncClient,
    office_service: object,
    guest_runtime_service: object,
    auth_headers_system: dict[str, str],
    unique_id: str,
) -> None:
    _ = office_service, guest_runtime_service
    require_s3_configured()
    await _require_cheetah_git()
    headers = code_agent_headers(auth_headers_system)
    flow_id = f"ca_ch_in_{unique_id}"
    node_id = "agent"
    await _create_cheetah_flow(flows_client_http, headers, flow_id=flow_id, node_id=node_id)
    await _import_cheetah(flows_client_http, headers, flow_id=flow_id, node_id=node_id)


@pytest.mark.asyncio
async def test_code_agent_cheetah_docker_flow_ui_chat(
    flows_client_http: AsyncClient,
    office_service: object,
    guest_runtime_service: object,
    auth_headers_system: dict[str, str],
    mock_llm_redis: MockLlmQueue,
    unique_id: str,
) -> None:
    _ = office_service, guest_runtime_service
    require_s3_configured()
    await _skip_unless_docker_farm()
    await _require_cheetah_git()
    await mock_llm_redis(list(CHEETAH_MOCK_LLM))
    headers = code_agent_headers(auth_headers_system)
    flow_id = f"ca_ch_dk_{unique_id}"
    node_id = "agent"
    await _create_cheetah_flow(flows_client_http, headers, flow_id=flow_id, node_id=node_id)
    await _import_cheetah(flows_client_http, headers, flow_id=flow_id, node_id=node_id)
    digest = await rebuild_code_agent(
        flows_client_http,
        headers,
        flow_id=flow_id,
        node_id=node_id,
        invoke_argv=["python3", "main.py"],
        git_url=CHEETAH_WEB_URL,
        source_sha=CHEETAH_SOURCE_SHA,
    )
    if digest.startswith("inprocess:"):
        raise AssertionError(f"cheetah docker rebuild returned inprocess digest: {digest}")
    sdk = FlowUIClient(FLOWS_BASE_URL, flow_id=flow_id, headers=headers, timeout=600.0)
    _ = await sdk.open(context_id=f"ctx-ch-{unique_id}")
    turn = await sdk.send("Какая максимальная скорость гепарда?")
    assert turn.status == "completed"
    if not turn.response.strip():
        raise AssertionError("cheetah FlowUI response is empty")
