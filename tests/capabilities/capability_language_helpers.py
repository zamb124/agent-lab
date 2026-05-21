"""Shared real-service capability checks for every sandbox language."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from httpx import AsyncClient

from core.capabilities import (
    CAPABILITY_LANGUAGES,
    CapabilityExecutionContext,
    CapabilityExecutionTokenClaims,
    CapabilityLanguage,
    CapabilityManifest,
    CodeExecutionRequest,
    execution_token_exp,
    issue_execution_token,
)

STATIC_PLATFORM_CAPABILITIES = {
    "channel.send",
    "channel.send_with_buttons",
    "files.create",
    "files.get_bytes",
    "files.get_metadata",
    "files.read",
    "http.delete",
    "http.get",
    "http.head",
    "http.patch",
    "http.post",
    "http.put",
    "http.request",
    "log.debug",
    "log.error",
    "log.info",
    "log.warning",
    "platform.request",
    "state.add_agent_message",
    "state.add_user_message",
    "state.extract_json",
    "state.find_file",
    "state.get_files",
    "state.get_messages",
    "state.get_nested",
    "state.get_tool_result",
    "state.get_user",
    "state.merge",
    "state.pop_ui_events",
    "state.push_ui_event",
    "state.push_ui_events",
    "state.set_nested",
    "text.format_markdown",
    "text.summarize",
    "trace.event",
    "voice.synthesize_speech",
    "voice.transcribe_audio",
}
INTERRUPT_PLATFORM_CAPABILITIES = {"flow.ask_user"}

EXPECTED_FILE_BASE64 = "Y2FwYWJpbGl0eSBzbW9rZQ=="
RUNNER_ENDPOINTS = {
    "python": ("code_runner_python", "/code-runner-python/api/v1/execute"),
    "javascript": ("code_runner_node", "/code-runner-node/api/v1/execute"),
    "typescript": ("code_runner_node", "/code-runner-node/api/v1/execute"),
    "go": ("code_runner_go", "/code-runner-go/api/v1/execute"),
    "csharp": ("code_runner_csharp", "/code-runner-csharp/api/v1/execute"),
}


def go_exported_name(raw: str) -> str:
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


def sdk_pairs(manifest: Mapping[str, object]) -> list[tuple[str, str]]:
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


def sdk_presence_code(language: str, pairs: list[tuple[str, str]]) -> str:
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
            lines.append(f"    _ = {namespace}.{go_exported_name(method)}")
            lines.append("    checks++")
        lines.append('    return map[string]any{"sdk_method_count": checks}, nil')
        lines.append("}")
        return "\n".join(lines) + "\n"

    if language == "csharp":
        lines = [
            "using System;",
            "using System.Collections.Generic;",
            "using System.Threading.Tasks;",
            "",
            "async Task<object?> InspectSDK(Dictionary<string, object?> args, Dictionary<string, object?> state)",
            "{",
            "    var checks = 0;",
        ]
        for index, (namespace, method) in enumerate(pairs):
            lines.append(
                "    Func<Dictionary<string, object?>, Task<object?>> "
                f"methodRef{index} = {namespace}.{go_exported_name(method)};"
            )
            lines.append(f"    _ = methodRef{index};")
            lines.append("    checks++;")
        lines.append('    return new Dictionary<string, object?> { ["sdk_method_count"] = checks };')
        lines.append("}")
        return "\n".join(lines) + "\n"

    raise AssertionError(f"Unsupported language: {language}")


def static_capability_code(language: str) -> str:
    if language == "python":
        return """
async def run(args, state):
    results = {}
    async def call(name, kwargs):
        result = await capability(name, **kwargs)
        results[name] = result
        return result

    created = await call("files.create", {
        "content": "capability smoke",
        "original_name": state["file_name"],
        "content_mode": "raw",
    })
    results["files.create"] = created["file_id"]
    file_bytes = await call("files.get_bytes", {"file_id": created["file_id"]})
    results["files.get_bytes"] = file_bytes["content_base64"]
    metadata = await call("files.get_metadata", {"file_id": created["file_id"]})
    results["files.get_metadata"] = metadata["file_id"]
    read_result = await call("files.read", {"file_id": created["file_id"]})
    results["files.read"] = read_result["pages"][0]["text"]
    http_result = await call("http.request", {"method": "GET", "url": state["manifest_url"], "timeout_seconds": 10})
    results["http.request"] = http_result["status_code"]
    for method in ["get", "post", "put", "patch", "delete", "head"]:
        payload = {"url": state["echo_url"], "timeout_seconds": 10}
        if method in {"post", "put", "patch"}:
            payload["json"] = {"method": method}
        http_method_result = await call(f"http.{method}", payload)
        results[f"http.{method}"] = http_method_result["status_code"]
    platform_result = await call("platform.request", {
        "service": "capability_gateway",
        "method": "GET",
        "path": "/capability-gateway/api/v1/capabilities/manifest",
        "timeout_seconds": 10,
    })
    results["platform.request"] = platform_result["version"]
    for level in ["debug", "info", "warning", "error"]:
        log_result = await call(f"log.{level}", {"message": f"capability {level}", "fields": {"language": "python"}})
        results[f"log.{level}"] = log_result["logged"]
    nested = await call("state.get_nested", {"path": "nested.value", "default": "missing"})
    results["state.get_nested"] = nested
    set_nested = await call("state.set_nested", {"path": "nested.value", "value": "updated"})
    results["state.set_nested"] = set_nested["value"]
    merge = await call("state.merge", {"updates": {"merged": {"ok": True}}})
    results["state.merge"] = merge["state"]["merged"]["ok"]
    files_state = await call("state.get_files", {})
    results["state.get_files"] = len(files_state)
    found_file = await call("state.find_file", {"name": "state-file.txt"})
    results["state.find_file"] = found_file["name"]
    user = await call("state.get_user", {})
    results["state.get_user"] = user["id"]
    tool_result = await call("state.get_tool_result", {"tool_name": "seed_tool"})
    results["state.get_tool_result"] = tool_result["ok"]
    messages_before = await call("state.get_messages", {})
    results["state.get_messages"] = len(messages_before)
    user_message = await call("state.add_user_message", {"content": "hello user"})
    results["state.add_user_message"] = user_message["role"]
    agent_message = await call("state.add_agent_message", {"content": "hello agent"})
    results["state.add_agent_message"] = agent_message["role"]
    ui_event = await call("state.push_ui_event", {"event_type": "capability.single", "payload": {"ok": True}})
    results["state.push_ui_event"] = ui_event["type"]
    ui_events = await call("state.push_ui_events", {"events": [{"type": "capability.batch", "payload": {"ok": True}}]})
    results["state.push_ui_events"] = len(ui_events)
    popped = await call("state.pop_ui_events", {})
    results["state.pop_ui_events"] = len(popped)
    extracted = await call("state.extract_json", {"text": "```json\\n{\\"ok\\": true}\\n```"})
    results["state.extract_json"] = extracted["ok"]
    channel_sent = await call("channel.send", {"content": "queued message"})
    results["channel.send"] = channel_sent["queued"]
    channel_buttons = await call("channel.send_with_buttons", {"content": "queued buttons", "buttons": ["A", "B"]})
    results["channel.send_with_buttons"] = channel_buttons["queued"]
    trace_event = await call("trace.event", {"event_type": "capability.test", "attributes": {"language": "python"}})
    results["trace.event"] = trace_event["recorded"]
    summary = await call("text.summarize", {
        "text": "Capability smoke text",
        "provider": "mock",
        "model": "mock-gpt-4",
        "max_output_tokens": 32,
    })
    results["text.summarize"] = summary["summary"]
    markdown = await call("text.format_markdown", {
        "text": "Title\\nItem one",
        "provider": "mock",
        "model": "mock-gpt-4",
        "max_chunk_chars": 512,
    })
    results["text.format_markdown"] = markdown["markdown"]
    speech = await call("voice.synthesize_speech", {
        "text": "Capability smoke speech",
        "provider": "mock",
        "response_format": "wav",
        "file_name": state["speech_file_name"],
    })
    results["voice.synthesize_speech"] = speech["file_id"]
    transcript = await call("voice.transcribe_audio", {"file_id": speech["file_id"], "provider": "mock", "language": "ru"})
    results["voice.transcribe_audio"] = transcript["text"]
    state["capability_results"] = results
    return {"capability_results": results}
"""

    if language in {"javascript", "typescript"}:
        return """
async function run(args, state) {
  const results = {};
  async function call(name, kwargs) {
    const result = await capability(name, kwargs);
    results[name] = result;
    return result;
  }
  const created = await call("files.create", {
    content: "capability smoke",
    original_name: state.file_name,
    content_mode: "raw",
  });
  results["files.create"] = created.file_id;
  const fileBytes = await call("files.get_bytes", {file_id: created.file_id});
  results["files.get_bytes"] = fileBytes.content_base64;
  const metadata = await call("files.get_metadata", {file_id: created.file_id});
  results["files.get_metadata"] = metadata.file_id;
  const readResult = await call("files.read", {file_id: created.file_id});
  results["files.read"] = readResult.pages[0].text;
  const httpResult = await call("http.request", {method: "GET", url: state.manifest_url, timeout_seconds: 10});
  results["http.request"] = httpResult.status_code;
  for (const method of ["get", "post", "put", "patch", "delete", "head"]) {
    const payload = {url: state.echo_url, timeout_seconds: 10};
    if (["post", "put", "patch"].includes(method)) payload.json = {method};
    const httpMethodResult = await call(`http.${method}`, payload);
    results[`http.${method}`] = httpMethodResult.status_code;
  }
  const platformResult = await call("platform.request", {
    service: "capability_gateway",
    method: "GET",
    path: "/capability-gateway/api/v1/capabilities/manifest",
    timeout_seconds: 10,
  });
  results["platform.request"] = platformResult.version;
  for (const level of ["debug", "info", "warning", "error"]) {
    const logResult = await call(`log.${level}`, {message: `capability ${level}`, fields: {language: "javascript"}});
    results[`log.${level}`] = logResult.logged;
  }
  results["state.get_nested"] = await call("state.get_nested", {path: "nested.value", default: "missing"});
  results["state.set_nested"] = (await call("state.set_nested", {path: "nested.value", value: "updated"})).value;
  results["state.merge"] = (await call("state.merge", {updates: {merged: {ok: true}}})).state.merged.ok;
  results["state.get_files"] = (await call("state.get_files", {})).length;
  results["state.find_file"] = (await call("state.find_file", {name: "state-file.txt"})).name;
  results["state.get_user"] = (await call("state.get_user", {})).id;
  results["state.get_tool_result"] = (await call("state.get_tool_result", {tool_name: "seed_tool"})).ok;
  results["state.get_messages"] = (await call("state.get_messages", {})).length;
  results["state.add_user_message"] = (await call("state.add_user_message", {content: "hello user"})).role;
  results["state.add_agent_message"] = (await call("state.add_agent_message", {content: "hello agent"})).role;
  results["state.push_ui_event"] = (await call("state.push_ui_event", {event_type: "capability.single", payload: {ok: true}})).type;
  results["state.push_ui_events"] = (await call("state.push_ui_events", {events: [{type: "capability.batch", payload: {ok: true}}]})).length;
  results["state.pop_ui_events"] = (await call("state.pop_ui_events", {})).length;
  results["state.extract_json"] = (await call("state.extract_json", {text: "```json\\n{\\"ok\\": true}\\n```"})).ok;
  results["channel.send"] = (await call("channel.send", {content: "queued message"})).queued;
  results["channel.send_with_buttons"] = (await call("channel.send_with_buttons", {content: "queued buttons", buttons: ["A", "B"]})).queued;
  results["trace.event"] = (await call("trace.event", {event_type: "capability.test", attributes: {language: "javascript"}})).recorded;
  const summary = await call("text.summarize", {
    text: "Capability smoke text",
    provider: "mock",
    model: "mock-gpt-4",
    max_output_tokens: 32,
  });
  results["text.summarize"] = summary.summary;
  const markdown = await call("text.format_markdown", {
    text: "Title\\nItem one",
    provider: "mock",
    model: "mock-gpt-4",
    max_chunk_chars: 512,
  });
  results["text.format_markdown"] = markdown.markdown;
  const speech = await call("voice.synthesize_speech", {
    text: "Capability smoke speech",
    provider: "mock",
    response_format: "wav",
    file_name: state.speech_file_name,
  });
  results["voice.synthesize_speech"] = speech.file_id;
  const transcript = await call("voice.transcribe_audio", {file_id: speech.file_id, provider: "mock", language: "ru"});
  results["voice.transcribe_audio"] = transcript.text;
  state.capability_results = results;
  return {capability_results: results};
}
"""

    if language == "go":
        return """
package main

func Run(args map[string]any, state map[string]any) (any, error) {
    results := map[string]any{}
    call := func(name string, kwargs map[string]any) (any, error) {
        result, err := Capability(name, kwargs)
        if err != nil {
            return nil, err
        }
        results[name] = result
        return result, nil
    }
    callObj := func(name string, kwargs map[string]any) (map[string]any, error) {
        result, err := call(name, kwargs)
        if err != nil {
            return nil, err
        }
        return result.(map[string]any), nil
    }

    created, err := callObj("files.create", map[string]any{
        "content": "capability smoke",
        "original_name": state["file_name"],
        "content_mode": "raw",
    })
    if err != nil {
        return nil, err
    }
    results["files.create"] = created["file_id"]

    fileBytes, err := callObj("files.get_bytes", map[string]any{"file_id": created["file_id"]})
    if err != nil {
        return nil, err
    }
    results["files.get_bytes"] = fileBytes["content_base64"]

    metadata, err := callObj("files.get_metadata", map[string]any{"file_id": created["file_id"]})
    if err != nil {
        return nil, err
    }
    results["files.get_metadata"] = metadata["file_id"]

    readResult, err := callObj("files.read", map[string]any{"file_id": created["file_id"]})
    if err != nil {
        return nil, err
    }
    readPages := readResult["pages"].([]any)
    results["files.read"] = readPages[0].(map[string]any)["text"]

    httpResult, err := callObj("http.request", map[string]any{
        "method": "GET",
        "url": state["manifest_url"],
        "timeout_seconds": 10,
    })
    if err != nil {
        return nil, err
    }
    results["http.request"] = httpResult["status_code"]

    for _, method := range []string{"get", "post", "put", "patch", "delete", "head"} {
        payload := map[string]any{"url": state["echo_url"], "timeout_seconds": 10}
        if method == "post" || method == "put" || method == "patch" {
            payload["json"] = map[string]any{"method": method}
        }
        httpMethodResult, err := callObj("http." + method, payload)
        if err != nil {
            return nil, err
        }
        results["http." + method] = httpMethodResult["status_code"]
    }

    platformResult, err := callObj("platform.request", map[string]any{
        "service": "capability_gateway",
        "method": "GET",
        "path": "/capability-gateway/api/v1/capabilities/manifest",
        "timeout_seconds": 10,
    })
    if err != nil {
        return nil, err
    }
    results["platform.request"] = platformResult["version"]

    for _, level := range []string{"debug", "info", "warning", "error"} {
        logResult, err := callObj("log." + level, map[string]any{
            "message": "capability " + level,
            "fields": map[string]any{"language": "go"},
        })
        if err != nil {
            return nil, err
        }
        results["log." + level] = logResult["logged"]
    }

    nested, err := call("state.get_nested", map[string]any{"path": "nested.value", "default": "missing"})
    if err != nil { return nil, err }
    results["state.get_nested"] = nested
    setNested, err := callObj("state.set_nested", map[string]any{"path": "nested.value", "value": "updated"})
    if err != nil { return nil, err }
    results["state.set_nested"] = setNested["value"]
    merge, err := callObj("state.merge", map[string]any{"updates": map[string]any{"merged": map[string]any{"ok": true}}})
    if err != nil { return nil, err }
    results["state.merge"] = merge["state"].(map[string]any)["merged"].(map[string]any)["ok"]
    filesState, err := call("state.get_files", map[string]any{})
    if err != nil { return nil, err }
    results["state.get_files"] = len(filesState.([]any))
    foundFile, err := callObj("state.find_file", map[string]any{"name": "state-file.txt"})
    if err != nil { return nil, err }
    results["state.find_file"] = foundFile["name"]
    user, err := callObj("state.get_user", map[string]any{})
    if err != nil { return nil, err }
    results["state.get_user"] = user["id"]
    toolResult, err := callObj("state.get_tool_result", map[string]any{"tool_name": "seed_tool"})
    if err != nil { return nil, err }
    results["state.get_tool_result"] = toolResult["ok"]
    messagesBefore, err := call("state.get_messages", map[string]any{})
    if err != nil { return nil, err }
    results["state.get_messages"] = len(messagesBefore.([]any))
    userMessage, err := callObj("state.add_user_message", map[string]any{"content": "hello user"})
    if err != nil { return nil, err }
    results["state.add_user_message"] = userMessage["role"]
    agentMessage, err := callObj("state.add_agent_message", map[string]any{"content": "hello agent"})
    if err != nil { return nil, err }
    results["state.add_agent_message"] = agentMessage["role"]
    uiEvent, err := callObj("state.push_ui_event", map[string]any{"event_type": "capability.single", "payload": map[string]any{"ok": true}})
    if err != nil { return nil, err }
    results["state.push_ui_event"] = uiEvent["type"]
    uiEvents, err := call("state.push_ui_events", map[string]any{"events": []any{map[string]any{"type": "capability.batch", "payload": map[string]any{"ok": true}}}})
    if err != nil { return nil, err }
    results["state.push_ui_events"] = len(uiEvents.([]any))
    popped, err := call("state.pop_ui_events", map[string]any{})
    if err != nil { return nil, err }
    results["state.pop_ui_events"] = len(popped.([]any))
    extracted, err := callObj("state.extract_json", map[string]any{"text": "```json\\n{\\"ok\\": true}\\n```"})
    if err != nil { return nil, err }
    results["state.extract_json"] = extracted["ok"]
    channelSent, err := callObj("channel.send", map[string]any{"content": "queued message"})
    if err != nil { return nil, err }
    results["channel.send"] = channelSent["queued"]
    channelButtons, err := callObj("channel.send_with_buttons", map[string]any{"content": "queued buttons", "buttons": []any{"A", "B"}})
    if err != nil { return nil, err }
    results["channel.send_with_buttons"] = channelButtons["queued"]
    traceEvent, err := callObj("trace.event", map[string]any{"event_type": "capability.test", "attributes": map[string]any{"language": "go"}})
    if err != nil { return nil, err }
    results["trace.event"] = traceEvent["recorded"]

    summary, err := callObj("text.summarize", map[string]any{
        "text": "Capability smoke text",
        "provider": "mock",
        "model": "mock-gpt-4",
        "max_output_tokens": 32,
    })
    if err != nil {
        return nil, err
    }
    results["text.summarize"] = summary["summary"]

    markdown, err := callObj("text.format_markdown", map[string]any{
        "text": "Title\\nItem one",
        "provider": "mock",
        "model": "mock-gpt-4",
        "max_chunk_chars": 512,
    })
    if err != nil {
        return nil, err
    }
    results["text.format_markdown"] = markdown["markdown"]

    speech, err := callObj("voice.synthesize_speech", map[string]any{
        "text": "Capability smoke speech",
        "provider": "mock",
        "response_format": "wav",
        "file_name": state["speech_file_name"],
    })
    if err != nil {
        return nil, err
    }
    results["voice.synthesize_speech"] = speech["file_id"]

    transcript, err := callObj("voice.transcribe_audio", map[string]any{
        "file_id": speech["file_id"],
        "provider": "mock",
        "language": "ru",
    })
    if err != nil {
        return nil, err
    }
    results["voice.transcribe_audio"] = transcript["text"]

    state["capability_results"] = results
    return map[string]any{"capability_results": results}, nil
}
"""

    if language == "csharp":
        return """
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;

async Task<object?> Run(Dictionary<string, object?> args, Dictionary<string, object?> state)
{
    var results = new Dictionary<string, object?>();
    async Task<object?> Call(string name, Dictionary<string, object?> kwargs)
    {
        var result = await Capability(name, kwargs);
        results[name] = result;
        return result;
    }
    async Task<Dictionary<string, object?>> CallObj(string name, Dictionary<string, object?> kwargs)
    {
        return (Dictionary<string, object?>) (await Call(name, kwargs))!;
    }

    var created = await CallObj("files.create", new Dictionary<string, object?> {
        ["content"] = "capability smoke",
        ["original_name"] = state["file_name"],
        ["content_mode"] = "raw",
    });
    results["files.create"] = created["file_id"];

    var fileBytes = await CallObj("files.get_bytes", new Dictionary<string, object?> {
        ["file_id"] = created["file_id"],
    });
    results["files.get_bytes"] = fileBytes["content_base64"];

    var metadata = await CallObj("files.get_metadata", new Dictionary<string, object?> {
        ["file_id"] = created["file_id"],
    });
    results["files.get_metadata"] = metadata["file_id"];

    var readResult = await CallObj("files.read", new Dictionary<string, object?> {
        ["file_id"] = created["file_id"],
    });
    var readPages = (List<object?>) readResult["pages"]!;
    results["files.read"] = ((Dictionary<string, object?>) readPages[0]!)["text"];

    var httpResult = await CallObj("http.request", new Dictionary<string, object?> {
        ["method"] = "GET",
        ["url"] = state["manifest_url"],
        ["timeout_seconds"] = 10,
    });
    results["http.request"] = httpResult["status_code"];

    foreach (var method in new[] {"get", "post", "put", "patch", "delete", "head"})
    {
        var payload = new Dictionary<string, object?> {
            ["url"] = state["echo_url"],
            ["timeout_seconds"] = 10,
        };
        if (new[] {"post", "put", "patch"}.Contains(method))
        {
            payload["json"] = new Dictionary<string, object?> { ["method"] = method };
        }
        var httpMethodResult = await CallObj($"http.{method}", payload);
        results[$"http.{method}"] = httpMethodResult["status_code"];
    }

    var platformResult = await CallObj("platform.request", new Dictionary<string, object?> {
        ["service"] = "capability_gateway",
        ["method"] = "GET",
        ["path"] = "/capability-gateway/api/v1/capabilities/manifest",
        ["timeout_seconds"] = 10,
    });
    results["platform.request"] = platformResult["version"];

    foreach (var level in new[] {"debug", "info", "warning", "error"})
    {
        var logResult = await CallObj($"log.{level}", new Dictionary<string, object?> {
            ["message"] = $"capability {level}",
            ["fields"] = new Dictionary<string, object?> { ["language"] = "csharp" },
        });
        results[$"log.{level}"] = logResult["logged"];
    }

    results["state.get_nested"] = await Call("state.get_nested", new Dictionary<string, object?> { ["path"] = "nested.value", ["default"] = "missing" });
    results["state.set_nested"] = (await CallObj("state.set_nested", new Dictionary<string, object?> { ["path"] = "nested.value", ["value"] = "updated" }))["value"];
    results["state.merge"] = ((Dictionary<string, object?>) ((Dictionary<string, object?>) (await CallObj("state.merge", new Dictionary<string, object?> {
        ["updates"] = new Dictionary<string, object?> { ["merged"] = new Dictionary<string, object?> { ["ok"] = true } },
    }))["state"]!)["merged"]!)["ok"];
    results["state.get_files"] = ((List<object?>) (await Call("state.get_files", new Dictionary<string, object?>()))!).Count;
    results["state.find_file"] = (await CallObj("state.find_file", new Dictionary<string, object?> { ["name"] = "state-file.txt" }))["name"];
    results["state.get_user"] = (await CallObj("state.get_user", new Dictionary<string, object?>()))["id"];
    results["state.get_tool_result"] = (await CallObj("state.get_tool_result", new Dictionary<string, object?> { ["tool_name"] = "seed_tool" }))["ok"];
    results["state.get_messages"] = ((List<object?>) (await Call("state.get_messages", new Dictionary<string, object?>()))!).Count;
    results["state.add_user_message"] = (await CallObj("state.add_user_message", new Dictionary<string, object?> { ["content"] = "hello user" }))["role"];
    results["state.add_agent_message"] = (await CallObj("state.add_agent_message", new Dictionary<string, object?> { ["content"] = "hello agent" }))["role"];
    results["state.push_ui_event"] = (await CallObj("state.push_ui_event", new Dictionary<string, object?> {
        ["event_type"] = "capability.single",
        ["payload"] = new Dictionary<string, object?> { ["ok"] = true },
    }))["type"];
    results["state.push_ui_events"] = ((List<object?>) (await Call("state.push_ui_events", new Dictionary<string, object?> {
        ["events"] = new List<object?> { new Dictionary<string, object?> { ["type"] = "capability.batch", ["payload"] = new Dictionary<string, object?> { ["ok"] = true } } },
    }))!).Count;
    results["state.pop_ui_events"] = ((List<object?>) (await Call("state.pop_ui_events", new Dictionary<string, object?>()))!).Count;
    results["state.extract_json"] = (await CallObj("state.extract_json", new Dictionary<string, object?> { ["text"] = "```json\\n{\\"ok\\": true}\\n```" }))["ok"];
    results["channel.send"] = (await CallObj("channel.send", new Dictionary<string, object?> { ["content"] = "queued message" }))["queued"];
    results["channel.send_with_buttons"] = (await CallObj("channel.send_with_buttons", new Dictionary<string, object?> {
        ["content"] = "queued buttons",
        ["buttons"] = new List<object?> {"A", "B"},
    }))["queued"];
    results["trace.event"] = (await CallObj("trace.event", new Dictionary<string, object?> {
        ["event_type"] = "capability.test",
        ["attributes"] = new Dictionary<string, object?> { ["language"] = "csharp" },
    }))["recorded"];

    var summary = await CallObj("text.summarize", new Dictionary<string, object?> {
        ["text"] = "Capability smoke text",
        ["provider"] = "mock",
        ["model"] = "mock-gpt-4",
        ["max_output_tokens"] = 32,
    });
    results["text.summarize"] = summary["summary"];

    var markdown = await CallObj("text.format_markdown", new Dictionary<string, object?> {
        ["text"] = "Title\\nItem one",
        ["provider"] = "mock",
        ["model"] = "mock-gpt-4",
        ["max_chunk_chars"] = 512,
    });
    results["text.format_markdown"] = markdown["markdown"];

    var speech = await CallObj("voice.synthesize_speech", new Dictionary<string, object?> {
        ["text"] = "Capability smoke speech",
        ["provider"] = "mock",
        ["response_format"] = "wav",
        ["file_name"] = state["speech_file_name"],
    });
    results["voice.synthesize_speech"] = speech["file_id"];

    var transcript = await CallObj("voice.transcribe_audio", new Dictionary<string, object?> {
        ["file_id"] = speech["file_id"],
        ["provider"] = "mock",
        ["language"] = "ru",
    });
    results["voice.transcribe_audio"] = transcript["text"];

    state["capability_results"] = results;
    return new Dictionary<string, object?> { ["capability_results"] = results };
}
"""

    raise AssertionError(f"Unsupported language: {language}")


def interrupt_capability_code(language: str) -> str:
    if language == "python":
        return """
async def run(args, state):
    await flow.ask_user(question="Need input")
    return {"unreachable": True}
"""
    if language in {"javascript", "typescript"}:
        return """
async function run(args, state) {
  await flow.ask_user({question: "Need input"});
  return {unreachable: true};
}
"""
    if language == "go":
        return """
package main

func Run(args map[string]any, state map[string]any) (any, error) {
    _, err := flow.AskUser(map[string]any{"question": "Need input"})
    if err != nil {
        return nil, err
    }
    return map[string]any{"unreachable": true}, nil
}
"""
    if language == "csharp":
        return """
using System.Collections.Generic;
using System.Threading.Tasks;

async Task<object?> Run(Dictionary<string, object?> args, Dictionary<string, object?> state)
{
    await flow.AskUser(new Dictionary<string, object?> { ["question"] = "Need input" });
    return new Dictionary<string, object?> { ["unreachable"] = true };
}
"""
    raise AssertionError(f"Unsupported language: {language}")


def cross_language_tool_code(language: str, tool_ids: Mapping[str, str]) -> str:
    if language == "python":
        return """
async def run(args, state):
    outputs = {}
    for language, tool_id in state["tool_ids"].items():
        result = await tools.call(tool_id, value=language)
        outputs[language] = result
    state["cross_language_results"] = outputs
    return {"cross_language_results": outputs}
"""

    if language in {"javascript", "typescript"}:
        return """
async function run(args, state) {
  const outputs = {};
  for (const [language, toolId] of Object.entries(state.tool_ids)) {
    outputs[language] = await tools.call(toolId, {value: language});
  }
  state.cross_language_results = outputs;
  return {cross_language_results: outputs};
}
"""

    if language == "go":
        return """
package main

func Run(args map[string]any, state map[string]any) (any, error) {
    outputs := map[string]any{}
    toolIDs := state["tool_ids"].(map[string]any)
    for language, rawToolID := range toolIDs {
        result, err := tools.Call(rawToolID.(string), map[string]any{"value": language})
        if err != nil {
            return nil, err
        }
        outputs[language] = result
    }
    state["cross_language_results"] = outputs
    return map[string]any{"cross_language_results": outputs}, nil
}
"""

    if language == "csharp":
        return """
using System.Collections.Generic;
using System.Threading.Tasks;

async Task<object?> Run(Dictionary<string, object?> args, Dictionary<string, object?> state)
{
    var outputs = new Dictionary<string, object?>();
    var toolIds = (Dictionary<string, object?>) state["tool_ids"]!;
    foreach (var pair in toolIds)
    {
        outputs[pair.Key] = await tools.Call(pair.Value!.ToString()!, new Dictionary<string, object?> {
            ["value"] = pair.Key,
        });
    }
    state["cross_language_results"] = outputs;
    return new Dictionary<string, object?> { ["cross_language_results"] = outputs };
}
"""

    raise AssertionError(f"Unsupported language: {language}")


def tool_payloads(tool_ids: Mapping[str, str]) -> list[dict[str, Any]]:
    schema = {
        "type": "object",
        "properties": {"value": {"type": "string"}},
        "required": ["value"],
        "additionalProperties": False,
    }
    return [
        {
            "tool_id": tool_ids["python"],
            "title": "Python capability test tool",
            "description": "Python tool used by cross-language capability tests.",
            "language": "python",
            "code": (
                "async def python_tool(args, state):\n"
                "    value = str(args['value'])\n"
                "    state['tool_python_seen'] = value\n"
                "    return {'tool_language': 'python', 'value': value}\n"
            ),
            "parameters_schema": schema,
            "tags": ["capability-test"],
        },
        {
            "tool_id": tool_ids["javascript"],
            "title": "JavaScript capability test tool",
            "description": "JavaScript tool used by cross-language capability tests.",
            "language": "javascript",
            "code": (
                "async function javascriptTool(args, state) {\n"
                "  const value = String(args.value);\n"
                "  state.tool_javascript_seen = value;\n"
                "  return {tool_language: 'javascript', value};\n"
                "}\n"
            ),
            "parameters_schema": schema,
            "tags": ["capability-test"],
        },
        {
            "tool_id": tool_ids["typescript"],
            "title": "TypeScript capability test tool",
            "description": "TypeScript tool used by cross-language capability tests.",
            "language": "typescript",
            "code": (
                "async function typescriptTool(args: {value: string}, state: Record<string, unknown>) {\n"
                "  const value = String(args.value);\n"
                "  state.tool_typescript_seen = value;\n"
                "  return {tool_language: 'typescript', value};\n"
                "}\n"
            ),
            "parameters_schema": schema,
            "tags": ["capability-test"],
        },
        {
            "tool_id": tool_ids["go"],
            "title": "Go capability test tool",
            "description": "Go tool used by cross-language capability tests.",
            "language": "go",
            "code": (
                "package main\n\n"
                "func GoTool(args map[string]any, state map[string]any) (any, error) {\n"
                "    value := args[\"value\"].(string)\n"
                "    state[\"tool_go_seen\"] = value\n"
                "    return map[string]any{\"tool_language\": \"go\", \"value\": value}, nil\n"
                "}\n"
            ),
            "parameters_schema": schema,
            "tags": ["capability-test"],
        },
        {
            "tool_id": tool_ids["csharp"],
            "title": "C# capability test tool",
            "description": "C# tool used by cross-language capability tests.",
            "language": "csharp",
            "code": (
                "using System.Collections.Generic;\n"
                "using System.Threading.Tasks;\n\n"
                "Task<object?> CsharpTool(Dictionary<string, object?> args, Dictionary<string, object?> state)\n"
                "{\n"
                "    var value = args[\"value\"]!.ToString()!;\n"
                "    state[\"tool_csharp_seen\"] = value;\n"
                "    return Task.FromResult<object?>(new Dictionary<string, object?> {\n"
                "        [\"tool_language\"] = \"csharp\",\n"
                "        [\"value\"] = value,\n"
                "    });\n"
                "}\n"
            ),
            "parameters_schema": schema,
            "tags": ["capability-test"],
        },
    ]


async def fetch_manifest(sandbox_services: Mapping[str, str]) -> dict[str, Any]:
    async with AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"{sandbox_services['capability_gateway']}/capability-gateway/api/v1/capabilities/manifest",
            headers={"X-Request-Id": "capability-test-request", "X-Trace-Id": "capability-test-trace"},
        )
        response.raise_for_status()
        return response.json()


async def assert_language_documentation(language: str, sandbox_services: Mapping[str, str]) -> None:
    manifest = await fetch_manifest(sandbox_services)
    capability_names = {item["name"] for item in manifest["capabilities"]}
    async with AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"{sandbox_services['capability_gateway']}/capability-gateway/api/v1/capabilities/documentation",
            params={"language": language},
            headers={"X-Request-Id": "capability-test-request", "X-Trace-Id": "capability-test-trace"},
        )
        response.raise_for_status()
        payload = response.json()
        markdown = payload["markdown"]

    assert "Capability API" in markdown
    assert f"Language: `{language}`" in markdown
    assert "### Parameters" in markdown
    assert "### Returns" in markdown
    assert "Input JSON Schema" in markdown
    for capability_name in capability_names:
        assert f"## `{capability_name}`" in markdown
    capability_docs = {item["capability_name"]: item for item in payload["capabilities"]}
    assert capability_docs.keys() >= capability_names
    assert "flow_state" in {item["name"] for item in payload["namespaces"]}
    files_create = capability_docs["files.create"]
    assert {field["path"] for field in files_create["input_fields"]} >= {
        "content",
        "original_name",
        "content_mode",
    }
    assert files_create["signature"]
    assert files_create["insert_text"]

    if language == "python":
        assert "async def run(args, state):" in markdown
        assert "await tools.calculator(" in markdown
        assert files_create["label"] == "files.create"
    elif language in {"javascript", "typescript"}:
        assert "async function run(args, state)" in markdown
        assert "export async function" not in markdown
        assert "await tools.calculator(" in markdown
        assert files_create["label"] == "files.create"
    elif language == "go":
        assert "func run(args map[string]any, state map[string]any) (any, error)" in markdown
        assert "tools.Calculator(" in markdown
        assert files_create["label"] == "files.Create"
    elif language == "csharp":
        assert "async Task<object?> run(Dictionary<string, object?> args, Dictionary<string, object?> state)" in markdown
        assert "await tools.Calculator(" in markdown
        assert files_create["label"] == "files.Create"
    else:
        raise AssertionError(f"Unsupported language: {language}")


async def assert_language_sdk_covers_manifest(
    language: str,
    sandbox_services: Mapping[str, str],
    flows_client_http: AsyncClient,
    auth_headers_system: dict[str, str],
) -> None:
    manifest = await fetch_manifest(sandbox_services)
    pairs = sdk_pairs(manifest)
    assert pairs
    response = await flows_client_http.post(
        "/flows/api/v1/code/execute",
        json={
            "node_type": "code",
            "node_config": {
                "type": "code",
                "language": language,
                "code": sdk_presence_code(language, pairs),
            },
            "state": {},
        },
        headers=auth_headers_system,
        timeout=180.0,
    )
    response.raise_for_status()
    body = response.json()
    assert body["success"] is True, body
    assert body["output_state"]["sdk_method_count"] == len(pairs)


async def assert_language_runs_static_platform_capabilities(
    language: str,
    sandbox_services: Mapping[str, str],
    flows_client_http: AsyncClient,
    auth_headers_system: dict[str, str],
    unique_id: str,
) -> None:
    manifest = await fetch_manifest(sandbox_services)
    static_names = {
        item["name"]
        for item in manifest["capabilities"]
        if isinstance(item, dict) and isinstance(item.get("name"), str) and not item["name"].startswith("tools.")
    }
    assert static_names == STATIC_PLATFORM_CAPABILITIES | INTERRUPT_PLATFORM_CAPABILITIES

    response = await flows_client_http.post(
        "/flows/api/v1/code/execute",
        json={
            "node_type": "code",
            "node_config": {
                "type": "code",
                "language": language,
                "code": static_capability_code(language),
            },
            "state": {
                "manifest_url": f"{sandbox_services['capability_gateway']}/capability-gateway/api/v1/capabilities/manifest",
                "echo_url": f"{sandbox_services['capability_gateway']}/capability-gateway/api/v1/capabilities/manifest",
                "file_name": f"capability-{language}-{unique_id}.txt",
                "speech_file_name": f"capability-{language}-{unique_id}.wav",
                "nested": {"value": "initial"},
                "files": [{"name": "state-file.txt", "file_id": "state-file-id"}],
                "user_id": f"user-{language}",
                "user_groups": ["capability"],
                "tool_results": {"seed_tool": {"ok": True}},
                "messages": [],
            },
        },
        headers=auth_headers_system,
        timeout=180.0,
    )
    response.raise_for_status()
    body = response.json()
    assert body["success"] is True, body
    results = body["output_state"]["capability_results"]
    assert set(results) == STATIC_PLATFORM_CAPABILITIES
    assert isinstance(results["files.create"], str) and results["files.create"]
    assert results["files.get_bytes"] == EXPECTED_FILE_BASE64
    assert isinstance(results["files.get_metadata"], str) and results["files.get_metadata"]
    assert "capability smoke" in results["files.read"]
    assert results["http.request"] == 200
    for method in ["get", "post", "put", "patch", "delete", "head"]:
        assert isinstance(results[f"http.{method}"], int)
    assert results["platform.request"] == "capabilities.v1"
    for level in ["debug", "info", "warning", "error"]:
        assert results[f"log.{level}"] is True
    assert results["state.get_nested"] == "initial"
    assert results["state.set_nested"] == "updated"
    assert results["state.merge"] is True
    assert results["state.get_files"] == 1
    assert results["state.find_file"] == "state-file.txt"
    assert results["state.get_user"] == f"user-{language}"
    assert results["state.get_tool_result"] is True
    assert results["state.get_messages"] == 0
    assert results["state.add_user_message"] == "user"
    assert results["state.add_agent_message"] == "agent"
    assert results["state.push_ui_event"] == "capability.single"
    assert results["state.push_ui_events"] == 1
    assert results["state.pop_ui_events"] == 2
    assert results["state.extract_json"] is True
    assert results["channel.send"] is True
    assert results["channel.send_with_buttons"] is True
    assert results["trace.event"] is True
    assert isinstance(results["text.summarize"], str) and results["text.summarize"].strip()
    assert isinstance(results["text.format_markdown"], str) and results["text.format_markdown"].strip()
    assert isinstance(results["voice.synthesize_speech"], str) and results["voice.synthesize_speech"]
    assert isinstance(results["voice.transcribe_audio"], str) and results["voice.transcribe_audio"].strip()


async def assert_language_runs_interrupt_platform_capabilities(
    language: str,
    sandbox_services: Mapping[str, str],
) -> None:
    manifest = CapabilityManifest.model_validate(await fetch_manifest(sandbox_services))
    service_name, path = RUNNER_ENDPOINTS[language]
    claims = CapabilityExecutionTokenClaims(
        company_id="system",
        user_id="test_user",
        flow_id="test_flow",
        branch_id="main",
        session_id="test_flow:test_context",
        task_id="test_task",
        context_id="test_context",
        request_id=f"capability-interrupt-{language}",
        exp=execution_token_exp(300),
    )
    request = CodeExecutionRequest(
        kind="node",
        language=cast(CapabilityLanguage, language),
        code=interrupt_capability_code(language),
        entrypoint=None,
        wall_time_limit_seconds=30,
        args={},
        state={},
        context=CapabilityExecutionContext(
            execution_token=issue_execution_token(claims),
            company_id=claims.company_id,
            user_id=claims.user_id,
            flow_id=claims.flow_id,
            branch_id=claims.branch_id,
            session_id=claims.session_id,
            task_id=claims.task_id,
            context_id=claims.context_id,
            request_id=claims.request_id,
            trace_id=f"capability-interrupt-trace-{language}",
        ),
        capability_manifest=manifest,
    )
    async with AsyncClient(timeout=60.0) as client:
        response = await client.post(
            f"{sandbox_services[service_name]}{path}",
            json=request.model_dump(mode="json"),
            headers={
                "X-Request-Id": f"capability-interrupt-{language}",
                "X-Trace-Id": f"capability-interrupt-trace-{language}",
            },
        )
    response.raise_for_status()
    body = response.json()
    assert body["status"] == "interrupted", body
    assert body["interrupt"]["kind"] == "user_message"
    assert body["interrupt"]["body"]["question"] == "Need input"


async def assert_language_calls_tools_written_in_every_language(
    language: str,
    flows_client_http: AsyncClient,
    auth_headers_system: dict[str, str],
    cross_language_tool_ids: Mapping[str, str],
) -> None:
    response = await flows_client_http.post(
        "/flows/api/v1/code/execute",
        json={
            "node_type": "code",
            "node_config": {
                "type": "code",
                "language": language,
                "code": cross_language_tool_code(language, cross_language_tool_ids),
            },
            "state": {"tool_ids": dict(cross_language_tool_ids)},
        },
        headers=auth_headers_system,
        timeout=180.0,
    )
    response.raise_for_status()
    body = response.json()
    assert body["success"] is True, body
    output_state = body["output_state"]
    results = output_state["cross_language_results"]
    assert set(results) == set(CAPABILITY_LANGUAGES)
    for tool_language in CAPABILITY_LANGUAGES:
        assert results[tool_language] == {
            "tool_language": tool_language,
            "value": tool_language,
        }
        assert output_state[f"tool_{tool_language}_seen"] == tool_language
