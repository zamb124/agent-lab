"""Платформенный слой LLM-контекста.

Memory / compaction не реэкспортируются здесь: иначе
``config.base → llm_context → memory → config`` при импорте ``LLMContextConfig``.
Импортируй из ``core.llm_context.memory`` / ``core.llm_context.memory_compaction``.
"""

from core.llm_context.compiler import LLMContextBudgetError, LLMContextCompiler
from core.llm_context.models import (
    CompiledLLMContext,
    LLMContextBlock,
    LLMContextBlockBudgetScope,
    LLMContextBlockKind,
    LLMContextBudget,
    LLMContextBudgetName,
    LLMContextBudgetPatch,
    LLMContextCacheMode,
    LLMContextCompactionMode,
    LLMContextCompileRequest,
    LLMContextConfig,
    LLMContextMemoryScope,
    LLMContextMessageRole,
    LLMContextMode,
    LLMContextPatch,
    LLMContextProfile,
    LLMContextRetrievalMode,
    LLMContextRetrievalPatch,
    LLMContextRetrievalPolicy,
    LLMContextUsage,
)
from core.llm_context.profile import (
    LLM_CONTEXT_PROFILE_METADATA_KEY,
    IdentityLLMContextProfileSource,
    build_identity_llm_context_profile_block,
)
from core.llm_context.sources import (
    LLMContextSource,
    LLMContextSourceRegistry,
    LLMContextSourceRequest,
    StaticLLMContextSource,
)
from core.llm_context.token_counter import SimpleTokenCounter, TiktokenTokenCounter, TokenCounter

__all__ = [
    "CompiledLLMContext",
    "LLMContextBlock",
    "LLMContextBlockBudgetScope",
    "LLMContextBlockKind",
    "LLMContextBudget",
    "LLMContextBudgetPatch",
    "LLMContextBudgetError",
    "LLMContextBudgetName",
    "LLMContextCacheMode",
    "LLMContextCompiler",
    "LLMContextCompactionMode",
    "LLMContextCompileRequest",
    "LLMContextConfig",
    "LLM_CONTEXT_PROFILE_METADATA_KEY",
    "IdentityLLMContextProfileSource",
    "LLMContextMemoryScope",
    "LLMContextMessageRole",
    "LLMContextMode",
    "LLMContextPatch",
    "LLMContextProfile",
    "LLMContextRetrievalMode",
    "LLMContextRetrievalPatch",
    "LLMContextRetrievalPolicy",
    "LLMContextSource",
    "LLMContextSourceRegistry",
    "LLMContextSourceRequest",
    "LLMContextUsage",
    "SimpleTokenCounter",
    "StaticLLMContextSource",
    "TiktokenTokenCounter",
    "TokenCounter",
    "build_identity_llm_context_profile_block",
]
