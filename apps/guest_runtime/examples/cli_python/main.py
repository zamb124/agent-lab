"""Эталон code_agent CLI (python): LLM proxy + capability text.summarize, extra argv → JSON {text}."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

type CapabilityValue = (
    str | int | float | bool | None | list[CapabilityValue] | dict[str, CapabilityValue]
)


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


def _http_json(url: str, payload: dict[str, CapabilityValue]) -> dict[str, CapabilityValue]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers=_request_headers(),
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} {url}: {detail}") from exc
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise RuntimeError(f"{url} must return a JSON object")
    return parsed


def _llm_chat(prompt: str) -> str:
    base = _require_env("OPENAI_BASE_URL")
    key = _require_env("OPENAI_API_KEY")
    url = base.rstrip("/") + "/chat/completions"
    headers = _request_headers()
    headers["Authorization"] = f"Bearer {key}"
    body = json.dumps(
        {
            "model": "auto",
            "messages": [{"role": "user", "content": prompt}],
        }
    ).encode("utf-8")
    request = urllib.request.Request(url, data=body, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"llm proxy HTTP {exc.code}: {detail}") from exc
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise RuntimeError("llm proxy must return a JSON object")
    choices = parsed.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeError("llm proxy choices required")
    first = choices[0]
    if not isinstance(first, dict):
        raise RuntimeError("llm proxy choice must be an object")
    message = first.get("message")
    if not isinstance(message, dict):
        raise RuntimeError("llm proxy message required")
    content = message.get("content")
    if not isinstance(content, str):
        raise RuntimeError("llm proxy message.content required")
    return content


def _call_capability(name: str, **kwargs: CapabilityValue) -> CapabilityValue:
    gateway = _require_env("CAPABILITY_GATEWAY_URL")
    context_raw = _require_env("PLATFORM_CAPABILITY_CONTEXT")
    context = json.loads(context_raw)
    if not isinstance(context, dict):
        raise RuntimeError("PLATFORM_CAPABILITY_CONTEXT must be a JSON object")
    url = gateway.rstrip("/") + "/capability-gateway/api/v1/capabilities/call"
    parsed = _http_json(
        url,
        {
            "context": context,
            "name": name,
            "args": [],
            "kwargs": kwargs,
            "state": {},
        },
    )
    status = parsed.get("status")
    if status != "ok":
        raise RuntimeError(f"capability {name} status {status!r}")
    return parsed.get("result")


def main() -> None:
    extra = " ".join(sys.argv[1:])
    if extra.strip() == "":
        raise RuntimeError("prompt text is required")
    llm_text = _llm_chat(extra)
    summary_payload = _call_capability("text.summarize", text=extra)
    if not isinstance(summary_payload, dict):
        raise RuntimeError("text.summarize result must be an object")
    summary = summary_payload.get("summary")
    if not isinstance(summary, str) or summary.strip() == "":
        raise RuntimeError("text.summarize summary required")
    sys.stdout.write(
        json.dumps(
            {"text": extra, "llm": llm_text, "summary": summary},
            ensure_ascii=False,
        )
    )
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
