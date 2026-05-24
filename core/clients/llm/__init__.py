"""
LLM клиенты.

Stream-first архитектура: LLM ВСЕГДА вызывается как stream.
"""

from .client import LLMClient
from .config import LLMCallConfig
from .errors import (
    LLMStreamIdleTimeoutError,
    LLMStreamUserCancelledError,
)
from .messages import LLMToolCall, LLMToolCallFunction, MessageInput, StreamEvent
from .mock import MockLLM, get_global_mock_llm, get_or_create_global_mock_llm
from .model_routing import (
    HUMANITEC_LLM_AUTO_MODEL,
    HUMANITEC_LLM_PROVIDER,
    LLM_ROUTING_PROVIDER_SLUGS,
    split_provider_prefixed_model,
)
from .runtime import (
    get_llm,
    get_llm_for_state,
    setup_mock_responses,
    should_use_platform_default_free_pool,
)

__all__ = [
    "get_llm",
    "get_llm_for_state",
    "LLMClient",
    "LLMCallConfig",
    "LLMStreamIdleTimeoutError",
    "LLMStreamUserCancelledError",
    "MessageInput",
    "LLMToolCall",
    "LLMToolCallFunction",
    "MockLLM",
    "setup_mock_responses",
    "should_use_platform_default_free_pool",
    "get_global_mock_llm",
    "get_or_create_global_mock_llm",
    "StreamEvent",
    "HUMANITEC_LLM_AUTO_MODEL",
    "HUMANITEC_LLM_PROVIDER",
    "LLM_ROUTING_PROVIDER_SLUGS",
    "split_provider_prefixed_model",
]
