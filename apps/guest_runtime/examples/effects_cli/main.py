"""Эталон code_agent CLI: capability ui.render, platform_effects из ответа gateway."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        raise RuntimeError(f"{name} is required")
    return value


def _request_headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    test_scope = os.environ.get("PLATFORM_TEST_SCOPE")
    if test_scope is not None and test_scope.strip() != "":
        headers["X-Test-Scope"] = test_scope.strip()
    return headers


def _call_capability(name: str, **kwargs: object) -> dict[str, object]:
    gateway = _require_env("CAPABILITY_GATEWAY_URL")
    context_raw = _require_env("PLATFORM_CAPABILITY_CONTEXT")
    context = json.loads(context_raw)
    if not isinstance(context, dict):
        raise RuntimeError("PLATFORM_CAPABILITY_CONTEXT must be a JSON object")
    url = gateway.rstrip("/") + "/capability-gateway/api/v1/capabilities/call"
    body = json.dumps(
        {
            "context": context,
            "name": name,
            "args": [],
            "kwargs": kwargs,
            "state": {},
        }
    ).encode("utf-8")
    request = urllib.request.Request(url, data=body, method="POST", headers=_request_headers())
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"capability HTTP {exc.code}: {detail}") from exc
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise RuntimeError("capability must return a JSON object")
    status = parsed.get("status")
    if status != "ok":
        raise RuntimeError(f"capability {name} status {status!r}")
    return parsed


def main() -> None:
    extra = " ".join(sys.argv[1:])
    if extra.strip() == "":
        raise RuntimeError("render markdown is required")
    parsed = _call_capability(
        "ui.render",
        slot_id="conversation",
        blocks=[
            {
                "type": "text",
                "block_id": "guest-note",
                "markdown": extra,
            }
        ],
    )
    effects = parsed.get("platform_effects")
    if not isinstance(effects, list) or not effects:
        raise RuntimeError("ui.render platform_effects required")
    sys.stdout.write(
        json.dumps({"text": extra, "platform_effects": effects}, ensure_ascii=False)
    )
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
