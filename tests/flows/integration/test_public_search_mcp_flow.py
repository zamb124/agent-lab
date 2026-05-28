import base64
import json
from typing import Any

import pytest

from apps.flows.src.services.mcp_sync import sync_mcp_server_tools
from core.integrations.mcp import mcp_tool_reference_id


def _task_response_text(data: dict[str, Any]) -> str:
    message = data.get("status", {}).get("message") or {}
    parts = message.get("parts") or []
    if not parts:
        return ""
    return str(parts[0].get("text") or "")


def _captured_text(call: dict[str, Any]) -> str:
    return "\n".join(str(message.get("text") or "") for message in call["messages"])


def _parse_sse_results(text: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line in text.splitlines():
        if not line.startswith("data: "):
            continue
        raw = line[6:]
        if raw == "[DONE]":
            continue
        data = json.loads(raw)
        result = data.get("result")
        if isinstance(result, dict):
            events.append(result)
    return events


def _artifact_data_part(artifact: dict[str, Any]) -> dict[str, Any]:
    parts = artifact.get("parts")
    assert isinstance(parts, list) and parts
    part = parts[0]
    assert isinstance(part, dict)
    data = part.get("data")
    if isinstance(data, dict):
        return data
    root = part.get("root")
    assert isinstance(root, dict)
    root_data = root.get("data")
    assert isinstance(root_data, dict)
    return root_data


def _captured_tool_names(calls: list[dict[str, Any]]) -> set[str]:
    names: set[str] = set()
    for call in calls:
        tools = call.get("tools")
        if not isinstance(tools, list):
            continue
        for item in tools:
            if not isinstance(item, dict):
                continue
            function = item.get("function")
            if isinstance(function, dict):
                name = function.get("name")
                if isinstance(name, str):
                    names.add(name)
                    continue
            name = item.get("name")
            if isinstance(name, str):
                names.add(name)
    return names


@pytest.mark.asyncio
@pytest.mark.real_taskiq
@pytest.mark.timeout(180, func_only=True)
async def test_public_search_flow_calls_search_mcp_without_monkeypatches(
    search_service,
    client,
    container,
    mock_llm_redis,
    mock_llm_capture,
    unique_id,
) -> None:
    _ = search_service
    await mock_llm_redis(
        [
            {
                "type": "text",
                "content": "SEARCH_FLOW_OK",
            }
        ]
    )
    search_mcp_server = await container.mcp_server_repository.get("search")
    assert search_mcp_server is not None
    synced_tool_ids, _ = await sync_mcp_server_tools(
        container=container,
        server_config=search_mcp_server,
    )
    assert set(synced_tool_ids) >= {
        mcp_tool_reference_id("search", "meta_web_search"),
        mcp_tool_reference_id("search", "search_suggest"),
        mcp_tool_reference_id("search", "search_result_insights"),
    }

    response = await client.post(
        "/flows/api/v1/tasks/submit",
        json={
            "flow_id": "public_search",
            "session_id": f"public_search:search-mcp-{unique_id}",
            "content": f"Tavily Search API official documentation {unique_id}",
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"]["state"] == "completed", payload
    search_artifact = json.loads(_task_response_text(payload))
    assert search_artifact["kind"] == "public_search_serp"
    assert search_artifact["version"] == 1
    assert search_artifact["flow_id"] == "public_search"
    assert search_artifact["mode"] == "quick"
    assert search_artifact["query"] == f"Tavily Search API official documentation {unique_id}"
    assert search_artifact["answer"] == "SEARCH_FLOW_OK"
    assert search_artifact["results"]
    assert search_artifact["providers"]["tavily"]["ok"] is True
    assert search_artifact["suggestions"]
    assert search_artifact["followups"]
    assert search_artifact["result_insights"]

    for tool_name in ["meta_web_search", "search_suggest", "search_result_insights"]:
        tool_ref = await container.tool_repository.get(mcp_tool_reference_id("search", tool_name))
        assert tool_ref is not None
        assert tool_ref.mcp_server_id == "search"
        assert tool_ref.mcp_tool_name == tool_name

    calls = await mock_llm_capture()
    prompt_text = "\n".join(_captured_text(call) for call in calls)
    assert f"Tavily Search API official documentation {unique_id}" in prompt_text
    assert '"tavily"' in prompt_text
    assert '"ok": true' in prompt_text
    assert '"selected": true' in prompt_text
    assert "Подсказки для уточнения" in prompt_text
    assert "Follow-up вопросы" in prompt_text
    assert "Инсайты по результатам" in prompt_text
    assert '"actions"' in prompt_text

    await mock_llm_redis(
        [
            {
                "type": "text",
                "content": "SEARCH_FLOW_STREAM_OK",
            }
        ]
    )
    stream_response = await client.post(
        "/flows/api/v1/public_search",
        json={
            "jsonrpc": "2.0",
            "id": f"public-search-stream-{unique_id}",
            "method": "message/stream",
            "params": {
                "message": {
                    "messageId": f"public-search-stream-message-{unique_id}",
                    "role": "user",
                    "parts": [
                        {"kind": "text", "text": f"Serper Search API pricing {unique_id}"}
                    ],
                },
                "metadata": {"branch": "quick"},
            },
        },
    )
    assert stream_response.status_code == 200, stream_response.text
    assert "text/event-stream" in stream_response.headers.get("content-type", "")
    events = _parse_sse_results(stream_response.text)
    ui_payloads: dict[str, dict[str, Any]] = {}
    for event in events:
        if event.get("kind") != "artifact-update":
            continue
        artifact = event.get("artifact")
        if not isinstance(artifact, dict):
            continue
        if artifact.get("name") != "ui_event":
            continue
        data = _artifact_data_part(artifact)
        event_type = data.get("type")
        payload = data.get("payload")
        if isinstance(event_type, str) and isinstance(payload, dict):
            ui_payloads[event_type] = payload

    assert ui_payloads["search/serp/results_ready"]["phase"] == "results"
    assert ui_payloads["search/serp/results_ready"]["results"]
    assert ui_payloads["search/serp/suggestions_ready"]["phase"] == "suggestions"
    assert ui_payloads["search/serp/suggestions_ready"]["followups"]
    assert ui_payloads["search/serp/insights_ready"]["phase"] == "insights"
    assert ui_payloads["search/serp/insights_ready"]["result_insights"]
    assert ui_payloads["search/serp/completed"]["kind"] == "public_search_serp"
    assert ui_payloads["search/serp/completed"]["answer"] == "SEARCH_FLOW_STREAM_OK"


@pytest.mark.asyncio
@pytest.mark.real_taskiq
@pytest.mark.timeout(180, func_only=True)
async def test_public_search_with_file_reads_file_before_search(
    search_service,
    client,
    mock_llm_redis,
    mock_llm_capture,
    unique_id,
) -> None:
    _ = search_service
    query = f"Найди официальные условия договора {unique_id}"
    file_name = f"contract-search-{unique_id}.txt"
    file_text = (
        "Договор бронирования. Ракурс Вальдштейн. "
        "Ключевые условия: депозит, отмена бронирования, ответственность сторон."
    )
    summary = (
        "- Файл про договор бронирования Ракурс Вальдштейн.\n"
        "- Важны депозит, отмена бронирования и ответственность сторон.\n"
        "Ключевые термины: договор бронирования, депозит, отмена, ответственность."
    )
    await mock_llm_redis(
        [
            {
                "type": "tool_call",
                "tool": "read_file",
                "args": {"file_name": file_name},
            },
            {
                "type": "text",
                "content": summary,
            },
            {
                "type": "text",
                "content": "SEARCH_WITH_FILE_OK",
            },
        ]
    )

    stream_response = await client.post(
        "/flows/api/v1/public_search",
        json={
            "jsonrpc": "2.0",
            "id": f"public-search-file-{unique_id}",
            "method": "message/stream",
            "params": {
                "message": {
                    "messageId": f"public-search-file-message-{unique_id}",
                    "role": "user",
                    "parts": [
                        {"kind": "text", "text": query},
                        {
                            "kind": "file",
                            "file": {
                                "bytes": base64.b64encode(file_text.encode("utf-8")).decode("utf-8"),
                                "name": file_name,
                                "mimeType": "text/plain",
                            },
                        },
                    ],
                },
                "metadata": {"branch": "quick"},
            },
        },
    )

    assert stream_response.status_code == 200, stream_response.text
    events = _parse_sse_results(stream_response.text)
    completed_payload: dict[str, Any] | None = None
    for event in events:
        if event.get("kind") != "artifact-update":
            continue
        artifact = event.get("artifact")
        if not isinstance(artifact, dict) or artifact.get("name") != "ui_event":
            continue
        data = _artifact_data_part(artifact)
        if data.get("type") == "search/serp/completed":
            payload = data.get("payload")
            assert isinstance(payload, dict)
            completed_payload = payload

    assert completed_payload is not None, stream_response.text
    assert completed_payload["query"] == query
    assert "[FILE]" not in completed_payload["query"]
    assert completed_payload["answer"] == "SEARCH_WITH_FILE_OK"
    assert completed_payload["file_context"] == summary
    assert "Краткий контекст приложенных файлов" in completed_payload["effective_query"]
    assert "Ключевые термины" in completed_payload["effective_query"]

    calls = await mock_llm_capture()
    assert "read_file" in _captured_tool_names(calls)
    prompt_text = "\n".join(_captured_text(call) for call in calls)
    assert file_name in prompt_text
    assert "[FILE]" not in completed_payload["effective_query"]


@pytest.mark.asyncio
@pytest.mark.real_taskiq
@pytest.mark.timeout(180, func_only=True)
async def test_public_search_source_branch_calls_browser_tool_without_builtin_bypass(
    client,
    container,
    mock_llm_redis,
    mock_llm_capture,
    unique_id,
) -> None:
    tool_ref = await container.tool_repository.get("browser_page_markdown")
    assert tool_ref is not None
    assert "tools.call_builtin" not in (tool_ref.code or "")

    await mock_llm_redis(
        [
            {
                "type": "tool_call",
                "tool": "browser_page_markdown",
                "args": {
                    "url": "https://example.com/source-ai",
                    "server_id": "missing_browser_for_test",
                },
            },
            {
                "type": "text",
                "content": "SOURCE_AI_OK",
            },
        ]
    )

    response = await client.post(
        "/flows/api/v1/tasks/submit",
        json={
            "flow_id": "public_search",
            "branch_id": "source",
            "session_id": f"public_search:source-ai-{unique_id}",
            "content": "AI по источнику https://example.com/source-ai",
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"]["state"] == "completed", payload
    response_text = _task_response_text(payload)
    assert "SOURCE_AI_OK" in response_text
    assert "Capability is not declared in manifest" not in response_text
    assert "tools.call_builtin" not in response_text

    calls = await mock_llm_capture()
    assert "browser_page_markdown" in _captured_tool_names(calls)
    prompt_text = "\n".join(_captured_text(call) for call in calls)
    assert "missing_browser_for_test" in prompt_text
    assert "tools.call_builtin" not in prompt_text
