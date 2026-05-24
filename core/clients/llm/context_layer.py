"""Adapter between LLMClient messages and the platform LLM context compiler."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass

from a2a.types import Message, Part, Role, TextPart

from core.clients.llm.messages import (
    messages_have_non_text_parts,
    messages_to_openai,
)
from core.llm_context import (
    CompiledLLMContext,
    IdentityLLMContextProfileSource,
    LLMContextBlock,
    LLMContextCompiler,
    LLMContextCompileRequest,
    LLMContextPatch,
    LLMContextProfile,
    LLMContextSourceRegistry,
    LLMContextSourceRequest,
    SimpleTokenCounter,
)
from core.llm_context.resolver import (
    resolve_company_llm_context_patch,
    resolve_llm_context_policy,
)
from core.types import JsonObject, JsonValue, require_json_object

LLMContextInput = LLMContextPatch | LLMContextProfile | JsonObject
_OPENAI_PROVIDER = "openai"
_OPENAI_PROMPT_CACHE_KEY_FIELD = "prompt_cache_key"
_ANTHROPIC_CACHE_CONTROL_FIELD = "cache_control"


@dataclass(frozen=True)
class PreparedLLMContextMessages:
    """Messages prepared for one LLM transport call."""

    messages: list[Message]
    openai_messages: list[JsonObject]
    compiled_context: CompiledLLMContext | None = None


async def prepare_messages_for_context_layer(
    messages: list[Message],
    *,
    tools: list[JsonObject] | None = None,
    llm_context: LLMContextInput | None = None,
    llm_context_blocks: list[LLMContextBlock] | None = None,
    llm_context_source_registry: LLMContextSourceRegistry | None = None,
    model_context_length: int | None = None,
    output_token_reserve: int | None = None,
    metadata: JsonObject | None = None,
    compiler: LLMContextCompiler | None = None,
) -> PreparedLLMContextMessages:
    """
    Compile text messages through the generic context layer when explicitly requested.

    Multimodal prompts keep the original message objects for now: the compiler is text-first and
    must not drop image/file parts while trimming context.
    """
    openai_messages = messages_to_openai(messages)
    has_sources = bool(
        llm_context_source_registry is not None
        and llm_context_source_registry.has_sources
    )
    company_patch = resolve_company_llm_context_patch()
    if llm_context is None and company_patch is None and not llm_context_blocks and not has_sources:
        return PreparedLLMContextMessages(messages=messages, openai_messages=openai_messages)
    if messages_have_non_text_parts(openai_messages):
        return PreparedLLMContextMessages(messages=messages, openai_messages=openai_messages)

    policy = _resolve_context_policy(llm_context, company_patch=company_patch)
    source_blocks: list[LLMContextBlock] = []
    if policy.mode != "off":
        profile_blocks = await IdentityLLMContextProfileSource().collect(
            LLMContextSourceRequest(
                messages=openai_messages,
                policy=policy,
                query=_latest_user_text(openai_messages),
                metadata=metadata or {},
            )
        )
        source_blocks.extend(profile_blocks)
        if llm_context_source_registry is not None:
            source_blocks.extend(
                await llm_context_source_registry.collect(
                    LLMContextSourceRequest(
                        messages=openai_messages,
                        policy=policy,
                        query=_latest_user_text(openai_messages),
                        metadata=metadata or {},
                    )
                )
            )
    compiled = (compiler or LLMContextCompiler()).compile(
        LLMContextCompileRequest(
            messages=openai_messages,
            candidate_blocks=[*(llm_context_blocks or []), *source_blocks],
            policy=policy,
            tools_schema_tokens=_estimate_tools_schema_tokens(tools),
            model_context_length=model_context_length,
            output_token_reserve=output_token_reserve,
            metadata=metadata or {},
        )
    )
    return PreparedLLMContextMessages(
        messages=openai_messages_to_a2a_messages(compiled.messages),
        openai_messages=compiled.messages,
        compiled_context=compiled,
    )


def merge_provider_cache_hints(
    *,
    provider: str | None,
    extra_body: JsonObject | None,
    provider_hints: JsonObject | None,
    model: str | None = None,
) -> JsonObject | None:
    """Merge safe provider-native cache controls into an OpenAI-compatible body."""
    stable_prefix_hash = str((provider_hints or {}).get("stable_prefix_hash") or "").strip()
    if not stable_prefix_hash:
        return dict(extra_body) if extra_body else None

    merged_body: JsonObject = dict(extra_body) if extra_body else {}
    provider_slug = str(provider or "").strip().lower()
    if provider_slug == _OPENAI_PROVIDER:
        _ = merged_body.setdefault(_OPENAI_PROMPT_CACHE_KEY_FIELD, stable_prefix_hash)
    elif provider_slug == "openrouter" and _is_openrouter_anthropic_model(model):
        _ = merged_body.setdefault(_ANTHROPIC_CACHE_CONTROL_FIELD, {"type": "ephemeral"})
    elif provider_slug == "anthropic":
        _ = merged_body.setdefault(_ANTHROPIC_CACHE_CONTROL_FIELD, {"type": "ephemeral"})
    return merged_body or None


def _is_openrouter_anthropic_model(model: str | None) -> bool:
    model_id = str(model or "").strip().lower()
    return model_id.startswith("anthropic/") or "claude" in model_id


def llm_context_trace_metadata(
    compiled_context: CompiledLLMContext | None,
) -> JsonObject | None:
    """Compact, content-free context-layer metadata for traces and LLM status events."""
    if compiled_context is None:
        return None
    return {
        "usage": require_json_object(
            compiled_context.usage.model_dump(mode="json", exclude_none=True),
            "llm_context.usage",
        ),
        "selected_blocks": [
            _block_trace_metadata(block) for block in compiled_context.selected_blocks
        ],
        "dropped_blocks": [
            _block_trace_metadata(block) for block in compiled_context.dropped_blocks
        ],
        "provider_hints": {
            key: value
            for key, value in compiled_context.provider_hints.items()
            if key in {"stable_prefix_block_keys", "stable_prefix_hash"}
        },
    }


def openai_messages_to_a2a_messages(messages: list[JsonObject]) -> list[Message]:
    """Convert compiled OpenAI-compatible messages back to A2A messages for transport."""
    converted: list[Message] = []
    for message in messages:
        role_raw = str(message.get("role", "user"))
        metadata: JsonObject = {}
        if role_raw == "system":
            role = Role.user
            metadata["system"] = True
        elif role_raw == "assistant":
            role = Role.agent
        elif role_raw == "tool":
            role = Role.agent
            tool_call_id = message.get("tool_call_id")
            if isinstance(tool_call_id, str) and tool_call_id:
                metadata["tool_call_id"] = tool_call_id
        else:
            role = Role.user

        tool_calls = message.get("tool_calls")
        if tool_calls:
            metadata["tool_calls"] = tool_calls

        converted.append(
            Message(
                message_id=str(uuid.uuid4()),
                role=role,
                parts=[Part(root=TextPart(text=_content_to_text(message.get("content"))))],
                metadata=metadata or None,
            )
        )
    return converted


def _block_trace_metadata(block: LLMContextBlock) -> JsonObject:
    return {
        "kind": block.kind,
        "budget_scope": block.budget_scope,
        "stable_key": block.stable_key,
        "priority": block.priority,
        "score": block.score,
        "token_count": block.token_count,
        "required": block.required,
        "provenance": _json_safe(block.provenance),
    }


def _resolve_context_policy(
    llm_context: LLMContextInput | None,
    *,
    company_patch: LLMContextPatch | None = None,
) -> LLMContextProfile:
    if isinstance(llm_context, LLMContextProfile):
        return llm_context
    return resolve_llm_context_policy(
        company=company_patch,
        call=llm_context,
    )


def _estimate_tools_schema_tokens(tools: list[JsonObject] | None) -> int:
    if not tools:
        return 0
    encoded = json.dumps(tools, ensure_ascii=False, sort_keys=True, default=str)
    return SimpleTokenCounter().count_text(encoded)


def _content_to_text(content: JsonValue | None) -> str:
    if isinstance(content, str):
        return content
    if content is None:
        return ""
    if isinstance(content, list):
        text_parts: list[str] = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                text = part.get("text")
                if isinstance(text, str):
                    text_parts.append(text)
        return "\n".join(text_parts)
    return json.dumps(content, ensure_ascii=False, sort_keys=True, default=str)


def _latest_user_text(messages: list[JsonObject]) -> str | None:
    for message in reversed(messages):
        if message.get("role") != "user":
            continue
        content = message.get("content")
        text = _content_to_text(content).strip()
        return text or None
    return None


def _json_safe(value: JsonValue) -> JsonValue:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    return str(value)


__all__ = [
    "LLMContextInput",
    "PreparedLLMContextMessages",
    "llm_context_trace_metadata",
    "merge_provider_cache_hints",
    "openai_messages_to_a2a_messages",
    "prepare_messages_for_context_layer",
]
