"""Живой LSP JSON-RPC к code-node language servers (без моков).

HTTP bootstrap — реальный flows `:9001`. JSON-RPC — текстовые кадры без Content-Length.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from typing import Protocol, final

from httpx2 import AsyncClient

from core.capabilities.models import (
    CapabilityLanguage,
    CodeLspSession,
    CodeLspSessionCreateRequest,
)
from core.types import JsonObject, JsonValue, parse_json_object, require_json_object

FLOWS_LSP_WS_ORIGIN = "ws://127.0.0.1:9001"
_LSP_RPC_TIMEOUT_SECONDS = 60.0


class LspWebSocket(Protocol):
    async def send(self, message: str) -> None: ...

    async def recv(self) -> str | bytes: ...


def lsp_position_of(source: str, needle: str) -> tuple[int, int]:
    index = source.index(needle)
    line = source.count("\n", 0, index)
    last_nl = source.rfind("\n", 0, index)
    character = index if last_nl < 0 else index - last_nl - 1
    return line, character


def lsp_position_after(source: str, needle: str) -> tuple[int, int]:
    index = source.index(needle) + len(needle)
    line = source.count("\n", 0, index)
    last_nl = source.rfind("\n", 0, index)
    character = index if last_nl < 0 else index - last_nl - 1
    return line, character


def labels_contain(labels: set[str], expected: str) -> bool:
    return any(expected == label or expected in label for label in labels)


async def create_code_lsp_session(
    flows_client_http: AsyncClient,
    headers: Mapping[str, str],
    body: CodeLspSessionCreateRequest,
) -> CodeLspSession:
    response = await flows_client_http.post(
        "/flows/api/v1/code/lsp/session",
        headers=dict(headers),
        json=body.model_dump(mode="json"),
        timeout=180.0,
    )
    if response.status_code != 200:
        raise AssertionError(
            f"POST /flows/api/v1/code/lsp/session -> {response.status_code}: {response.text}"
        )
    return CodeLspSession.model_validate(response.json())


@asynccontextmanager
async def connect_code_lsp_ws(
    auth_token: str | None,
    ws_path: str,
) -> AsyncIterator[CodeLspRpc]:
    import websockets

    extra_headers: list[tuple[str, str]] = []
    if auth_token is not None:
        extra_headers.append(("Cookie", f"auth_token={auth_token}"))
    async with websockets.connect(
        f"{FLOWS_LSP_WS_ORIGIN}{ws_path}",
        additional_headers=extra_headers,
        open_timeout=30,
        ping_interval=None,
        max_size=None,
    ) as ws:
        yield CodeLspRpc(ws)


async def assert_lsp_ws_closed_policy(auth_token: str | None, ws_path: str) -> None:
    import websockets

    extra_headers: list[tuple[str, str]] = []
    if auth_token is not None:
        extra_headers.append(("Cookie", f"auth_token={auth_token}"))
    try:
        async with websockets.connect(
            f"{FLOWS_LSP_WS_ORIGIN}{ws_path}",
            additional_headers=extra_headers,
            open_timeout=15,
            ping_interval=None,
            close_timeout=15,
        ) as ws:
            _ = await asyncio.wait_for(ws.recv(), timeout=15)
    except TimeoutError as exc:
        raise AssertionError("expected language server websocket to close with 1008") from exc
    except websockets.exceptions.ConnectionClosed as exc:
        close_code = _websocket_close_code(exc)
        if close_code != 1008:
            raise AssertionError(f"expected close 1008, got {close_code}: {exc.reason}") from exc
        return
    except websockets.exceptions.InvalidStatus as exc:
        raise AssertionError(
            f"expected WS close 1008 after accept, handshake failed: {exc}"
        ) from exc
    raise AssertionError("expected language server websocket to close with 1008")


def _websocket_close_code(exc: object) -> int:
    received = getattr(exc, "rcvd", None)
    received_code = getattr(received, "code", None)
    if isinstance(received_code, int):
        return received_code
    sent = getattr(exc, "sent", None)
    sent_code = getattr(sent, "code", None)
    if isinstance(sent_code, int):
        return sent_code
    legacy_code = getattr(exc, "code", None)
    if isinstance(legacy_code, int):
        return legacy_code
    return 1011


@final
class CodeLspRpc:
    """Клиент JSON-RPC поверх WS text frames; отвечает на server requests."""

    def __init__(self, ws: LspWebSocket) -> None:
        self._ws = ws
        self._next_id = 1
        self._notifications: list[JsonObject] = []
        self._root_uri = ""

    async def initialize(self, session: CodeLspSession) -> JsonObject:
        self._root_uri = session.root_uri
        result = await self.request(
            "initialize",
            {
                "processId": None,
                "clientInfo": {"name": "platform-lsp-tests", "version": "1"},
                "rootUri": session.root_uri,
                "capabilities": {
                    "workspace": {
                        "configuration": True,
                        "workspaceFolders": True,
                        "didChangeConfiguration": {"dynamicRegistration": True},
                    },
                    "window": {"workDoneProgress": True},
                    "textDocument": {
                        "synchronization": {"dynamicRegistration": True, "didSave": True},
                        "completion": {
                            "completionItem": {
                                "snippetSupport": True,
                                "documentationFormat": ["markdown", "plaintext"],
                            }
                        },
                        "hover": {"contentFormat": ["markdown", "plaintext"]},
                        "publishDiagnostics": {"relatedInformation": True},
                    },
                },
                "workspaceFolders": [{"uri": session.root_uri, "name": "workspace"}],
            },
        )
        await self.notify("initialized", {})
        return result

    async def did_open(self, session: CodeLspSession, source: str) -> None:
        await self.notify(
            "textDocument/didOpen",
            {
                "textDocument": {
                    "uri": session.document_uri,
                    "languageId": session.language_id,
                    "version": 1,
                    "text": source,
                }
            },
        )

    async def request(self, method: str, params: JsonObject) -> JsonObject:
        request_id = self._next_id
        self._next_id += 1
        await self._send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        deadline = asyncio.get_event_loop().time() + _LSP_RPC_TIMEOUT_SECONDS
        while asyncio.get_event_loop().time() < deadline:
            payload = await self._recv_message(deadline)
            if await self._answer_server_request(payload):
                continue
            if "method" in payload and "id" not in payload:
                self._notifications.append(payload)
                continue
            if payload.get("id") != request_id:
                continue
            if "error" in payload:
                raise AssertionError(f"LSP {method} error: {payload['error']}")
            result = payload.get("result")
            if isinstance(result, dict):
                return require_json_object(result, "lsp.result")
            return {"result": result}
        raise AssertionError(f"LSP {method} timed out after {_LSP_RPC_TIMEOUT_SECONDS}s")

    async def notify(self, method: str, params: JsonObject) -> None:
        await self._send({"jsonrpc": "2.0", "method": method, "params": params})

    async def wait_notification(
        self, method: str, *, timeout: float = _LSP_RPC_TIMEOUT_SECONDS
    ) -> JsonObject:
        for index, payload in enumerate(self._notifications):
            if payload.get("method") == method:
                return self._notifications.pop(index)
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            payload = await self._recv_message(deadline)
            if await self._answer_server_request(payload):
                continue
            if payload.get("method") != method:
                if "method" in payload and "id" not in payload:
                    self._notifications.append(payload)
                continue
            return payload
        raise AssertionError(f"LSP notification {method} not received in {timeout}s")

    async def completion_labels(self, uri: str, line: int, character: int) -> set[str]:
        envelope = await self.request(
            "textDocument/completion",
            {
                "textDocument": {"uri": uri},
                "position": {"line": line, "character": character},
                "context": {"triggerKind": 2, "triggerCharacter": "."},
            },
        )
        raw_result: JsonValue
        if "items" in envelope:
            raw_result = envelope
        else:
            raw_result = envelope.get("result")
        return _completion_labels(raw_result)

    async def wait_completion_containing(
        self,
        uri: str,
        source: str,
        needle: str,
        expected: str,
        *,
        timeout: float = _LSP_RPC_TIMEOUT_SECONDS,
    ) -> set[str]:
        line, character = lsp_position_after(source, needle)
        deadline = asyncio.get_event_loop().time() + timeout
        last: set[str] = set()
        while asyncio.get_event_loop().time() < deadline:
            last = await self.completion_labels(uri, line, character)
            if labels_contain(last, expected):
                return last
            await asyncio.sleep(0.4)
        raise AssertionError(
            f"completion after {needle!r} missing {expected!r}; labels={sorted(last)!r}"
        )

    async def wait_hover_text(
        self,
        uri: str,
        source: str,
        needle: str,
        *,
        timeout: float = _LSP_RPC_TIMEOUT_SECONDS,
    ) -> str:
        line, character = lsp_position_of(source, needle)
        deadline = asyncio.get_event_loop().time() + timeout
        last_error = "hover empty"
        while asyncio.get_event_loop().time() < deadline:
            try:
                return await self.hover_text(uri, line, character)
            except AssertionError as exc:
                last_error = str(exc)
            await asyncio.sleep(0.4)
        raise AssertionError(f"hover on {needle!r} failed: {last_error}")

    async def hover_text(self, uri: str, line: int, character: int) -> str:
        envelope = await self.request(
            "textDocument/hover",
            {
                "textDocument": {"uri": uri},
                "position": {"line": line, "character": character},
            },
        )
        contents: JsonValue
        if "contents" in envelope:
            contents = envelope.get("contents")
        else:
            inner = envelope.get("result")
            if isinstance(inner, dict):
                contents = inner.get("contents")
            else:
                contents = inner
        text = _markup_text(contents).strip()
        if text == "":
            raise AssertionError("LSP hover contents are empty")
        return text

    async def wait_error_diagnostic(
        self,
        uri: str,
        needle: str,
        *,
        timeout: float = _LSP_RPC_TIMEOUT_SECONDS,
    ) -> str:
        deadline = asyncio.get_event_loop().time() + timeout
        seen: list[str] = []
        while asyncio.get_event_loop().time() < deadline:
            remaining = deadline - asyncio.get_event_loop().time()
            try:
                notification = await self.wait_notification(
                    "textDocument/publishDiagnostics",
                    timeout=max(remaining, 0.1),
                )
            except AssertionError:
                break
            params = notification.get("params")
            if not isinstance(params, dict):
                continue
            diagnostics = params.get("diagnostics")
            if not isinstance(diagnostics, list):
                continue
            for item in diagnostics:
                if not isinstance(item, dict):
                    continue
                message = item.get("message")
                if not isinstance(message, str):
                    continue
                seen.append(message)
                if needle in message:
                    return message
        raise AssertionError(
            f"no error diagnostic containing {needle!r} for {uri}; messages={seen!r}"
        )

    async def _send(self, payload: JsonObject) -> None:
        await self._ws.send(json.dumps(payload))

    async def _recv_message(self, deadline: float) -> JsonObject:
        remaining = deadline - asyncio.get_event_loop().time()
        if remaining <= 0:
            raise AssertionError("LSP recv timed out")
        try:
            raw = await asyncio.wait_for(self._ws.recv(), timeout=remaining)
        except TimeoutError as exc:
            raise AssertionError("LSP recv timed out") from exc
        if isinstance(raw, bytes):
            text = raw.decode("utf-8")
        else:
            text = raw
        return parse_json_object(text, "lsp.frame")

    async def _answer_server_request(self, payload: JsonObject) -> bool:
        if "method" not in payload or "id" not in payload:
            return False
        if "result" in payload or "error" in payload:
            return False
        method = payload.get("method")
        request_id = payload.get("id")
        params = payload.get("params")
        result: JsonValue = None
        if method == "workspace/configuration":
            items = params.get("items") if isinstance(params, dict) else None
            result = [{} for _ in items] if isinstance(items, list) else []
        elif method == "workspace/workspaceFolders":
            result = [{"uri": self._root_uri, "name": "workspace"}]
        await self._send({"jsonrpc": "2.0", "id": request_id, "result": result})
        return True


def default_lsp_source(language: CapabilityLanguage, unique_id: str) -> str:
    if language == "python":
        return (
            f"# {unique_id}\n"
            "import json\n"
            "import httpx2\n"
            "\n"
            "async def run(args, state):\n"
            '    data = json.loads("{}")\n'
            "    created = await files.create(content='x')\n"
            "    return created\n"
        )
    if language == "javascript":
        return (
            f"// {unique_id}\n"
            "import lodash from 'lodash';\n"
            "import leftPad from 'left-pad';\n"
            "\n"
            "async function run(args, state) {\n"
            "  const value = lodash.get(args, 'x');\n"
            "  return value;\n"
            "}\n"
        )
    if language == "typescript":
        return (
            f"// {unique_id}\n"
            "import lodash from 'lodash';\n"
            "import leftPad from 'left-pad';\n"
            "\n"
            "async function run(args: Record<string, unknown>, state: Record<string, unknown>) {\n"
            "  const value = lodash.get(args, 'x');\n"
            "  return value;\n"
            "}\n"
        )
    if language == "go":
        return (
            "package main\n"
            "\n"
            f"// {unique_id}\n"
            "\n"
            "import (\n"
            '\t"encoding/json"\n'
            '\t"github.com/not-allowed/mod"\n'
            ")\n"
            "\n"
            "func run(args map[string]any, state map[string]any) (any, error) {\n"
            "\tb, err := json.Marshal(args)\n"
            "\t_ = err\n"
            "\treturn b, nil\n"
            "}\n"
        )
    return (
        "using System.Collections.Generic;\n"
        "using System.Text.Json;\n"
        "using System.Threading.Tasks;\n"
        "\n"
        f"// {unique_id}\n"
        "\n"
        "Task<object?> run(Dictionary<string, object?> args, Dictionary<string, object?> state)\n"
        "{\n"
        "    var encoded = JsonSerializer.Serialize(args);\n"
        "    var created = files.Create(new Dictionary<string, object?>());\n"
        "    return Task.FromResult<object?>(encoded);\n"
        "}\n"
    )


def session_request(language: CapabilityLanguage, unique_id: str) -> CodeLspSessionCreateRequest:
    variable_key = f"var_{unique_id}"
    return CodeLspSessionCreateRequest(
        language=language,
        source=default_lsp_source(language, unique_id),
        parameters_schema={
            "type": "object",
            "properties": {"file_id": {"type": "string"}},
            "required": ["file_id"],
        },
        variable_keys=[variable_key],
    )


def _completion_labels(result: JsonValue) -> set[str]:
    items: list[JsonValue]
    if isinstance(result, list):
        items = result
    elif isinstance(result, dict) and "items" in result:
        raw_items = result["items"]
        if not isinstance(raw_items, list):
            raise AssertionError(f"completion items must be a list, got {type(raw_items)!r}")
        items = raw_items
    elif result is None:
        return set()
    else:
        raise AssertionError(f"unexpected completion result: {result!r}")
    labels: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        label = item.get("label")
        if isinstance(label, str) and label != "":
            labels.add(label)
        insert_text = item.get("insertText")
        if isinstance(insert_text, str) and insert_text != "":
            labels.add(insert_text)
        filter_text = item.get("filterText")
        if isinstance(filter_text, str) and filter_text != "":
            labels.add(filter_text)
        text_edit = item.get("textEdit")
        if isinstance(text_edit, dict):
            new_text = text_edit.get("newText")
            if isinstance(new_text, str) and new_text != "":
                labels.add(new_text)
    return labels


def _markup_text(value: JsonValue) -> str:
    if value is None or isinstance(value, bool):
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, int | float):
        return str(value)
    if isinstance(value, list):
        return "\n".join(_markup_text(item) for item in value)
    inner = value.get("value")
    if isinstance(inner, str):
        return inner
    contents = value.get("contents")
    if contents is not None:
        return _markup_text(contents)
    return json.dumps(value)
