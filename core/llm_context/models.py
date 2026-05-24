"""Strict contracts for platform LLM context compilation."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator, model_validator

from core.models import StrictBaseModel
from core.types import JsonObject

LLMContextMode = Literal["off", "window", "smart", "agent"]
LLMContextMemoryScope = Literal["off", "session", "node", "flow", "company"]
LLMContextRetrievalMode = Literal["off", "semantic", "lexical", "hybrid"]
LLMContextCompactionMode = Literal["off", "auto", "force"]
LLMContextCacheMode = Literal["off", "auto", "provider_hints"]
LLMContextBudgetName = Literal["tiny", "small", "medium", "large", "max"]
LLMContextBlockKind = Literal[
    "profile",
    "memory",
    "rag",
    "tool_summary",
    "system",
    "custom",
]
LLMContextBlockBudgetScope = Literal[
    "profile",
    "memory",
    "rag",
    "tool_result",
    "custom",
]
LLMContextMessageRole = Literal["system", "user", "assistant", "tool"]


def _default_budgets() -> dict[str, "LLMContextBudget"]:
    return {
        "tiny": LLMContextBudget(
            max_input_tokens=8_000,
            output_reserve_tokens=1_000,
            reasoning_reserve_tokens=0,
            safety_buffer_tokens=500,
            active_window_tokens=2_000,
            memory_tokens=1_000,
            rag_tokens=1_500,
            tool_result_tokens=500,
        ),
        "small": LLMContextBudget(
            max_input_tokens=32_000,
            output_reserve_tokens=2_000,
            reasoning_reserve_tokens=1_000,
            safety_buffer_tokens=1_000,
            active_window_tokens=8_000,
            memory_tokens=6_000,
            rag_tokens=8_000,
            tool_result_tokens=2_000,
        ),
        "medium": LLMContextBudget(
            max_input_tokens=128_000,
            output_reserve_tokens=4_000,
            reasoning_reserve_tokens=4_000,
            safety_buffer_tokens=2_000,
            active_window_tokens=20_000,
            memory_tokens=32_000,
            rag_tokens=32_000,
            tool_result_tokens=8_000,
        ),
        "large": LLMContextBudget(
            max_input_tokens=200_000,
            output_reserve_tokens=6_000,
            reasoning_reserve_tokens=8_000,
            safety_buffer_tokens=4_000,
            active_window_tokens=32_000,
            memory_tokens=64_000,
            rag_tokens=48_000,
            tool_result_tokens=16_000,
        ),
        "max": LLMContextBudget(
            max_input_tokens=200_000,
            output_reserve_tokens=4_000,
            reasoning_reserve_tokens=4_000,
            safety_buffer_tokens=2_000,
            active_window_tokens=64_000,
            memory_tokens=80_000,
            rag_tokens=40_000,
            tool_result_tokens=10_000,
        ),
    }


def _default_profiles() -> dict[str, "LLMContextProfile"]:
    budgets = _default_budgets()
    return {
        "off": LLMContextProfile(
            mode="off",
            budget=budgets["small"],
            memory="off",
            retrieval=LLMContextRetrievalPolicy(mode="off", rerank=False),
            compaction="off",
            cache="off",
        ),
        "compact": LLMContextProfile(
            mode="window",
            budget=budgets["small"],
            memory="off",
            retrieval=LLMContextRetrievalPolicy(mode="off", rerank=False),
            compaction="auto",
            cache="auto",
        ),
        "standard": LLMContextProfile(
            mode="smart",
            budget=budgets["medium"],
            memory="session",
            retrieval=LLMContextRetrievalPolicy(mode="hybrid", top_k=16, rerank=True),
            compaction="auto",
            cache="auto",
        ),
        "agent": LLMContextProfile(
            mode="agent",
            budget=budgets["large"],
            memory="session",
            retrieval=LLMContextRetrievalPolicy(mode="hybrid", top_k=32, rerank=True),
            compaction="auto",
            cache="provider_hints",
        ),
    }


class LLMContextBudget(StrictBaseModel):
    """Resolved token budget for one compiled LLM request."""

    max_input_tokens: int = Field(default=128_000, gt=0)
    output_reserve_tokens: int = Field(default=4_000, ge=0)
    reasoning_reserve_tokens: int = Field(default=0, ge=0)
    safety_buffer_tokens: int = Field(default=1_000, ge=0)
    active_window_tokens: int = Field(default=8_000, ge=0)
    memory_tokens: int = Field(default=16_000, ge=0)
    rag_tokens: int = Field(default=12_000, ge=0)
    tool_result_tokens: int = Field(default=4_000, ge=0)

    @model_validator(mode="after")
    def reserves_must_leave_input_room(self) -> "LLMContextBudget":
        reserved = (
            self.output_reserve_tokens
            + self.reasoning_reserve_tokens
            + self.safety_buffer_tokens
        )
        if reserved >= self.max_input_tokens:
            raise ValueError("LLM context budget reserves must be lower than max_input_tokens")
        return self


class LLMContextBudgetPatch(StrictBaseModel):
    """Partial token budget overlay."""

    max_input_tokens: int | None = Field(default=None, gt=0)
    output_reserve_tokens: int | None = Field(default=None, ge=0)
    reasoning_reserve_tokens: int | None = Field(default=None, ge=0)
    safety_buffer_tokens: int | None = Field(default=None, ge=0)
    active_window_tokens: int | None = Field(default=None, ge=0)
    memory_tokens: int | None = Field(default=None, ge=0)
    rag_tokens: int | None = Field(default=None, ge=0)
    tool_result_tokens: int | None = Field(default=None, ge=0)


class LLMContextRetrievalPolicy(StrictBaseModel):
    """Retrieval settings after layer resolution."""

    mode: LLMContextRetrievalMode = "off"
    top_k: int = Field(default=8, ge=1, le=256)
    rerank: bool = False
    min_score: float | None = Field(default=None, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def disabled_retrieval_must_not_rerank(self) -> "LLMContextRetrievalPolicy":
        if self.mode == "off" and self.rerank:
            raise ValueError("retrieval.rerank requires retrieval.mode != 'off'")
        return self


class LLMContextRetrievalPatch(StrictBaseModel):
    """Partial retrieval overlay."""

    mode: LLMContextRetrievalMode | None = None
    top_k: int | None = Field(default=None, ge=1, le=256)
    rerank: bool | None = None
    min_score: float | None = Field(default=None, ge=0.0, le=1.0)


class LLMContextProfile(StrictBaseModel):
    """Fully resolved behavior profile used by the compiler."""

    mode: LLMContextMode = "smart"
    budget: LLMContextBudget = Field(default_factory=LLMContextBudget)
    memory: LLMContextMemoryScope = "session"
    retrieval: LLMContextRetrievalPolicy = Field(default_factory=LLMContextRetrievalPolicy)
    compaction: LLMContextCompactionMode = "auto"
    cache: LLMContextCacheMode = "auto"


class LLMContextPatch(StrictBaseModel):
    """Partial overlay accepted from company/resource/node/inline layers."""

    profile: str | None = Field(default=None, min_length=1)
    mode: LLMContextMode | None = None
    budget: LLMContextBudgetPatch | LLMContextBudgetName | None = None
    memory: LLMContextMemoryScope | None = None
    retrieval: LLMContextRetrievalPatch | LLMContextRetrievalMode | None = None
    compaction: LLMContextCompactionMode | None = None
    cache: LLMContextCacheMode | None = None

    @field_validator("profile")
    @classmethod
    def profile_must_be_slug(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not all(ch.isalnum() or ch in ("_", "-") for ch in value):
            raise ValueError("profile must contain only letters, digits, '_' or '-'")
        return value


class LLMContextConfig(StrictBaseModel):
    """Platform-level context profiles and named budgets."""

    default_profile: str = Field(default="off", min_length=1)
    budgets: dict[str, LLMContextBudget] = Field(default_factory=_default_budgets)
    profiles: dict[str, LLMContextProfile] = Field(default_factory=_default_profiles)

    @field_validator("default_profile")
    @classmethod
    def default_profile_must_be_slug(cls, value: str) -> str:
        if not all(ch.isalnum() or ch in ("_", "-") for ch in value):
            raise ValueError("default_profile must contain only letters, digits, '_' or '-'")
        return value

    @field_validator("budgets", "profiles")
    @classmethod
    def keys_must_be_slugs(
        cls,
        value: dict[str, LLMContextBudget] | dict[str, LLMContextProfile],
    ) -> dict[str, LLMContextBudget] | dict[str, LLMContextProfile]:
        for key in value:
            if not key or not all(ch.isalnum() or ch in ("_", "-") for ch in key):
                raise ValueError(f"context profile/budget key is not a slug: {key!r}")
        return value

    @model_validator(mode="after")
    def default_profile_must_exist(self) -> "LLMContextConfig":
        if self.default_profile not in self.profiles:
            raise ValueError(f"default_profile {self.default_profile!r} is absent in profiles")
        return self


class LLMContextBlock(StrictBaseModel):
    """Candidate context block before compiler packing."""

    kind: LLMContextBlockKind
    budget_scope: LLMContextBlockBudgetScope = "custom"
    role: LLMContextMessageRole = "system"
    content: str = Field(..., min_length=1)
    stable_key: str = Field(..., min_length=1)
    priority: int = Field(default=100, ge=0)
    score: float | None = Field(default=None, ge=0.0, le=1.0)
    token_count: int | None = Field(default=None, ge=0)
    required: bool = False
    provenance: JsonObject = Field(default_factory=dict)


class LLMContextCompileRequest(StrictBaseModel):
    """Input to the platform context compiler."""

    messages: list[JsonObject] = Field(default_factory=list)
    candidate_blocks: list[LLMContextBlock] = Field(default_factory=list)
    policy: LLMContextProfile = Field(default_factory=LLMContextProfile)
    tools_schema_tokens: int = Field(default=0, ge=0)
    model_context_length: int | None = Field(default=None, gt=0)
    output_token_reserve: int | None = Field(default=None, ge=0)
    metadata: JsonObject = Field(default_factory=dict)


class LLMContextUsage(StrictBaseModel):
    """Compiler token accounting for tracing and tests."""

    max_input_tokens: int
    policy_max_input_tokens: int | None = None
    model_context_length: int | None = None
    reserved_tokens: int
    available_input_tokens: int
    active_message_tokens: int
    selected_block_tokens: int
    total_input_tokens: int
    tool_result_original_tokens: int = 0
    tool_result_compacted_tokens: int = 0
    tool_result_saved_tokens: int = 0
    tool_result_compacted_messages: int = 0


class CompiledLLMContext(StrictBaseModel):
    """Final messages and debug data after context compilation."""

    messages: list[JsonObject]
    selected_blocks: list[LLMContextBlock] = Field(default_factory=list)
    dropped_blocks: list[LLMContextBlock] = Field(default_factory=list)
    usage: LLMContextUsage
    provider_hints: JsonObject = Field(default_factory=dict)


__all__ = [
    "CompiledLLMContext",
    "LLMContextBlock",
    "LLMContextBlockBudgetScope",
    "LLMContextBlockKind",
    "LLMContextBudget",
    "LLMContextBudgetPatch",
    "LLMContextBudgetName",
    "LLMContextCacheMode",
    "LLMContextCompactionMode",
    "LLMContextCompileRequest",
    "LLMContextConfig",
    "LLMContextMemoryScope",
    "LLMContextMessageRole",
    "LLMContextMode",
    "LLMContextPatch",
    "LLMContextProfile",
    "LLMContextRetrievalMode",
    "LLMContextRetrievalPatch",
    "LLMContextRetrievalPolicy",
    "LLMContextUsage",
]
