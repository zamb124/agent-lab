from __future__ import annotations

import pytest

from tests.capabilities.capability_language_helpers import (
    assert_language_calls_tools_written_in_every_language,
    assert_language_documentation,
    assert_language_runs_interrupt_platform_capabilities,
    assert_language_runs_static_platform_capabilities,
    assert_language_sdk_covers_manifest,
)

pytestmark = pytest.mark.timeout(240)
LANGUAGE = "csharp"


@pytest.mark.asyncio
async def test_csharp_documentation_describes_every_capability(sandbox_services) -> None:
    await assert_language_documentation(LANGUAGE, sandbox_services)


@pytest.mark.asyncio
async def test_csharp_sdk_contains_every_manifest_capability(
    sandbox_services,
    flows_client_http,
    auth_headers_system,
) -> None:
    await assert_language_sdk_covers_manifest(
        LANGUAGE,
        sandbox_services,
        flows_client_http,
        auth_headers_system,
    )


@pytest.mark.asyncio
async def test_csharp_runs_every_static_platform_capability(
    sandbox_services,
    flows_client_http,
    auth_headers_system,
    unique_id,
) -> None:
    await assert_language_runs_static_platform_capabilities(
        LANGUAGE,
        sandbox_services,
        flows_client_http,
        auth_headers_system,
        unique_id,
    )


@pytest.mark.asyncio
async def test_csharp_runs_interrupt_platform_capability(sandbox_services) -> None:
    await assert_language_runs_interrupt_platform_capabilities(LANGUAGE, sandbox_services)


@pytest.mark.asyncio
async def test_csharp_calls_tools_written_in_every_language(
    flows_client_http,
    auth_headers_system,
    cross_language_tool_ids,
) -> None:
    await assert_language_calls_tools_written_in_every_language(
        LANGUAGE,
        flows_client_http,
        auth_headers_system,
        cross_language_tool_ids,
    )
