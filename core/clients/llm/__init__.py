"""
LLM клиенты.

Stream-first архитектура: LLM ВСЕГДА вызывается как stream.
"""

from .config import LLMCallConfig
from .factory import (
    LLMClient,
    LLMStreamIdleTimeoutError,
    LLMStreamUserCancelledError,
    MessageInput,
    StreamEvent,
    get_llm,
    get_llm_for_state,
    setup_mock_responses,
    should_use_platform_default_free_pool,
)
from .mock import MockLLM, get_global_mock_llm
from .model_routing import (
    HUMANITEC_LLM_AUTO_MODEL,
    HUMANITEC_LLM_PROVIDER,
    LLM_ROUTING_PROVIDER_SLUGS,
    split_provider_prefixed_model,
)

__all__ = [
    "get_llm",
    "get_llm_for_state",
    "LLMClient",
    "LLMCallConfig",
    "LLMStreamIdleTimeoutError",
    "LLMStreamUserCancelledError",
    "MessageInput",
    "MockLLM",
    "setup_mock_responses",
    "should_use_platform_default_free_pool",
    "get_global_mock_llm",
    "StreamEvent",
    "HUMANITEC_LLM_AUTO_MODEL",
    "HUMANITEC_LLM_PROVIDER",
    "LLM_ROUTING_PROVIDER_SLUGS",
    "split_provider_prefixed_model",
]
