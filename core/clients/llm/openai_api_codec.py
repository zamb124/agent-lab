"""
OpenAI Chat Completions wire codec (response/SSE envelopes).

Используется тонким HTTP adapter'ом (agent LLM proxy). Execution — только через LLMClient.
"""

from __future__ import annotations

import json
import time
import uuid

from core.types import JsonObject


def new_chat_completion_id() -> str:
    return f"chatcmpl-{uuid.uuid4().hex}"


def build_openai_usage(
    *,
    prompt_tokens: int,
    completion_tokens: int,
    cost: float | None = None,
) -> JsonObject:
    usage: JsonObject = {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
    }
    if cost is not None:
        usage["cost"] = cost
    return usage


def build_chat_completion(
    *,
    completion_id: str,
    model_id: str,
    content: str,
    tool_calls: list[JsonObject] | None,
    finish_reason: str,
    usage: JsonObject,
    system_fingerprint: str | None = None,
    created: int | None = None,
) -> JsonObject:
    message_body: JsonObject = {"role": "assistant", "content": content}
    if tool_calls:
        message_body["tool_calls"] = tool_calls
    return {
        "id": completion_id,
        "object": "chat.completion",
        "created": int(time.time()) if created is None else created,
        "model": model_id,
        "system_fingerprint": system_fingerprint,
        "choices": [
            {
                "index": 0,
                "message": message_body,
                "finish_reason": finish_reason,
            }
        ],
        "usage": usage,
    }


def build_chat_completion_chunk(
    *,
    completion_id: str,
    model_id: str,
    delta: JsonObject,
    finish_reason: str | None = None,
    system_fingerprint: str | None = None,
    created: int | None = None,
) -> JsonObject:
    # ChatStreamChunk: system_fingerprint — string only (omit when unset; null invalid).
    chunk: JsonObject = {
        "id": completion_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()) if created is None else created,
        "model": model_id,
        "choices": [
            {
                "index": 0,
                "delta": delta,
                "finish_reason": finish_reason,
            }
        ],
    }
    if system_fingerprint is not None:
        chunk["system_fingerprint"] = system_fingerprint
    return chunk


def build_chat_completion_usage_chunk(
    *,
    completion_id: str,
    model_id: str,
    usage: JsonObject,
    system_fingerprint: str | None = None,
    created: int | None = None,
) -> JsonObject:
    chunk: JsonObject = {
        "id": completion_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()) if created is None else created,
        "model": model_id,
        "choices": [],
        "usage": usage,
    }
    if system_fingerprint is not None:
        chunk["system_fingerprint"] = system_fingerprint
    return chunk


def sse_data_line(payload: JsonObject) -> bytes:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode("utf-8")


def sse_done_line() -> bytes:
    return b"data: [DONE]\n\n"


def openai_error_body(
    *,
    message: str,
    error_type: str,
    code: str | None = None,
) -> JsonObject:
    error: JsonObject = {
        "message": message,
        "type": error_type,
    }
    if code is not None:
        error["code"] = code
    return {"error": error}


__all__ = [
    "build_chat_completion",
    "build_chat_completion_chunk",
    "build_chat_completion_usage_chunk",
    "build_openai_usage",
    "new_chat_completion_id",
    "openai_error_body",
    "sse_data_line",
    "sse_done_line",
]
