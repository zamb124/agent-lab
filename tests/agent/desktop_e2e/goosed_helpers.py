"""HTTP helpers для real goosed через Electron preload (CDP evaluate)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from httpx import AsyncClient
from playwright.async_api import Page

from tests.agent.desktop_e2e.electron_launcher import HumanitecDesktopProcess
from tests.agent.desktop_e2e.helpers import (
    ensure_humanitec_paired_and_llm_ready,
    open_settings_extensions,
)


class GoosedResponseError(RuntimeError):
    def __init__(self, status: int, body: object) -> None:
        super().__init__(f"goosed HTTP {status}: {body!r}")
        self.status = status
        self.body = body


async def get_goosed_base_url(page: Page) -> str:
    base_url = await page.evaluate("window.electron.getGoosedHostPort()")
    if not isinstance(base_url, str) or not base_url.strip():
        raise RuntimeError("goosed baseUrl missing from getGoosedHostPort()")
    return base_url.rstrip("/")


async def goosed_request(
    page: Page,
    method: str,
    path: str,
    body: dict[str, object] | None = None,
) -> tuple[int, object]:
    payload = {"method": method, "path": path, "body": body}
    result = await page.evaluate(
        """async ({ method, path, body }) => {
          const baseUrl = await window.electron.getGoosedHostPort();
          if (!baseUrl) {
            throw new Error('goosed baseUrl missing');
          }
          const secret = await window.electron.getSecretKey();
          const headers = { 'X-Secret-Key': secret };
          let requestInit = { method, headers };
          if (body !== null && body !== undefined) {
            headers['Content-Type'] = 'application/json';
            requestInit = { ...requestInit, body: JSON.stringify(body) };
          }
          const response = await fetch(`${baseUrl}${path}`, requestInit);
          const text = await response.text();
          let parsed = text;
          try {
            parsed = JSON.parse(text);
          } catch {
            parsed = text;
          }
          return { status: response.status, body: parsed };
        }""",
        payload,
    )
    if not isinstance(result, dict):
        raise RuntimeError(f"goosed evaluate returned unexpected payload: {result!r}")
    status = result.get("status")
    response_body = result.get("body")
    if not isinstance(status, int):
        raise RuntimeError(f"goosed status missing: {result!r}")
    return status, response_body


async def goosed_start_session(page: Page, working_dir: Path) -> str:
    status, body = await goosed_request(
        page,
        "POST",
        "/agent/start",
        {"working_dir": str(working_dir)},
    )
    if status != 200:
        raise GoosedResponseError(status, body)
    if not isinstance(body, dict):
        raise RuntimeError(f"goosed start returned non-object: {body!r}")
    session_id = body.get("id")
    if not isinstance(session_id, str) or not session_id:
        raise RuntimeError(f"goosed session id missing: {body!r}")
    return session_id


async def goosed_resume_session(page: Page, session_id: str) -> None:
    status, body = await goosed_request(
        page,
        "POST",
        "/agent/resume",
        {
            "session_id": session_id,
            "load_model_and_extensions": True,
        },
    )
    if status != 200:
        raise GoosedResponseError(status, body)


async def goosed_tools_list(
    page: Page,
    session_id: str,
    *,
    extension_name: str | None = None,
) -> list[dict[str, object]]:
    query = f"session_id={session_id}"
    if extension_name is not None:
        query = f"{query}&extension_name={extension_name}"
    status, body = await goosed_request(page, "GET", f"/agent/tools?{query}")
    if status != 200:
        raise GoosedResponseError(status, body)
    if not isinstance(body, list):
        raise RuntimeError(f"goosed tools/list returned non-list: {body!r}")
    tools: list[dict[str, object]] = []
    for item in body:
        if isinstance(item, dict):
            tools.append(item)
    return tools


async def goosed_call_tool(
    page: Page,
    session_id: str,
    tool_name: str,
    arguments: dict[str, object],
) -> dict[str, object]:
    status, body = await goosed_request(
        page,
        "POST",
        "/agent/call_tool",
        {
            "session_id": session_id,
            "name": tool_name,
            "arguments": arguments,
        },
    )
    if status != 200:
        raise GoosedResponseError(status, body)
    if not isinstance(body, dict):
        raise RuntimeError(f"goosed call_tool returned non-object: {body!r}")
    return body


async def wait_for_goosed_tools(
    page: Page,
    session_id: str,
    *,
    name_suffix: str,
    timeout_seconds: float = 120.0,
) -> dict[str, object]:
    deadline = asyncio.get_event_loop().time() + timeout_seconds
    last_tools: list[dict[str, object]] = []
    while asyncio.get_event_loop().time() < deadline:
        last_tools = await goosed_tools_list(page, session_id)
        for tool in last_tools:
            tool_name = tool.get("name")
            if isinstance(tool_name, str) and tool_name.endswith(name_suffix):
                return tool
        await asyncio.sleep(1.0)
    names = [tool.get("name") for tool in last_tools]
    raise TimeoutError(
        f"goosed tool suffix {name_suffix!r} not found; tools={names!r}"
    )


def resolve_tool_name(tools: list[dict[str, object]], suffix: str) -> str:
    for tool in tools:
        tool_name = tool.get("name")
        if isinstance(tool_name, str) and tool_name.endswith(suffix):
            return tool_name
    names = [tool.get("name") for tool in tools]
    raise ValueError(f"tool suffix {suffix!r} not in {names!r}")


def resolve_tool_exact(tools: list[dict[str, object]], name: str) -> str:
    for tool in tools:
        tool_name = tool.get("name")
        if tool_name == name:
            return name
    names = [tool.get("name") for tool in tools if isinstance(tool.get("name"), str)]
    raise ValueError(f"tool {name!r} not in {names!r}")


def tool_response_text(body: dict[str, object]) -> str:
    content = body.get("content")
    if not isinstance(content, list):
        raise ValueError("call_tool content missing")
    chunks: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        text_value = item.get("text")
        if isinstance(text_value, str):
            chunks.append(text_value)
    if not chunks:
        raise ValueError(f"call_tool returned no text: {json.dumps(body)}")
    return "\n".join(chunks)


def tool_response_contains(body: dict[str, object], needle: str) -> bool:
    text = tool_response_text(body)
    if needle in text:
        return True
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return False
    if isinstance(parsed, dict):
        stdout = parsed.get("stdout")
        if isinstance(stdout, str) and needle in stdout:
            return True
        stderr = parsed.get("stderr")
        if isinstance(stderr, str) and needle in stderr:
            return True
    return False


async def assert_extension_tools_present(
    page: Page,
    session_id: str,
    extension_id: str,
    expected_tool_names: set[str],
) -> None:
    tools = await goosed_tools_list(page, session_id, extension_name=extension_id)
    present: set[str] = set()
    for tool in tools:
        tool_name = tool.get("name")
        if isinstance(tool_name, str):
            present.add(tool_name)
    missing = expected_tool_names - present
    if missing:
        raise AssertionError(
            f"extension {extension_id!r} missing tools {sorted(missing)!r}; present={sorted(present)!r}"
        )


async def enable_extension_in_settings(page: Page, extension_display_name: str) -> None:
    await _set_extension_toggle(page, extension_display_name, enabled=True)


async def disable_extension_in_settings(page: Page, extension_display_name: str) -> None:
    await _set_extension_toggle(page, extension_display_name, enabled=False)


async def _set_extension_toggle(
    page: Page,
    extension_display_name: str,
    *,
    enabled: bool,
) -> None:
    await open_settings_extensions(page)
    toggle = page.get_by_role("switch", name=extension_display_name)
    if await toggle.count() > 0:
        is_checked = await toggle.first.is_checked()
        if is_checked != enabled:
            await toggle.first.click()
            await page.wait_for_timeout(1000)
        return
    checkbox = page.locator("input[type=checkbox]").filter(
        has=page.get_by_text(extension_display_name, exact=False)
    )
    if await checkbox.count() > 0:
        is_checked = await checkbox.first.is_checked()
        if is_checked != enabled:
            await checkbox.first.click()
            await page.wait_for_timeout(1000)
        return
    label = page.get_by_text(extension_display_name, exact=False).first
    await label.click()
    await page.wait_for_timeout(1000)


async def goosed_get_config_extensions(page: Page) -> list[dict[str, object]]:
    status, body = await goosed_request(page, "GET", "/config/extensions")
    if status != 200:
        raise GoosedResponseError(status, body)
    if not isinstance(body, dict):
        raise RuntimeError(f"goosed config/extensions returned non-object: {body!r}")
    extensions = body.get("extensions")
    if not isinstance(extensions, list):
        raise RuntimeError(f"goosed config/extensions missing list: {body!r}")
    result: list[dict[str, object]] = []
    for item in extensions:
        if isinstance(item, dict):
            result.append(item)
    return result


async def prepare_goosed_developer_session(
    page: Page,
    workspace_dir: Path,
    *,
    desktop: HumanitecDesktopProcess,
    agent_frontend_http_client: AsyncClient,
    auth_token: str,
) -> str:
    await ensure_humanitec_paired_and_llm_ready(
        desktop,
        page,
        agent_frontend_http_client,
        auth_token,
    )
    workspace_dir.mkdir(parents=True, exist_ok=True)
    session_id = await goosed_start_session(page, workspace_dir)
    await goosed_resume_session(page, session_id)
    await wait_for_goosed_tools(page, session_id, name_suffix="tree")
    return session_id


async def prepare_goosed_session_with_extensions(
    page: Page,
    workspace_dir: Path,
    *,
    desktop: HumanitecDesktopProcess,
    agent_frontend_http_client: AsyncClient,
    auth_token: str,
    enabled_extensions: list[str],
) -> str:
    await ensure_humanitec_paired_and_llm_ready(
        desktop,
        page,
        agent_frontend_http_client,
        auth_token,
    )
    for extension_display_name in enabled_extensions:
        await enable_extension_in_settings(page, extension_display_name)
    workspace_dir.mkdir(parents=True, exist_ok=True)
    session_id = await goosed_start_session(page, workspace_dir)
    await goosed_resume_session(page, session_id)
    return session_id
