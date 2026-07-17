#!/usr/bin/env python3
"""Минимальный Streamable HTTP MCP-клиент для zed-search (index / tools/call).

Использование:
  python3 mcp_http.py --url http://127.0.0.1:9752/mcp --api-key KEY \\
    call index_codebase '{"path":"/abs/repo"}'
  python3 mcp_http.py --url http://127.0.0.1:9751/mcp --api-key KEY \\
    call index_repository '{"repo_path":"/abs/repo"}'
  python3 mcp_http.py --url ... --api-key KEY ping
  python3 mcp_http.py --url ... --api-key KEY call search_code '{"path":"...","query":"x","limit":3}'
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from typing import Any


class McpHttpError(RuntimeError):
    pass


class McpHttpClient:
    def __init__(self, url: str, api_key: str, timeout_s: float = 600.0) -> None:
        if not url:
            raise ValueError("url is required")
        if not api_key:
            raise ValueError("api_key is required")
        self._url = url.rstrip("/")
        self._api_key = api_key
        self._timeout_s = timeout_s
        self._session_id: str | None = None
        self._next_id = 1

    def _headers(self, *, with_session: bool) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "X-API-Key": self._api_key,
        }
        if with_session and self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        return headers

    def _post(self, payload: dict[str, Any], *, with_session: bool) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self._url,
            data=body,
            headers=self._headers(with_session=with_session),
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout_s) as resp:
                session = resp.headers.get("Mcp-Session-Id")
                if session:
                    self._session_id = session
                raw = resp.read().decode("utf-8")
                content_type = (resp.headers.get("Content-Type") or "").lower()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise McpHttpError(f"HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise McpHttpError(f"connection failed: {exc}") from exc

        if "text/event-stream" in content_type:
            return self._parse_sse(raw)
        if not raw.strip():
            return {}
        try:
            parsed: dict[str, Any] = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise McpHttpError(f"invalid JSON response: {raw[:500]}") from exc
        return parsed

    def _parse_sse(self, raw: str) -> dict[str, Any]:
        data_lines: list[str] = []
        for line in raw.splitlines():
            if line.startswith("data:"):
                data_lines.append(line[5:].lstrip())
            elif line.strip() == "" and data_lines:
                break
        if not data_lines:
            raise McpHttpError(f"empty SSE payload: {raw[:500]}")
        blob = "\n".join(data_lines)
        try:
            parsed: dict[str, Any] = json.loads(blob)
        except json.JSONDecodeError as exc:
            raise McpHttpError(f"invalid SSE JSON: {blob[:500]}") from exc
        return parsed

    def _rpc(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        req_id = self._next_id
        self._next_id += 1
        payload: dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
        }
        if params is not None:
            payload["params"] = params
        with_session = method != "initialize"
        resp = self._post(payload, with_session=with_session)
        if "error" in resp:
            raise McpHttpError(json.dumps(resp["error"], ensure_ascii=False))
        return resp

    def _notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        payload: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            payload["params"] = params
        self._post(payload, with_session=True)

    def initialize(self) -> None:
        self._rpc(
            "initialize",
            {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "zed-search-mcp-http", "version": "1.0.0"},
            },
        )
        self._notify("notifications/initialized")

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        resp = self._rpc(
            "tools/call",
            {"name": name, "arguments": arguments},
        )
        result = resp.get("result")
        if not isinstance(result, dict):
            raise McpHttpError(f"unexpected tools/call result: {resp}")
        return result

    def ping_http(self) -> None:
        ping_url = self._url.rsplit("/mcp", 1)[0] + "/ping"
        req = urllib.request.Request(ping_url, method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = resp.read().decode("utf-8")
            if "pong" not in body.lower() and resp.status != 200:
                raise McpHttpError(f"ping failed: {resp.status} {body}")


def extract_text(result: dict[str, Any]) -> str:
    content = result.get("content")
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "\n".join(parts)
    if isinstance(content, str):
        return content
    return json.dumps(result, ensure_ascii=False)


def main() -> int:
    parser = argparse.ArgumentParser(description="zed-search MCP HTTP client")
    parser.add_argument("--url", required=True)
    parser.add_argument("--api-key", required=True)
    parser.add_argument("--timeout", type=float, default=600.0)
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("ping")
    call_p = sub.add_parser("call")
    call_p.add_argument("tool")
    call_p.add_argument("arguments_json")
    call_p.add_argument("--wait-status", action="store_true")
    call_p.add_argument("--status-tool", default="get_indexing_status")
    call_p.add_argument("--status-path", default="")
    call_p.add_argument("--poll-s", type=float, default=5.0)
    call_p.add_argument("--max-wait-s", type=float, default=900.0)

    args = parser.parse_args()
    client = McpHttpClient(args.url, args.api_key, timeout_s=args.timeout)

    if args.cmd == "ping":
        client.ping_http()
        print("pong")
        return 0

    client.initialize()
    arguments = json.loads(args.arguments_json)
    if not isinstance(arguments, dict):
        raise SystemExit("arguments_json must be a JSON object")
    pre_status_text = ""
    if args.wait_status:
        path_for_pre_status = args.status_path or arguments.get("path") or arguments.get("repo_path")
        if isinstance(path_for_pre_status, str) and path_for_pre_status:
            try:
                pre_status = client.call_tool(args.status_tool, {"path": path_for_pre_status})
                pre_status_text = extract_text(pre_status)
            except McpHttpError:
                pre_status_text = ""

    result = client.call_tool(args.tool, arguments)
    text = extract_text(result)
    print(text)
    if result.get("isError"):
        return 1

    if args.wait_status:
        path = args.status_path or arguments.get("path") or arguments.get("repo_path")
        if not isinstance(path, str) or not path:
            raise SystemExit("--wait-status needs path in arguments or --status-path")
        started = time.monotonic()
        last = ""
        saw_non_completed_status = False
        while time.monotonic() - started < args.max_wait_s:
            status = client.call_tool(args.status_tool, {"path": path})
            status_text = extract_text(status)
            if status_text != last:
                print(f"[status] {status_text}", flush=True)
                last = status_text
            low = status_text.lower()
            if not (
                "completed" in low
                or "ready" in low
                or "fully indexed" in low
            ):
                saw_non_completed_status = True
            if "completed" in low or "ready" in low or "fully indexed" in low:
                if not pre_status_text or status_text != pre_status_text or saw_non_completed_status:
                    return 0
                print(
                    "[status] still seeing pre-existing completed status; waiting for fresh indexing state",
                    flush=True,
                )
            if "failed" in low or "error" in low:
                return 1
            time.sleep(args.poll_s)
        print(f"timeout waiting for status after {args.max_wait_s}s", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except McpHttpError as exc:
        print(f"mcp_http error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
