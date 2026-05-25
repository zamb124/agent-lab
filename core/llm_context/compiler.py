"""Deterministic context compiler for platform LLM calls."""

from __future__ import annotations

import hashlib
import json
from typing import TypedDict

from core.llm_context.models import (
    CompiledLLMContext,
    LLMContextBlock,
    LLMContextCacheMode,
    LLMContextCompileRequest,
    LLMContextProfile,
    LLMContextUsage,
)
from core.llm_context.token_counter import TiktokenTokenCounter, TokenCounter
from core.types import JsonObject, JsonValue


class LLMContextBudgetError(ValueError):
    """Raised when mandatory context cannot fit into the resolved token budget."""


_BLOCK_OUTPUT_ORDER = {
    "system": 0,
    "profile": 10,
    "memory": 20,
    "rag": 30,
    "tool_summary": 40,
    "custom": 50,
}


class _ToolCompactionStats(TypedDict):
    original_tokens: int
    compacted_tokens: int
    saved_tokens: int
    compacted_messages: int


class LLMContextCompiler:
    """Compile messages + candidate blocks into a bounded, provider-neutral prompt."""

    def __init__(self, token_counter: TokenCounter | None = None) -> None:
        self._token_counter: TokenCounter = token_counter or TiktokenTokenCounter()

    def compile(self, request: LLMContextCompileRequest) -> CompiledLLMContext:
        policy = request.policy
        messages = [dict(message) for message in request.messages]
        tool_compaction: _ToolCompactionStats = {
            "original_tokens": 0,
            "compacted_tokens": 0,
            "saved_tokens": 0,
            "compacted_messages": 0,
        }
        if policy.mode != "off" and policy.compaction != "off":
            messages, tool_compaction = self._compact_tool_result_messages(messages, policy)

        policy_max_input_tokens = policy.budget.max_input_tokens
        max_input_tokens = policy_max_input_tokens
        if request.model_context_length is not None:
            max_input_tokens = min(max_input_tokens, request.model_context_length)
        output_reserve_tokens = policy.budget.output_reserve_tokens
        if request.output_token_reserve is not None:
            output_reserve_tokens = max(output_reserve_tokens, request.output_token_reserve)
        reserved_tokens = (
            output_reserve_tokens
            + policy.budget.reasoning_reserve_tokens
            + policy.budget.safety_buffer_tokens
            + request.tools_schema_tokens
        )
        available_input_tokens = max_input_tokens - reserved_tokens
        if available_input_tokens <= 0:
            raise LLMContextBudgetError("LLM context reserves leave no input token budget")

        if policy.mode == "off":
            active_message_tokens = self._count_messages(messages)
            if active_message_tokens > available_input_tokens:
                raise LLMContextBudgetError("LLM context mode=off messages exceed token budget")
            return CompiledLLMContext(
                messages=messages,
                usage=LLMContextUsage(
                    max_input_tokens=max_input_tokens,
                    policy_max_input_tokens=policy_max_input_tokens,
                    model_context_length=request.model_context_length,
                    reserved_tokens=reserved_tokens,
                    available_input_tokens=available_input_tokens,
                    active_message_tokens=active_message_tokens,
                    selected_block_tokens=0,
                    total_input_tokens=active_message_tokens,
                ),
                provider_hints={},
            )

        system_prefix, conversation_messages = self._split_system_prefix(messages)
        system_prefix_tokens = self._count_messages(system_prefix)
        if system_prefix_tokens > available_input_tokens:
            raise LLMContextBudgetError("System LLM context prefix exceeds available input token budget")

        active_messages, active_message_tokens = self._select_active_messages(
            conversation_messages,
            active_window_tokens=policy.budget.active_window_tokens,
            available_input_tokens=available_input_tokens - system_prefix_tokens,
        )
        active_total_tokens = system_prefix_tokens + active_message_tokens
        remaining = available_input_tokens - active_total_tokens

        selected_blocks, dropped_blocks, selected_block_tokens = self._select_blocks(
            request.candidate_blocks,
            remaining_tokens=remaining,
            request=request,
        )
        ordered_blocks = sorted(selected_blocks, key=_block_output_sort_key)
        block_messages: list[JsonObject] = [
            {"role": block.role, "content": block.content}
            for block in ordered_blocks
        ]
        final_messages = system_prefix + block_messages + active_messages
        provider_hints = self._provider_hints(policy.cache, system_prefix, ordered_blocks)

        return CompiledLLMContext(
            messages=final_messages,
            selected_blocks=ordered_blocks,
            dropped_blocks=dropped_blocks,
            usage=LLMContextUsage(
                max_input_tokens=max_input_tokens,
                policy_max_input_tokens=policy_max_input_tokens,
                model_context_length=request.model_context_length,
                reserved_tokens=reserved_tokens,
                available_input_tokens=available_input_tokens,
                active_message_tokens=active_total_tokens,
                selected_block_tokens=selected_block_tokens,
                total_input_tokens=active_total_tokens + selected_block_tokens,
                tool_result_original_tokens=tool_compaction["original_tokens"],
                tool_result_compacted_tokens=tool_compaction["compacted_tokens"],
                tool_result_saved_tokens=tool_compaction["saved_tokens"],
                tool_result_compacted_messages=tool_compaction["compacted_messages"],
            ),
            provider_hints=provider_hints,
        )

    def _compact_tool_result_messages(
        self,
        messages: list[JsonObject],
        policy: LLMContextProfile,
    ) -> tuple[list[JsonObject], _ToolCompactionStats]:
        tool_indexes: list[tuple[int, int]] = []
        original_tokens = 0
        for index, message in enumerate(messages):
            if message.get("role") != "tool":
                continue
            content = self._message_content_to_text(message.get("content"))
            if not content.strip():
                continue
            token_count = self._token_counter.count_message(message)
            tool_indexes.append((index, token_count))
            original_tokens += token_count

        stats: _ToolCompactionStats = {
            "original_tokens": original_tokens,
            "compacted_tokens": original_tokens,
            "saved_tokens": 0,
            "compacted_messages": 0,
        }
        if not tool_indexes:
            return messages, stats

        budget = int(policy.budget.tool_result_tokens)
        if budget <= 0 or original_tokens <= budget:
            return messages, stats

        compacted_messages = [dict(message) for message in messages]
        remaining_tokens = original_tokens
        target_per_message = max(8, budget // len(tool_indexes))

        for index, token_count in sorted(tool_indexes, key=lambda item: item[1], reverse=True):
            if remaining_tokens <= budget:
                break
            message = compacted_messages[index]
            compacted = dict(message)
            compacted["content"] = self._compact_tool_result_content(
                message,
                original_tokens=token_count,
                target_tokens=target_per_message,
            )
            compacted_token_count = self._token_counter.count_message(compacted)
            if compacted_token_count >= token_count:
                continue
            compacted_messages[index] = compacted
            remaining_tokens -= token_count - compacted_token_count
            stats["compacted_messages"] += 1

        stats["compacted_tokens"] = remaining_tokens
        stats["saved_tokens"] = max(0, original_tokens - remaining_tokens)
        return compacted_messages, stats

    def _compact_tool_result_content(
        self,
        message: JsonObject,
        *,
        original_tokens: int,
        target_tokens: int,
    ) -> str:
        content = self._message_content_to_text(message.get("content"))
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
        tool_call_id_value = message.get("tool_call_id")
        if tool_call_id_value is not None and not isinstance(tool_call_id_value, str):
            raise ValueError("LLM tool message.tool_call_id must be a string")
        tool_call_id = tool_call_id_value.strip() if isinstance(tool_call_id_value, str) else ""
        prefix_lines = ["[tool result compacted]"]
        if tool_call_id:
            prefix_lines.append(f"tool_call_id={tool_call_id}")
        prefix_lines.extend((f"original_tokens={original_tokens}", f"sha256={digest}"))
        prefix = "\n".join(prefix_lines)
        compacted = prefix
        if self._token_counter.count_text(compacted) <= target_tokens:
            return compacted

        return f"[tool result compacted] sha256={digest} original_tokens={original_tokens}"

    @staticmethod
    def _message_content_to_text(content: JsonValue) -> str:
        if content is None:
            return ""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            text_parts: list[str] = []
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    text = part.get("text")
                    if isinstance(text, str):
                        text_parts.append(text)
            return "\n".join(text_parts)
        return json.dumps(content, ensure_ascii=False, sort_keys=True)

    @staticmethod
    def _split_system_prefix(
        messages: list[JsonObject],
    ) -> tuple[list[JsonObject], list[JsonObject]]:
        prefix: list[JsonObject] = []
        split_index = 0
        for message in messages:
            if message.get("role") != "system":
                break
            prefix.append(message)
            split_index += 1
        return prefix, messages[split_index:]

    def _select_active_messages(
        self,
        messages: list[JsonObject],
        *,
        active_window_tokens: int,
        available_input_tokens: int,
    ) -> tuple[list[JsonObject], int]:
        if not messages:
            return [], 0

        selected_reversed: list[JsonObject] = []
        selected_tokens = 0
        last_message = messages[-1]
        last_tokens = self._token_counter.count_message(last_message)
        if last_tokens > available_input_tokens:
            raise LLMContextBudgetError("Last LLM message exceeds available input token budget")
        selected_reversed.append(last_message)
        selected_tokens += last_tokens

        for message in reversed(messages[:-1]):
            token_count = self._token_counter.count_message(message)
            if selected_tokens + token_count > active_window_tokens:
                break
            if selected_tokens + token_count > available_input_tokens:
                break
            selected_reversed.append(message)
            selected_tokens += token_count

        return list(reversed(selected_reversed)), selected_tokens

    def _select_blocks(
        self,
        blocks: list[LLMContextBlock],
        *,
        remaining_tokens: int,
        request: LLMContextCompileRequest,
    ) -> tuple[list[LLMContextBlock], list[LLMContextBlock], int]:
        deduped = self._dedupe_blocks(blocks)
        allowed = [block for block in deduped if self._block_allowed(block, request)]
        candidates = sorted(allowed, key=_block_selection_sort_key)
        selected: list[LLMContextBlock] = []
        dropped: list[LLMContextBlock] = [block for block in deduped if block not in allowed]
        used_total = 0
        used_by_scope = {"memory": 0, "rag": 0, "tool_result": 0}

        for block in candidates:
            token_count = self._block_token_count(block)
            scope_budget = self._scope_budget(block, request)
            scope_used = used_by_scope.get(block.budget_scope, 0)
            fits_total = used_total + token_count <= remaining_tokens
            fits_scope = scope_budget is None or scope_used + token_count <= scope_budget
            if fits_total and fits_scope:
                selected.append(block.model_copy(update={"token_count": token_count}))
                used_total += token_count
                if block.budget_scope in used_by_scope:
                    used_by_scope[block.budget_scope] += token_count
                continue
            if block.required:
                raise LLMContextBudgetError(
                    f"Required LLM context block {block.stable_key!r} exceeds token budget"
                )
            dropped.append(block.model_copy(update={"token_count": token_count}))

        return selected, dropped, used_total

    def _dedupe_blocks(self, blocks: list[LLMContextBlock]) -> list[LLMContextBlock]:
        by_key: dict[str, LLMContextBlock] = {}
        for block in blocks:
            existing = by_key.get(block.stable_key)
            if existing is None:
                by_key[block.stable_key] = block
                continue
            existing_score = existing.score if existing.score is not None else -1.0
            block_score = block.score if block.score is not None else -1.0
            if (block.required, block.priority, block_score) > (
                existing.required,
                existing.priority,
                existing_score,
            ):
                by_key[block.stable_key] = block
        return list(by_key.values())

    def _block_allowed(self, block: LLMContextBlock, request: LLMContextCompileRequest) -> bool:
        policy = request.policy
        if block.budget_scope == "memory":
            if policy.memory == "off":
                return block.required
            if policy.retrieval.min_score is not None and block.score is not None:
                return block.required or block.score >= policy.retrieval.min_score
            return True
        if block.budget_scope == "rag":
            if policy.retrieval.mode == "off":
                return block.required
            if policy.retrieval.min_score is not None and block.score is not None:
                return block.required or block.score >= policy.retrieval.min_score
        if block.budget_scope == "tool_result" and policy.compaction == "off":
            return block.required
        return True

    def _scope_budget(self, block: LLMContextBlock, request: LLMContextCompileRequest) -> int | None:
        if block.budget_scope == "memory":
            return request.policy.budget.memory_tokens
        if block.budget_scope == "rag":
            return request.policy.budget.rag_tokens
        if block.budget_scope == "tool_result":
            return request.policy.budget.tool_result_tokens
        return None

    def _block_token_count(self, block: LLMContextBlock) -> int:
        if block.token_count is not None:
            return block.token_count
        return self._token_counter.count_text(block.content) + self._token_counter.count_text(block.role)

    def _count_messages(self, messages: list[JsonObject]) -> int:
        return sum(self._token_counter.count_message(message) for message in messages)

    @staticmethod
    def _provider_hints(
        cache_mode: LLMContextCacheMode,
        system_prefix: list[JsonObject],
        blocks: list[LLMContextBlock],
    ) -> JsonObject:
        if cache_mode == "off":
            return {}
        stable_messages_payload = [
            {
                "content": message.get("content"),
                "role": message.get("role"),
                "type": "message",
            }
            for message in system_prefix
            if message.get("role") == "system"
        ]
        stable_blocks_payload = [
            {"key": block.stable_key, "content": block.content, "role": block.role}
            for block in blocks
            if block.role == "system"
        ]
        if not stable_messages_payload and not stable_blocks_payload:
            return {}
        encoded = json.dumps(
            {
                "blocks": stable_blocks_payload,
                "messages": stable_messages_payload,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        return {
            "stable_prefix_block_keys": [item["key"] for item in stable_blocks_payload],
            "stable_prefix_hash": hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
        }


def _block_output_sort_key(block: LLMContextBlock) -> tuple[int, str, int, float, str]:
    kind_order = _BLOCK_OUTPUT_ORDER.get(block.kind, 100)
    if block.kind == "memory":
        return (
            kind_order,
            _memory_created_at_key(block),
            0,
            0.0,
            block.stable_key,
        )
    return (
        kind_order,
        "",
        -block.priority,
        -(block.score if block.score is not None else -1.0),
        block.stable_key,
    )


def _block_selection_sort_key(block: LLMContextBlock) -> tuple[bool, int, int, str, float, str]:
    kind_order = _BLOCK_OUTPUT_ORDER.get(block.kind, 100)
    if block.kind == "memory":
        return (
            not block.required,
            -block.priority,
            kind_order,
            _memory_created_at_key(block),
            0.0,
            block.stable_key,
        )
    return (
        not block.required,
        -block.priority,
        kind_order,
        "",
        -(block.score if block.score is not None else -1.0),
        block.stable_key,
    )


def _memory_created_at_key(block: LLMContextBlock) -> str:
    value = block.provenance.get("created_at")
    if isinstance(value, str) and value.strip() and value.strip() != "unknown":
        return value.strip()
    parts = block.stable_key.split(":")
    if len(parts) >= 4 and parts[2] and parts[2] != "unknown":
        return parts[2]
    return ""


__all__ = ["LLMContextBudgetError", "LLMContextCompiler"]
