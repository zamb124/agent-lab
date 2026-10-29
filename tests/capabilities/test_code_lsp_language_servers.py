"""Живой JSON-RPC к language servers code_node на пяти языках. Без моков LS."""

from __future__ import annotations

from collections.abc import Mapping

import pytest
from httpx2 import AsyncClient

from core.capabilities.models import CAPABILITY_LANGUAGES, CapabilityLanguage
from tests.capabilities.code_lsp_helpers import (
    assert_lsp_ws_closed_policy,
    connect_code_lsp_ws,
    create_code_lsp_session,
    default_lsp_source,
    session_request,
)

_COMPLETION_AFTER: dict[CapabilityLanguage, tuple[tuple[str, str], ...]] = {
    "python": (("json.", "loads"), ("files.", "create")),
    "javascript": (("lodash.", "get"),),
    "typescript": (("lodash.", "get"),),
    "go": (("json.", "Marshal"),),
    "csharp": (("JsonSerializer.", "Serialize"), ("files.", "Create")),
}

_HOVER_NEEDLE: dict[CapabilityLanguage, str] = {
    "python": "create(content",
    "javascript": "get(args",
    "typescript": "get(args",
    "go": "Marshal(args",
    "csharp": "Create(new",
}

_DIAGNOSTIC_NEEDLE: dict[CapabilityLanguage, str | None] = {
    "python": "httpx",
    "javascript": "left-pad",
    "typescript": "left-pad",
    "go": "github.com/not-allowed/mod",
    "csharp": None,
}


@pytest.mark.asyncio
@pytest.mark.parametrize("language", CAPABILITY_LANGUAGES)
async def test_code_lsp_language_server_jsonrpc(
    language: CapabilityLanguage,
    sandbox_services: dict[str, str],
    flows_client_http: AsyncClient,
    auth_headers_system: Mapping[str, str],
    auth_token_system: str,
    unique_id: str,
    code_lsp_toolchains_ready: None,
) -> None:
    _ = sandbox_services, code_lsp_toolchains_ready
    request = session_request(language, unique_id)
    source = request.source
    session = await create_code_lsp_session(flows_client_http, auth_headers_system, request)
    assert session.language == language
    assert session.ws_path == f"/flows/api/v1/code/lsp/ws/{language}/{session.session_id}"
    assert session.ws_path.startswith("/flows/api/v1/code/lsp/ws/")
    assert unique_id in source

    async with connect_code_lsp_ws(auth_token_system, session.ws_path) as rpc:
        _ = await rpc.initialize(session)
        await rpc.did_open(session, source)
        for needle, expected in _COMPLETION_AFTER[language]:
            labels = await rpc.wait_completion_containing(
                session.document_uri,
                source,
                needle,
                expected,
            )
            assert labels
        hover = await rpc.wait_hover_text(
            session.document_uri,
            source,
            _HOVER_NEEDLE[language],
        )
        assert hover.strip() != ""
        diagnostic_needle = _DIAGNOSTIC_NEEDLE[language]
        if diagnostic_needle is not None:
            message = await rpc.wait_error_diagnostic(session.document_uri, diagnostic_needle)
            assert diagnostic_needle in message


@pytest.mark.asyncio
async def test_code_lsp_ws_without_cookie_closes_1008(
    sandbox_services: dict[str, str],
    flows_client_http: AsyncClient,
    auth_headers_system: Mapping[str, str],
    unique_id: str,
    code_lsp_toolchains_ready: None,
) -> None:
    _ = sandbox_services, code_lsp_toolchains_ready
    session = await create_code_lsp_session(
        flows_client_http,
        auth_headers_system,
        session_request("python", unique_id),
    )
    await assert_lsp_ws_closed_policy(None, session.ws_path)


@pytest.mark.asyncio
async def test_code_lsp_ws_unknown_session_closes_1008(
    sandbox_services: dict[str, str],
    unique_id: str,
    code_lsp_toolchains_ready: None,
) -> None:
    _ = sandbox_services, code_lsp_toolchains_ready
    await assert_lsp_ws_closed_policy(
        None,
        f"/flows/api/v1/code/lsp/ws/python/{unique_id}",
    )


@pytest.mark.asyncio
async def test_code_lsp_ws_unknown_session_with_cookie_closes_1008(
    sandbox_services: dict[str, str],
    auth_token_system: str,
    unique_id: str,
    code_lsp_toolchains_ready: None,
) -> None:
    _ = sandbox_services, code_lsp_toolchains_ready
    await assert_lsp_ws_closed_policy(
        auth_token_system,
        f"/flows/api/v1/code/lsp/ws/python/{unique_id}",
    )


@pytest.mark.asyncio
async def test_code_lsp_session_post_without_auth(
    sandbox_services: dict[str, str],
    flows_client_http: AsyncClient,
    unique_id: str,
    code_lsp_toolchains_ready: None,
) -> None:
    _ = sandbox_services, code_lsp_toolchains_ready
    response = await flows_client_http.post(
        "/flows/api/v1/code/lsp/session",
        json={
            "language": "python",
            "source": default_lsp_source("python", unique_id),
        },
    )
    assert response.status_code in {401, 403}
