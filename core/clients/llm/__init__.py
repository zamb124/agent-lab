"""
LLM клиенты.

Stream-first архитектура: LLM ВСЕГДА вызывается как stream.
"""

from .factory import (
    LLMClient,
    LLMStreamIdleTimeoutError,
    LLMStreamUserCancelledError,
    MessageInput,
    StreamEvent,
    get_llm,
    get_llm_for_state,
    setup_mock_responses,
)
from .mock import MockLLM, get_global_mock_llm
from .model_routing import LLM_ROUTING_PROVIDER_SLUGS, split_provider_prefixed_model

__all__ = [
    "get_llm",
    "get_llm_for_state",
    "LLMClient",
    "LLMStreamIdleTimeoutError",
    "LLMStreamUserCancelledError",
    "MessageInput",
    "MockLLM",
    "setup_mock_responses",
    "get_global_mock_llm",
    "StreamEvent",
    "LLM_ROUTING_PROVIDER_SLUGS",
    "split_provider_prefixed_model",
]
