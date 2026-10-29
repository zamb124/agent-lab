"""HTTP contract tests for code-runner /analyze endpoints."""

from __future__ import annotations

import pytest

from core.code_contract import scan_code_contract

RUNNERS = (
    ("code_runner_python", "code-runner-python", "python"),
    ("code_runner_node", "code-runner-node", "javascript"),
    ("code_runner_go", "code-runner-go", "go"),
    ("code_runner_csharp", "code-runner-csharp", "csharp"),
)

CODE_SAMPLE = "state.answer = 42\nreturn { ok: true }"


@pytest.mark.asyncio
@pytest.mark.parametrize("service_key,prefix,language", RUNNERS)
async def test_code_runner_analyze_returns_contract(
    sandbox_services, service_key: str, prefix: str, language: str
):
    base_url = sandbox_services[service_key]
    import httpx2

    async with httpx2.AsyncClient(timeout=30.0) as http_client:
        response = await http_client.post(
            f"{base_url}/{prefix}/api/v1/analyze",
            json={"language": language, "code": CODE_SAMPLE},
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["language"] == language
    assert "contract" in payload
    expected = scan_code_contract(language, CODE_SAMPLE)
    assert payload["contract"]["writes"] == expected.writes


@pytest.mark.asyncio
@pytest.mark.parametrize("service_key,prefix,language", RUNNERS)
async def test_code_runner_analyze_empty_code(
    sandbox_services, service_key: str, prefix: str, language: str
):
    base_url = sandbox_services[service_key]
    import httpx2

    async with httpx2.AsyncClient(timeout=30.0) as http_client:
        response = await http_client.post(
            f"{base_url}/{prefix}/api/v1/analyze",
            json={"language": language, "code": ""},
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["contract"]["reads"] == []
    assert payload["contract"]["writes"] == []
    assert payload["contract"]["return_keys"] == []


@pytest.mark.asyncio
async def test_code_runner_analyze_invalid_json_422(sandbox_services):
    base_url = sandbox_services["code_runner_python"]
    import httpx2

    async with httpx2.AsyncClient(timeout=30.0) as http_client:
        response = await http_client.post(
            f"{base_url}/code-runner-python/api/v1/analyze",
            content=b"not-json",
            headers={"Content-Type": "application/json"},
        )
    assert response.status_code == 422
