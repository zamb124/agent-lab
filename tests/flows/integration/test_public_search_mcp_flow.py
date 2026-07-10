import base64
import json
from typing import Any

import pytest

from apps.flows.src.services.mcp_sync import sync_mcp_server_tools
from apps.flows.tools.builtin_specs import builtin_tool_ids
from apps.flows.tools.index_search import web_search
from core.integrations.mcp import mcp_tool_reference_id
from core.state import ExecutionState
from tests.search.conftest import make_search_index_slug
from tests.search.integration.snippet_support import strip_snippet_highlight

# Search MCP system context требует bootstrap system-admin (ensure_platform_search_worker_prerequisites
# — autouse session fixture в tests/search/conftest.py). Без регистрации плагина autouse-фикстура не
# срабатывает для тестов под tests/flows/, и MCP RPC падает "system admin user is required".
pytest_plugins = ["tests.search.conftest"]


async def _ingest_runet_marker(
    rag_client,
    auth_headers_system: dict[str, str],
    unique_id: str,
    marker: str,
) -> str:
    doc_text = (
        f"Public search runet integration document with marker {marker}. "
        "Длинный текст для стабильного RAG chunk и platform index search."
    )
    namespace_response = await rag_client.post(
        "/rag/api/v1/namespaces",
        json={"name": "runet:platform", "description": "runet platform index"},
        headers=auth_headers_system,
    )
    assert namespace_response.status_code in {201, 400}

    ingest = await rag_client.post(
        "/rag/api/v1/namespaces/runet:platform/ingest-text",
        json={
            "text": doc_text,
            "document_name": f"public-search-{unique_id}.md",
            "metadata": {
                "source_url": f"https://public-search-runet.test/{unique_id}",
                "collection_id": "runet",
            },
        },
        headers=auth_headers_system,
    )
    assert ingest.status_code == 200

    rag_search = await rag_client.post(
        "/rag/api/v1/namespaces/runet:platform/search",
        json={"query": doc_text, "limit": 3},
        headers=auth_headers_system,
    )
    assert rag_search.status_code == 200
    assert rag_search.json().get("results")

    return doc_text


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


def _collect_ui_events(stream_text: str) -> list[tuple[str, dict[str, Any]]]:
    events: list[tuple[str, dict[str, Any]]] = []
    for event in _parse_sse_results(stream_text):
        if event.get("kind") != "artifact-update":
            continue
        artifact = event.get("artifact")
        if not isinstance(artifact, dict) or artifact.get("name") != "ui_event":
            continue
        data = _artifact_data_part(artifact)
        event_type = data.get("type")
        payload = data.get("payload")
        if isinstance(event_type, str) and isinstance(payload, dict):
            events.append((event_type, payload))
    return events


async def _post_research_stream(
    client,
    *,
    unique_id: str,
    content: str,
    variables: dict[str, object] | None = None,
) -> str:
    metadata: dict[str, object] = {"branch": "research"}
    if variables is not None:
        metadata["variables"] = variables
    stream_response = await client.post(
        "/flows/api/v1/public_search",
        json={
            "jsonrpc": "2.0",
            "id": f"public-search-research-stream-{unique_id}",
            "method": "message/stream",
            "params": {
                "message": {
                    "messageId": f"public-search-research-stream-message-{unique_id}",
                    "role": "user",
                    "parts": [{"kind": "text", "text": content}],
                },
                "metadata": metadata,
            },
        },
    )
    assert stream_response.status_code == 200, stream_response.text
    assert "text/event-stream" in stream_response.headers.get("content-type", "")
    return stream_response.text


@pytest.mark.asyncio
@pytest.mark.real_taskiq
@pytest.mark.timeout(180, func_only=True)
async def test_public_search_flow_calls_search_mcp_without_monkeypatches(
    search_service,
    rag_service,
    rag_client,
    rag_worker,
    provider_litserve_service,
    auth_headers_system,
    client,
    container,
    mock_llm_redis,
    mock_llm_capture,
    unique_id,
) -> None:
    # rag_service (HTTP :9002) обязателен: search MCP index_search ходит в RAG по HTTP,
    # а rag_client — только in-process ASGI и сервер не поднимает.
    _ = search_service, rag_service, rag_worker, provider_litserve_service
    marker = f"public_search_runet_marker_{unique_id}"
    doc_text = await _ingest_runet_marker(
        rag_client,
        auth_headers_system,
        unique_id,
        marker,
    )
    query = doc_text
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
            "content": query,
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
    assert search_artifact["query"] == query
    assert search_artifact["answer"] == "SEARCH_FLOW_OK"
    assert search_artifact["results"]
    markdown_sources = search_artifact["markdown_sources"]
    first_result = search_artifact["results"][0]
    first_url = first_result["url"].replace(" ", "%20").replace("(", "%28").replace(")", "%29")
    assert markdown_sources.startswith("1. [")
    assert f"]({first_url})" in markdown_sources
    assert search_artifact["providers"]["index"]["ok"] is True
    snippet = strip_snippet_highlight(search_artifact["results"][0].get("snippet", ""))
    assert marker in snippet
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
    assert query in prompt_text
    assert '"index"' in prompt_text
    assert '"ok": true' in prompt_text
    assert '"selected": true' in prompt_text
    assert '"tavily"' not in prompt_text
    assert "Подсказки для уточнения" in prompt_text
    assert "Follow-up вопросы" in prompt_text
    assert "Инсайты по результатам" in prompt_text
    assert "Markdown-источники для финального ответа" in prompt_text
    assert "URL допустим только внутри Markdown-ссылки" in prompt_text
    assert markdown_sources in prompt_text
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
                        {"kind": "text", "text": query}
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
    assert ui_payloads["search/serp/completed"]["markdown_sources"].startswith("1. [")


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
                    "contextId": f"ctx-{unique_id}",
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


@pytest.mark.asyncio
@pytest.mark.real_taskiq
@pytest.mark.timeout(180, func_only=True)
async def test_public_search_runet_empty_index_honest(
    search_service,
    rag_service,
    search_client,
    rag_client,
    rag_worker,
    provider_litserve_service,
    auth_headers_system,
    client,
    mock_llm_redis,
    mock_llm_capture,
    unique_id,
) -> None:
    # rag_service (HTTP :9002) обязателен: search MCP index_search ходит в RAG по HTTP.
    _ = search_service, rag_service, rag_worker, provider_litserve_service
    search_index_id = make_search_index_slug(f"empty_{unique_id}")
    rag_namespace_id = f"{search_index_id}:ns"

    create_index = await search_client.post(
        "/search/api/v1/search-indexes",
        json={
            "search_index_id": search_index_id,
            "display_name": f"Public search empty {unique_id}",
            "rag_namespace_id": rag_namespace_id,
            "rag_collection_id": search_index_id,
        },
    )
    assert create_index.status_code == 201

    namespace_response = await rag_client.post(
        "/rag/api/v1/namespaces",
        json={"name": rag_namespace_id, "description": "public search empty index"},
        headers=auth_headers_system,
    )
    assert namespace_response.status_code in {201, 400}

    query = f"public_search_empty_runet_query_{unique_id}"
    await mock_llm_redis(
        [
            {
                "type": "text",
                "content": "EMPTY_RUNET_OK",
            }
        ]
    )

    response = await client.post(
        "/flows/api/v1/tasks/submit",
        json={
            "flow_id": "public_search",
            "session_id": f"public_search:empty-runet-{unique_id}",
            "content": query,
            "metadata": {
                "variables": {
                    "search_providers": [f"index:{search_index_id}"],
                }
            },
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"]["state"] == "completed", payload
    search_artifact = json.loads(_task_response_text(payload))
    assert search_artifact["results"] == []
    assert search_artifact["providers"]["index"]["ok"] is False
    assert search_artifact["providers"]["index"]["error"] == "index returned no results"
    assert "tavily" not in search_artifact["providers"]

    calls = await mock_llm_capture()
    prompt_text = "\n".join(_captured_text(call) for call in calls)
    assert query in prompt_text
    assert "index returned no results" in prompt_text
    assert search_artifact["answer"] == "EMPTY_RUNET_OK"


@pytest.mark.asyncio
@pytest.mark.real_taskiq
@pytest.mark.timeout(240, func_only=True)
async def test_public_search_research_branch_runs_agentic_loop(
    search_service,
    rag_service,
    rag_client,
    rag_worker,
    provider_litserve_service,
    auth_headers_system,
    client,
    container,
    mock_llm_redis,
    mock_llm_capture,
    unique_id,
) -> None:
    # rag_service (HTTP :9002) обязателен: web_search index provider ходит в RAG по HTTP.
    # Браузер (browser_page_markdown) в тестовой среде недоступен, поэтому read-wave
    # переносит сбои чтения без падения графа — проверяем именно durable-цикл и контракт отчёта.
    _ = search_service, rag_service, rag_worker, provider_litserve_service
    assert "web_search" in builtin_tool_ids()

    marker = f"public_search_research_marker_{unique_id}"
    query = await _ingest_runet_marker(
        rag_client,
        auth_headers_system,
        unique_id,
        marker,
    )

    plan_json = json.dumps(
        {
            "brief": f"Исследование по маркеру {marker}",
            "sub_questions": ["Что это за документ?", "Какие ключевые условия?"],
            "queries": [query],
            "outline": ["Обзор", "Детали"],
        },
        ensure_ascii=False,
    )
    reflect_json = json.dumps(
        {"need_more": False, "gap_queries": [], "coverage_note": "Данных достаточно"},
        ensure_ascii=False,
    )
    report_text = (
        "RESEARCH_REPORT_OK\n\n## Обзор\nКлючевой факт исследования.\n\n"
        "## Что дальше\n- Проверить дополнительные источники."
    )
    await mock_llm_redis(
        [
            {"type": "text", "content": plan_json},
            {"type": "text", "content": reflect_json},
            {"type": "text", "content": report_text},
        ]
    )

    response = await client.post(
        "/flows/api/v1/tasks/submit",
        json={
            "flow_id": "public_search",
            "branch_id": "research",
            "session_id": f"public_search:research-{unique_id}",
            "content": query,
            "metadata": {
                "variables": {
                    "search_providers": ["runet"],
                }
            },
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"]["state"] == "completed", payload
    artifact = json.loads(_task_response_text(payload))
    assert artifact["kind"] == "public_search_research_report"
    assert artifact["version"] == 1
    assert artifact["flow_id"] == "public_search"
    assert artifact["mode"] == "research"
    assert artifact["query"] == query
    assert artifact["brief"] == f"Исследование по маркеру {marker}"
    assert artifact["sub_questions"] == ["Что это за документ?", "Какие ключевые условия?"]
    assert artifact["outline"] == ["Обзор", "Детали"]
    assert "RESEARCH_REPORT_OK" in artifact["report"]
    assert isinstance(artifact["sources"], list)
    assert artifact["iterations"] >= 1
    assert artifact["coverage_note"] == "Данных достаточно"
    assert isinstance(artifact["markdown_sources"], str)

    calls = await mock_llm_capture()
    prompt_text = "\n".join(_captured_text(call) for call in calls)
    assert "Humanitec Deep Research" in prompt_text
    assert query in prompt_text


@pytest.mark.asyncio
@pytest.mark.real_taskiq
@pytest.mark.timeout(180, func_only=True)
async def test_web_search_builtin_returns_runet_results(
    search_service,
    rag_service,
    rag_client,
    rag_worker,
    provider_litserve_service,
    auth_headers_system,
    search_system_context,
    unique_id,
) -> None:
    _ = search_service, rag_service, rag_worker, provider_litserve_service, search_system_context
    marker = f"public_search_web_search_marker_{unique_id}"
    query = await _ingest_runet_marker(
        rag_client,
        auth_headers_system,
        unique_id,
        marker,
    )
    state = ExecutionState.create(
        task_id=f"web-search-{unique_id}",
        context_id=f"ctx-{unique_id}",
        user_id="test-user",
        session_id=f"public_search:web-search-{unique_id}",
        content=query,
    )
    raw = await web_search.run(
        {
            "query": query,
            "providers": ["runet"],
            "provider_strategy": "merge",
            "language": "ru",
            "region": "ru",
            "mode": "research",
            "limit": 5,
        },
        state,
    )
    assert isinstance(raw, dict)
    assert raw["success"] is True
    results = raw["results"]
    assert isinstance(results, list)
    assert len(results) >= 1
    first = results[0]
    assert isinstance(first, dict)
    assert marker in strip_snippet_highlight(str(first.get("snippet", "")))


@pytest.mark.asyncio
@pytest.mark.real_taskiq
@pytest.mark.timeout(240, func_only=True)
async def test_public_search_research_branch_streams_ui_events(
    search_service,
    rag_service,
    rag_client,
    rag_worker,
    provider_litserve_service,
    auth_headers_system,
    client,
    mock_llm_redis,
    unique_id,
) -> None:
    _ = search_service, rag_service, rag_worker, provider_litserve_service
    marker = f"public_search_research_stream_marker_{unique_id}"
    query = await _ingest_runet_marker(
        rag_client,
        auth_headers_system,
        unique_id,
        marker,
    )
    plan_json = json.dumps(
        {
            "brief": f"Исследование по маркеру {marker}",
            "sub_questions": ["Что это за документ?"],
            "queries": [query],
            "outline": ["Обзор"],
        },
        ensure_ascii=False,
    )
    reflect_json = json.dumps(
        {"need_more": False, "gap_queries": [], "coverage_note": "Данных достаточно"},
        ensure_ascii=False,
    )
    report_text = "RESEARCH_STREAM_OK\n\n## Обзор\nКлючевой факт."
    await mock_llm_redis(
        [
            {"type": "text", "content": plan_json},
            {"type": "text", "content": reflect_json},
            {"type": "text", "content": report_text},
        ]
    )

    stream_text = await _post_research_stream(
        client,
        unique_id=unique_id,
        content=query,
        variables={"search_providers": ["runet"]},
    )
    ui_events = _collect_ui_events(stream_text)
    event_types = [event_type for event_type, _payload in ui_events]

    assert "search/research/plan_ready" in event_types
    assert event_types.count("search/research/search_ready") >= 1
    assert "search/research/reflection_ready" in event_types
    assert "search/serp/completed" in event_types

    plan_payload = next(payload for et, payload in ui_events if et == "search/research/plan_ready")
    assert plan_payload["kind"] == "public_search_research_update"
    assert plan_payload["phase"] == "plan"
    assert plan_payload["mode"] == "research"
    assert plan_payload["brief"] == f"Исследование по маркеру {marker}"
    assert plan_payload["queries"] == [query]

    search_payloads = [payload for et, payload in ui_events if et == "search/research/search_ready"]
    first_search = search_payloads[0]
    assert first_search["phase"] == "search"
    assert first_search["iteration"] == 0
    assert first_search["queries"][0]["error"] == ""
    assert first_search["queries"][0]["count"] >= 1, first_search["queries"]
    assert first_search["found"] >= 1, first_search

    reflect_payload = next(
        payload for et, payload in ui_events if et == "search/research/reflection_ready"
    )
    assert reflect_payload["phase"] == "reflect"
    assert reflect_payload["need_more"] is False
    assert reflect_payload["coverage_note"] == "Данных достаточно"

    completed_payload = next(payload for et, payload in ui_events if et == "search/serp/completed")
    assert completed_payload["kind"] == "public_search_research_report"
    assert completed_payload["mode"] == "research"
    assert "RESEARCH_STREAM_OK" in completed_payload["report"]


@pytest.mark.asyncio
@pytest.mark.real_taskiq
@pytest.mark.timeout(240, func_only=True)
async def test_public_search_research_branch_runs_second_search_wave(
    search_service,
    rag_service,
    rag_client,
    rag_worker,
    provider_litserve_service,
    auth_headers_system,
    client,
    mock_llm_redis,
    mock_llm_capture,
    unique_id,
) -> None:
    _ = search_service, rag_service, rag_worker, provider_litserve_service
    marker_a = f"public_search_research_wave_a_{unique_id}"
    marker_b = f"public_search_research_wave_b_{unique_id}"
    query_a = await _ingest_runet_marker(
        rag_client,
        auth_headers_system,
        f"{unique_id}-a",
        marker_a,
    )
    gap_query = await _ingest_runet_marker(
        rag_client,
        auth_headers_system,
        f"{unique_id}-b",
        marker_b,
    )

    plan_json = json.dumps(
        {
            "brief": f"Исследование по маркерам {marker_a}",
            "sub_questions": ["Что это за документ A?"],
            "queries": [query_a],
            "outline": ["Обзор", "Детали"],
        },
        ensure_ascii=False,
    )
    reflect_json = json.dumps(
        {
            "need_more": True,
            "gap_queries": [gap_query],
            "coverage_note": "Нужны дополнительные данные по маркеру B",
        },
        ensure_ascii=False,
    )
    report_text = (
        "RESEARCH_SECOND_WAVE_OK\n\n## Обзор\nОтчёт после второй волны поиска.\n\n"
        "## Что дальше\n- Проверить дополнительные источники."
    )
    await mock_llm_redis(
        [
            {"type": "text", "content": plan_json},
            {"type": "text", "content": reflect_json},
            {"type": "text", "content": report_text},
        ]
    )

    stream_text = await _post_research_stream(
        client,
        unique_id=unique_id,
        content=query_a,
        variables={"search_providers": ["runet"]},
    )
    ui_events = _collect_ui_events(stream_text)
    search_payloads = [payload for et, payload in ui_events if et == "search/research/search_ready"]
    assert len(search_payloads) >= 2
    assert search_payloads[0]["iteration"] == 0
    assert search_payloads[0]["queries"][0]["error"] == ""
    assert search_payloads[0]["queries"][0]["count"] >= 1, search_payloads[0]["queries"]
    assert search_payloads[0]["found"] >= 1, search_payloads[0]
    assert search_payloads[1]["iteration"] == 1
    assert search_payloads[1]["queries"][0]["query"] == gap_query
    assert search_payloads[1]["queries"][0]["error"] == ""
    assert search_payloads[1]["queries"][0]["count"] >= 1, search_payloads[1]["queries"]
    assert search_payloads[1]["found"] >= 1, search_payloads[1]

    reflect_payload = next(
        payload for et, payload in ui_events if et == "search/research/reflection_ready"
    )
    assert reflect_payload["need_more"] is True
    assert reflect_payload["gap_queries"] == [gap_query]
    assert reflect_payload["coverage_note"] == "Нужны дополнительные данные по маркеру B"

    completed_payload = next(payload for et, payload in ui_events if et == "search/serp/completed")
    assert completed_payload["kind"] == "public_search_research_report"
    assert completed_payload["mode"] == "research"
    assert completed_payload["coverage_note"] == "Нужны дополнительные данные по маркеру B"
    assert completed_payload["iterations"] == 1
    assert "RESEARCH_SECOND_WAVE_OK" in completed_payload["report"]

    calls = await mock_llm_capture()
    prompt_text = "\n".join(_captured_text(call) for call in calls)
    assert marker_a in prompt_text
    assert "Humanitec Deep Research" in prompt_text
