"""Интеграция sandbox services без monkeypatch."""

from __future__ import annotations

import ast
import importlib
import json
from pathlib import Path
from typing import cast
from uuid import uuid4

import pytest
from httpx import AsyncClient

from apps.flows.tools.builtin_specs import BUILTIN_TOOL_SPECS
from core.capabilities import (
    CAPABILITY_LANGUAGES,
    CapabilityExecutionContext,
    CapabilityExecutionTokenClaims,
    CapabilityLanguage,
    CapabilityManifest,
    CodeExecutionKind,
    CodeExecutionRequest,
    CodeValidationRequest,
    JsonObject,
    execution_token_exp,
    issue_execution_token,
)

pytestmark = pytest.mark.timeout(180)
TOOLS_PACKAGE_ROOT = Path(__file__).resolve().parents[2] / "apps" / "flows" / "tools"
BUNDLES_ROOT = Path(__file__).resolve().parents[2] / "apps" / "flows" / "bundles"

RUNNER_BY_LANGUAGE: dict[CapabilityLanguage, tuple[str, str]] = {
    "python": ("code_runner_python", "/code-runner-python/api/v1/execute"),
    "javascript": ("code_runner_node", "/code-runner-node/api/v1/execute"),
    "typescript": ("code_runner_node", "/code-runner-node/api/v1/execute"),
    "go": ("code_runner_go", "/code-runner-go/api/v1/execute"),
    "csharp": ("code_runner_csharp", "/code-runner-csharp/api/v1/execute"),
}

RUNNER_VALIDATE_BY_LANGUAGE: dict[CapabilityLanguage, tuple[str, str]] = {
    "python": ("code_runner_python", "/code-runner-python/api/v1/validate"),
    "javascript": ("code_runner_node", "/code-runner-node/api/v1/validate"),
    "typescript": ("code_runner_node", "/code-runner-node/api/v1/validate"),
    "go": ("code_runner_go", "/code-runner-go/api/v1/validate"),
    "csharp": ("code_runner_csharp", "/code-runner-csharp/api/v1/validate"),
}


def _documented_builtin_tool_ids() -> set[str]:
    tool_ids: set[str] = set()
    for module_name, attr_name in BUILTIN_TOOL_SPECS:
        tool = getattr(importlib.import_module(module_name), attr_name)
        if getattr(tool, "listed_in_platform_tool_docs", True):
            tool_ids.add(tool.name)
    return tool_ids


def _decorated_tool_specs() -> set[tuple[str, str]]:
    specs: set[tuple[str, str]] = set()
    for path in sorted(TOOLS_PACKAGE_ROOT.glob("*.py")):
        if path.name in {"__init__.py", "builtin_specs.py"}:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        module_name = f"apps.flows.tools.{path.stem}"
        for node in tree.body:
            if not isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
                continue
            for decorator in node.decorator_list:
                if isinstance(decorator, ast.Call) and getattr(decorator.func, "id", None) == "tool":
                    specs.add((module_name, node.name))
                    break
    return specs


def test_builtin_tool_specs_include_every_decorated_tool() -> None:
    assert set(BUILTIN_TOOL_SPECS) == _decorated_tool_specs()


def _go_exported_name(raw: str) -> str:
    parts: list[str] = []
    current: list[str] = []
    for ch in raw:
        if ch.isalnum():
            current.append(ch)
        elif current:
            parts.append("".join(current))
            current = []
    if current:
        parts.append("".join(current))
    if not parts:
        return "Call"
    name = "".join(part[:1].upper() + part[1:] for part in parts)
    if name[:1].isdigit():
        name = f"Call{name}"
    return name


def _sdk_pairs(manifest: dict[str, object]) -> list[tuple[str, str]]:
    capabilities = manifest.get("capabilities")
    assert isinstance(capabilities, list)
    pairs: set[tuple[str, str]] = set()
    for item in capabilities:
        assert isinstance(item, dict)
        raw_name = item["name"]
        assert isinstance(raw_name, str)
        default_namespace, default_method = raw_name.split(".", 1)
        namespace = item.get("sdk_namespace")
        method = item.get("sdk_method")
        pairs.add(
            (
                namespace if isinstance(namespace, str) and namespace else default_namespace,
                method if isinstance(method, str) and method else default_method,
            )
        )
    return sorted(pairs)


def _sdk_presence_code(language: str, pairs: list[tuple[str, str]]) -> str:
    if language == "python":
        lines = ["async def inspect_sdk(args, state):", "    checks = []"]
        for namespace, method in pairs:
            lines.append(f"    _ = {namespace}.{method}")
            lines.append(f"    checks.append({namespace + '.' + method!r})")
        lines.append("    return {'sdk_method_count': len(checks)}")
        return "\n".join(lines) + "\n"

    if language in {"javascript", "typescript"}:
        lines = ["async function inspectSdk(args, state) {", "  const checks = [];"]
        for namespace, method in pairs:
            label = namespace + "." + method
            lines.append(
                f"  if (typeof globalThis[{namespace!r}][{method!r}] !== 'function') "
                f"throw new Error('missing SDK method: {label}');"
            )
            lines.append(f"  checks.push({label!r});")
        lines.append("  return {sdk_method_count: checks.length};")
        lines.append("}")
        return "\n".join(lines) + "\n"

    if language == "go":
        lines = [
            "package main",
            "",
            "func InspectSDK(args map[string]any, state map[string]any) (any, error) {",
            "    checks := 0",
        ]
        for namespace, method in pairs:
            lines.append(f"    _ = {namespace}.{_go_exported_name(method)}")
            lines.append("    checks++")
        lines.append('    return map[string]any{"sdk_method_count": checks}, nil')
        lines.append("}")
        return "\n".join(lines) + "\n"

    if language == "csharp":
        lines = [
            "using System.Collections.Generic;",
            "using System;",
            "using System.Threading.Tasks;",
            "",
            "async Task<object?> InspectSDK(Dictionary<string, object?> args, Dictionary<string, object?> state)",
            "{",
            "    var checks = 0;",
        ]
        for index, (namespace, method) in enumerate(pairs):
            lines.append(
                "    Func<Dictionary<string, object?>, Task<object?>> "
                f"methodRef{index} = {namespace}.{_go_exported_name(method)};"
            )
            lines.append(f"    _ = methodRef{index};")
            lines.append("    checks++;")
        lines.append('    return new Dictionary<string, object?> { ["sdk_method_count"] = checks };')
        lines.append("}")
        return "\n".join(lines) + "\n"

    raise AssertionError(f"Unsupported language: {language}")


def _execution_context() -> CapabilityExecutionContext:
    claims = CapabilityExecutionTokenClaims(
        company_id="system",
        user_id="test_user",
        flow_id="test_flow",
        branch_id="main",
        session_id="test_flow:test_context",
        task_id="test_task",
        context_id="test_context",
        request_id="test-request-id",
        exp=execution_token_exp(300),
    )
    return CapabilityExecutionContext(
        execution_token=issue_execution_token(claims),
        company_id=claims.company_id,
        user_id=claims.user_id,
        flow_id=claims.flow_id,
        branch_id=claims.branch_id,
        session_id=claims.session_id,
        task_id=claims.task_id,
        context_id=claims.context_id,
        request_id=claims.request_id,
        trace_id="test-trace-id",
    )


def _request(
    language: CapabilityLanguage,
    code: str,
    *,
    entrypoint: str | None = None,
    kind: CodeExecutionKind = "node",
    args: JsonObject | None = None,
    state: JsonObject | None = None,
) -> dict[str, object]:
    request = CodeExecutionRequest(
        kind=kind,
        language=language,
        code=code,
        entrypoint=entrypoint,
        wall_time_limit_seconds=30,
        args=args or {"x": 41},
        state=state or {},
        context=_execution_context(),
        capability_manifest=CapabilityManifest(version="test", capabilities=[]),
    )
    return request.model_dump(mode="json")


def _validation_request(
    language: CapabilityLanguage,
    code: str,
    *,
    entrypoint: str | None = None,
    kind: CodeExecutionKind = "node",
) -> dict[str, object]:
    request = CodeValidationRequest(
        kind=kind,
        language=language,
        code=code,
        entrypoint=entrypoint,
        wall_time_limit_seconds=30,
        context=_execution_context(),
        capability_manifest=CapabilityManifest(version="test", capabilities=[]),
    )
    return request.model_dump(mode="json")


def _walk_inline_code_tools(value: object) -> list[dict[str, object]]:
    found: list[dict[str, object]] = []
    if isinstance(value, dict):
        if isinstance(value.get("tool_id"), str) and isinstance(value.get("code"), str):
            found.append(value)
        for child in value.values():
            found.extend(_walk_inline_code_tools(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(_walk_inline_code_tools(child))
    return found


def _bundle_inline_code_tools(*relative_paths: str) -> dict[str, dict[str, object]]:
    tools: dict[str, dict[str, object]] = {}
    for relative_path in relative_paths:
        payload = json.loads((BUNDLES_ROOT / relative_path).read_text(encoding="utf-8"))
        for tool in _walk_inline_code_tools(payload):
            tool_id = tool.get("tool_id")
            if isinstance(tool_id, str):
                tools[tool_id] = tool
    return tools


def _bundle_tool_args(tool_id: str) -> JsonObject:
    samples: dict[str, JsonObject] = {
        "format_greeting": {"name": "Ada", "style": "formal"},
        "react_profile_card_js": {"name": "Ada", "role": "admin"},
        "react_priority_summary_ts": {"topic": "Billing", "priority": 9},
        "react_order_score_go": {"amount": 1500},
        "react_status_card_csharp": {"status": "open"},
        "graph_extract_topic_python": {"text": "hello graph route"},
        "graph_route_note_js": {"note": "custom note"},
        "graph_escalation_hint_ts": {"severity": 9},
        "graph_order_reference_go": {"number": "42"},
        "graph_reply_footer_csharp": {"channel": "chat"},
    }
    return samples[tool_id]


@pytest.mark.asyncio
async def test_capability_manifest_and_docs_are_served_by_gateway(sandbox_services) -> None:
    async with AsyncClient(timeout=30.0) as client:
        manifest_response = await client.get(
            f"{sandbox_services['capability_gateway']}/capability-gateway/api/v1/capabilities/manifest",
            headers={"X-Request-Id": "test-request-id", "X-Trace-Id": "test-trace-id"},
        )
        manifest_response.raise_for_status()
        manifest = manifest_response.json()
        assert manifest["version"] == "capabilities.v1"
        capability_names = {item["name"] for item in manifest["capabilities"]}
        tool_manifest_response = await client.get(
            f"{sandbox_services['flows']}/flows/api/v1/tool-runtime/manifest",
            headers={"X-Request-Id": "test-request-id", "X-Trace-Id": "test-trace-id"},
        )
        tool_manifest_response.raise_for_status()
        tool_capability_names = {
            item["name"] for item in tool_manifest_response.json()["capabilities"]
        }
        builtin_tool_capability_names = {
            f"tools.{tool_id}" for tool_id in _documented_builtin_tool_ids()
        }
        assert capability_names >= {
            "files.create",
            "files.get_bytes",
            "http.request",
            "text.summarize",
            "text.format_markdown",
            "voice.transcribe_audio",
            "voice.synthesize_speech",
            "tools.calculator",
        }
        assert capability_names >= tool_capability_names
        assert capability_names >= builtin_tool_capability_names
        assert "tools.call" not in capability_names

        for language in CAPABILITY_LANGUAGES:
            docs_response = await client.get(
                f"{sandbox_services['capability_gateway']}/capability-gateway/api/v1/capabilities/documentation",
                params={"language": language},
                headers={"X-Request-Id": "test-request-id", "X-Trace-Id": "test-trace-id"},
            )
            docs_response.raise_for_status()
            docs_payload = docs_response.json()
            markdown = docs_payload["markdown"]
            assert "Capability API" in markdown
            assert f"Language: `{language}`" in markdown
            assert "### Parameters" in markdown
            assert "### Returns" in markdown
            assert "Input JSON Schema" in markdown
            assert "Output JSON Schema" in markdown
            for capability_name in capability_names:
                assert f"## `{capability_name}`" in markdown
            capability_docs = {
                item["capability_name"]: item
                for item in docs_payload["capabilities"]
            }
            namespace_docs = {item["name"]: item for item in docs_payload["namespaces"]}
            assert capability_docs.keys() >= capability_names
            assert "files" in namespace_docs
            assert "tools" in namespace_docs
            assert "flow_state" in namespace_docs
            files_create = capability_docs["files.create"]
            assert {field["path"] for field in files_create["input_fields"]} >= {
                "content",
                "original_name",
                "content_mode",
            }
            assert "content_mode" in files_create["documentation"]
            assert files_create["signature"]
            assert files_create["insert_text"]
            if language == "go":
                assert "func run(args map[string]any, state map[string]any) (any, error)" in markdown
                assert "tools.Calculator(" in markdown
                assert "files.Create(" in markdown
                assert "http.Request(" in markdown
                assert files_create["label"] == "files.Create"
                assert "files.Create(map[string]any" in files_create["insert_text"]
            elif language == "csharp":
                assert "async Task<object?> run(Dictionary<string, object?> args, Dictionary<string, object?> state)" in markdown
                assert "await tools.Calculator(" in markdown
                assert "await files.Create(" in markdown
                assert "await http.Request(" in markdown
                assert files_create["label"] == "files.Create"
                assert "await files.Create(new Dictionary<string, object?>" in files_create["insert_text"]
            elif language == "python":
                assert "async def run(args, state):" in markdown
                assert "await tools.calculator(" in markdown
                assert "await files.create(" in markdown
                assert "await http.request(" in markdown
                assert files_create["label"] == "files.create"
                assert "await files.create(" in files_create["insert_text"]
            else:
                assert "async function run(args, state)" in markdown
                assert "export async function" not in markdown
                assert "await tools.calculator(" in markdown
                assert "await files.create(" in markdown
                assert "await http.request(" in markdown
                assert files_create["label"] == "files.create"
                assert "await files.create({" in files_create["insert_text"]


@pytest.mark.asyncio
async def test_all_manifest_capabilities_have_sdk_methods_in_every_language(
    sandbox_services,
    flows_client_http,
    auth_headers_system,
) -> None:
    async with AsyncClient(timeout=30.0) as client:
        manifest_response = await client.get(
            f"{sandbox_services['capability_gateway']}/capability-gateway/api/v1/capabilities/manifest",
            headers={"X-Request-Id": "test-request-id", "X-Trace-Id": "test-trace-id"},
        )
        manifest_response.raise_for_status()
        pairs = _sdk_pairs(manifest_response.json())

    assert pairs

    for language in CAPABILITY_LANGUAGES:
        response = await flows_client_http.post(
            "/flows/api/v1/code/execute",
            json={
                "node_type": "code",
                "node_config": {
                    "type": "code",
                    "language": language,
                    "code": _sdk_presence_code(language, pairs),
                },
                "state": {},
            },
            headers=auth_headers_system,
            timeout=120.0,
        )
        response.raise_for_status()
        body = response.json()
        assert body["success"] is True, body
        assert body["output_state"]["sdk_method_count"] == len(pairs)


@pytest.mark.asyncio
async def test_python_node_typescript_and_go_runners_execute_real_code(sandbox_services) -> None:
    cases = [
        (
            "code_runner_python",
            "/code-runner-python/api/v1/execute",
            _request(
                "python",
                "async def run(args, state):\n"
                "    state['x'] = args['x'] + 1\n"
                "    return {'ok': state['x']}\n",
            ),
        ),
        (
            "code_runner_node",
            "/code-runner-node/api/v1/execute",
            _request(
                "typescript",
                "async function run(args: {x: number}, state: Record<string, unknown>) {\n"
                "  state.x = args.x + 1;\n"
                "  return {ok: state.x};\n"
                "}\n",
            ),
        ),
        (
            "code_runner_go",
            "/code-runner-go/api/v1/execute",
            _request(
                "go",
                "package main\n\n"
                "func Run(args map[string]any, state map[string]any) (any, error) {\n"
                "    state[\"x\"] = args[\"x\"].(float64) + 1\n"
                "    return map[string]any{\"ok\": state[\"x\"]}, nil\n"
                "}\n",
            ),
        ),
        (
            "code_runner_csharp",
            "/code-runner-csharp/api/v1/execute",
            _request(
                "csharp",
                "using System.Collections.Generic;\n"
                "using System.Threading.Tasks;\n\n"
                "Task<object?> Run(Dictionary<string, object?> args, Dictionary<string, object?> state)\n"
                "{\n"
                "    state[\"x\"] = System.Convert.ToInt64(args[\"x\"]) + 1;\n"
                "    return Task.FromResult<object?>(new Dictionary<string, object?> { [\"ok\"] = state[\"x\"] });\n"
                "}\n",
            ),
        ),
    ]
    async with AsyncClient(timeout=60.0) as client:
        for service_name, path, payload in cases:
            response = await client.post(
                f"{sandbox_services[service_name]}{path}",
                json=payload,
                headers={"X-Request-Id": "test-request-id", "X-Trace-Id": "test-trace-id"},
            )
            response.raise_for_status()
            body = response.json()
            assert body["status"] == "completed"
            assert body["result"] == {"ok": 42}
            assert body["state"] == {"x": 42}


@pytest.mark.asyncio
async def test_runners_validate_code_without_user_execution(sandbox_services) -> None:
    valid_cases = [
        (
            "python",
            "raise RuntimeError('must not run during validation')\n\n"
            "async def run(args, state):\n"
            "    return {'ok': True}\n",
        ),
        (
            "javascript",
            "throw new Error('must not run during validation');\n\n"
            "async function run(args, state) {\n"
            "  return {ok: true};\n"
            "}\n",
        ),
        (
            "typescript",
            "type Args = { ok: boolean };\n"
            "async function run(args: Args, state: Record<string, unknown>) {\n"
            "  return {ok: args.ok};\n"
            "}\n",
        ),
        (
            "go",
            "package main\n\n"
            "func Run(args map[string]any, state map[string]any) (any, error) {\n"
            "    return map[string]any{\"ok\": true}, nil\n"
            "}\n",
        ),
        (
            "csharp",
            "using System.Collections.Generic;\n"
            "using System.Threading.Tasks;\n\n"
            "Task<object?> Run(Dictionary<string, object?> args, Dictionary<string, object?> state)\n"
            "{\n"
            "    return Task.FromResult<object?>(new Dictionary<string, object?> { [\"ok\"] = true });\n"
            "}\n",
        ),
    ]
    async with AsyncClient(timeout=60.0) as client:
        for language, code in valid_cases:
            capability_language = cast(CapabilityLanguage, language)
            service_name, path = RUNNER_VALIDATE_BY_LANGUAGE[capability_language]
            response = await client.post(
                f"{sandbox_services[service_name]}{path}",
                json=_validation_request(capability_language, code),
                headers={"X-Request-Id": "test-request-id", "X-Trace-Id": "test-trace-id"},
            )
            response.raise_for_status()
            body = response.json()
            assert body["valid"] is True, {language: body}

        service_name, path = RUNNER_VALIDATE_BY_LANGUAGE["typescript"]
        response = await client.post(
            f"{sandbox_services[service_name]}{path}",
            json=_validation_request("typescript", "async function run(args: {x: number}) {\n"),
            headers={"X-Request-Id": "test-request-id", "X-Trace-Id": "test-trace-id"},
        )
        response.raise_for_status()
        body = response.json()
        assert body["valid"] is False
        assert body["error"]["service"] == "code_runner_node"
        assert body["error"]["stage"] == "compile"


@pytest.mark.asyncio
async def test_flows_code_validate_go_uses_sandbox_runner(
    flows_client_http,
    auth_headers_system,
) -> None:
    response = await flows_client_http.post(
        "/flows/api/v1/code/validate",
        json={
            "language": "go",
            "node_type": "code",
            "code": (
                "package main\n\n"
                "func ScoreOrder(args map[string]any, state map[string]any) (any, error) {\n"
                "    amount := 0.0\n"
                "    if raw, ok := args[\"amount\"].(float64); ok {\n"
                "        amount = raw\n"
                "    }\n"
                "    tier := \"standard\"\n"
                "    if amount >= 10000 {\n"
                "        tier = \"enterprise\"\n"
                "    } else if amount >= 1000 {\n"
                "        tier = \"priority\"\n"
                "    }\n"
                "    state[\"react_order_tier\"] = tier\n"
                "    return map[string]any{\"language\": \"go\", \"amount\": amount, \"tier\": tier}, nil\n"
                "}\n"
            ),
        },
        headers=auth_headers_system,
        timeout=120.0,
    )
    response.raise_for_status()
    body = response.json()
    assert body["valid"] is True, body
    assert body["service"] is None
    assert body["exception_type"] is None


@pytest.mark.asyncio
async def test_python_runner_does_not_evaluate_annotations_at_load(sandbox_services) -> None:
    payload = _request(
        "python",
        "async def calculate(args: MissingArgsAlias, state) -> JsonDict:\n"
        "    state['value'] = args['x'] + 1\n"
        "    return {'ok': state['value']}\n",
    )
    async with AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{sandbox_services['code_runner_python']}/code-runner-python/api/v1/execute",
            json=payload,
            headers={"X-Request-Id": "test-request-id", "X-Trace-Id": "test-trace-id"},
        )
    response.raise_for_status()
    body = response.json()
    assert body["status"] == "completed", body
    assert body["result"] == {"ok": 42}
    assert body["state"] == {"value": 42}


@pytest.mark.asyncio
async def test_example_bundles_inline_code_tools_execute_on_declared_languages(
    sandbox_services,
) -> None:
    expected_tool_ids = {
        "format_greeting",
        "react_profile_card_js",
        "react_priority_summary_ts",
        "react_order_score_go",
        "react_status_card_csharp",
        "graph_extract_topic_python",
        "graph_route_note_js",
        "graph_escalation_hint_ts",
        "graph_order_reference_go",
        "graph_reply_footer_csharp",
    }
    tools = _bundle_inline_code_tools(
        "example_react/nodes.json",
        "example_graph/flow.json",
    )
    assert set(tools) >= expected_tool_ids

    async with AsyncClient(timeout=120.0) as client:
        for tool_id in sorted(expected_tool_ids):
            tool = tools[tool_id]
            language = tool.get("language")
            code = tool.get("code")
            assert language in RUNNER_BY_LANGUAGE
            assert isinstance(code, str)
            capability_language = cast(CapabilityLanguage, language)
            service_name, path = RUNNER_BY_LANGUAGE[capability_language]
            payload = _request(
                capability_language,
                code,
                kind="tool",
                args=_bundle_tool_args(tool_id),
                state=cast(
                    JsonObject,
                    {"content": "hello from bundle", "route": "general", "user_name": "Ada"},
                ),
            )
            response = await client.post(
                f"{sandbox_services[service_name]}{path}",
                json=payload,
                headers={"X-Request-Id": "test-request-id", "X-Trace-Id": "test-trace-id"},
            )
            response.raise_for_status()
            body = response.json()
            assert body["status"] == "completed", {tool_id: body}
            if tool_id != "format_greeting":
                assert body["result"]["language"] == language


@pytest.mark.asyncio
async def test_runner_failure_contains_traceback_and_correlation_ids(sandbox_services) -> None:
    payload = _request(
        "javascript",
        "async function run() { throw new Error('boom from js'); }\n",
    )
    async with AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{sandbox_services['code_runner_node']}/code-runner-node/api/v1/execute",
            json=payload,
            headers={"X-Request-Id": "test-request-id", "X-Trace-Id": "test-trace-id"},
        )
    response.raise_for_status()
    body = response.json()
    assert body["status"] == "failed"
    assert body["error"]["message"] == "boom from js"
    assert body["error"]["request_id"] == "test-request-id"
    assert body["error"]["trace_id"] == "test-trace-id"
    assert "Error: boom from js" in body["error"]["traceback"]


@pytest.mark.asyncio
async def test_runners_execute_custom_entrypoint_names(sandbox_services) -> None:
    cases = [
        (
            "code_runner_python",
            "/code-runner-python/api/v1/execute",
            _request(
                "python",
                "async def calculate(args, state):\n"
                "    state['value'] = args['x'] + 1\n"
                "    return {'ok': state['value']}\n",
                entrypoint="calculate",
            ),
        ),
        (
            "code_runner_node",
            "/code-runner-node/api/v1/execute",
            _request(
                "javascript",
                "async function calculate(args, state) {\n"
                "  state.value = args.x + 1;\n"
                "  return {ok: state.value};\n"
                "}\n",
                entrypoint="calculate",
            ),
        ),
        (
            "code_runner_go",
            "/code-runner-go/api/v1/execute",
            _request(
                "go",
                "package main\n\n"
                "func Calculate(args map[string]any, state map[string]any) (any, error) {\n"
                "    state[\"value\"] = args[\"x\"].(float64) + 1\n"
                "    return map[string]any{\"ok\": state[\"value\"]}, nil\n"
                "}\n",
                entrypoint="Calculate",
            ),
        ),
        (
            "code_runner_csharp",
            "/code-runner-csharp/api/v1/execute",
            _request(
                "csharp",
                "using System.Collections.Generic;\n"
                "using System.Threading.Tasks;\n\n"
                "Task<object?> Calculate(Dictionary<string, object?> args, Dictionary<string, object?> state)\n"
                "{\n"
                "    state[\"value\"] = System.Convert.ToInt64(args[\"x\"]) + 1;\n"
                "    return Task.FromResult<object?>(new Dictionary<string, object?> { [\"ok\"] = state[\"value\"] });\n"
                "}\n",
                entrypoint="Calculate",
            ),
        ),
    ]
    async with AsyncClient(timeout=60.0) as client:
        for service_name, path, payload in cases:
            response = await client.post(
                f"{sandbox_services[service_name]}{path}",
                json=payload,
                headers={"X-Request-Id": "test-request-id", "X-Trace-Id": "test-trace-id"},
            )
            response.raise_for_status()
            body = response.json()
            assert body["status"] == "completed"
            assert body["result"] == {"ok": 42}
            assert body["state"] == {"value": 42}


@pytest.mark.asyncio
async def test_all_languages_call_platform_tool_capability_through_public_sdk(
    flows_client_http,
    auth_headers_system,
) -> None:
    cases = [
        (
            "python",
            "async def compute(args, state):\n"
            "    result = await tools.calculator(expression=\"6*7\")\n"
            "    state[\"calc\"] = result\n"
            "    return {\"calc\": result}\n",
        ),
        (
            "javascript",
            "async function compute(args, state) {\n"
            "  const result = await tools.calculator({expression: \"6*7\"});\n"
            "  state.calc = result;\n"
            "  return {calc: result};\n"
            "}\n",
        ),
        (
            "typescript",
            "async function compute(args: Record<string, unknown>, state: Record<string, unknown>) {\n"
            "  const result = await tools.calculator({expression: \"6*7\"});\n"
            "  state.calc = result;\n"
            "  return {calc: result};\n"
            "}\n",
        ),
        (
            "go",
            "package main\n\n"
            "func Compute(args map[string]any, state map[string]any) (any, error) {\n"
            "    result, err := tools.Calculator(map[string]any{\"expression\": \"6*7\"})\n"
            "    if err != nil {\n"
            "        return nil, err\n"
            "    }\n"
            "    state[\"calc\"] = result\n"
            "    return map[string]any{\"calc\": result}, nil\n"
            "}\n",
        ),
        (
            "csharp",
            "using System.Collections.Generic;\n"
            "using System.Threading.Tasks;\n\n"
            "async Task<object?> Compute(Dictionary<string, object?> args, Dictionary<string, object?> state)\n"
            "{\n"
            "    var result = await tools.Calculator(new Dictionary<string, object?> { [\"expression\"] = \"6*7\" });\n"
            "    state[\"calc\"] = result;\n"
            "    return new Dictionary<string, object?> { [\"calc\"] = result };\n"
            "}\n",
        ),
    ]

    for language, code in cases:
        response = await flows_client_http.post(
            "/flows/api/v1/code/execute",
            json={
                "node_type": "code",
                "node_config": {
                    "type": "code",
                    "language": language,
                    "code": code,
                },
                "state": {},
            },
            headers=auth_headers_system,
            timeout=120.0,
        )
        response.raise_for_status()
        body = response.json()
        assert body["success"] is True, body
        assert "42" in body["output_state"]["calc"]


@pytest.mark.asyncio
async def test_go_code_node_calls_python_and_javascript_tools(
    flows_client_http,
    auth_headers_system,
    unique_id,
) -> None:
    python_tool_id = f"{unique_id}_py_tool_{uuid4().hex[:8]}"
    javascript_tool_id = f"{unique_id}_js_tool_{uuid4().hex[:8]}"
    tool_payloads = [
        {
            "tool_id": python_tool_id,
            "title": "Python multiplier",
            "description": "Test Python tool called from Go node through public tools SDK.",
            "language": "python",
            "code": (
                "async def multiply_python(args, state):\n"
                "    value = int(args['value'])\n"
                "    state['python_tool_value'] = value\n"
                "    return {'language': 'python', 'value': value * 2}\n"
            ),
            "parameters_schema": {
                "type": "object",
                "properties": {"value": {"type": "integer"}},
                "required": ["value"],
            },
        },
        {
            "tool_id": javascript_tool_id,
            "title": "JavaScript adder",
            "description": "Test JavaScript tool called from Go node through public tools SDK.",
            "language": "javascript",
            "code": (
                "async function addJavascript(args, state) {\n"
                "  const value = Number(args.value);\n"
                "  state.javascript_tool_value = value;\n"
                "  return {language: 'javascript', value: value + 5};\n"
                "}\n"
            ),
            "parameters_schema": {
                "type": "object",
                "properties": {"value": {"type": "integer"}},
                "required": ["value"],
            },
        },
    ]

    try:
        for payload in tool_payloads:
            response = await flows_client_http.post(
                "/flows/api/v1/tools/",
                json=payload,
                headers=auth_headers_system,
            )
            response.raise_for_status()

        go_code = f'''
package main

func Combine(args map[string]any, state map[string]any) (any, error) {{
    base := state["base"].(float64)
    pyResult, err := tools.Call("{python_tool_id}", map[string]any{{"value": base}})
    if err != nil {{
        return nil, err
    }}
    jsResult, err := tools.Call("{javascript_tool_id}", map[string]any{{"value": base}})
    if err != nil {{
        return nil, err
    }}
    state["go_node_done"] = true
    return map[string]any{{"python_result": pyResult, "javascript_result": jsResult}}, nil
}}
'''

        response = await flows_client_http.post(
            "/flows/api/v1/code/execute",
            json={
                "node_type": "code",
                "node_config": {
                    "type": "code",
                    "language": "go",
                    "code": go_code,
                },
                "state": {"base": 7},
            },
            headers=auth_headers_system,
            timeout=120.0,
        )
        response.raise_for_status()
        body = response.json()
        assert body["success"] is True, body
        output_state = body["output_state"]
        assert output_state["go_node_done"] is True
        assert output_state["python_tool_value"] == 7
        assert output_state["javascript_tool_value"] == 7
        assert output_state["python_result"] == {"language": "python", "value": 14}
        assert output_state["javascript_result"] == {"language": "javascript", "value": 12}
    finally:
        for tool_id in (python_tool_id, javascript_tool_id):
            await flows_client_http.delete(
                f"/flows/api/v1/tools/{tool_id}",
                headers=auth_headers_system,
            )
