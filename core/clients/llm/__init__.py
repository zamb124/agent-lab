"""
LLM клиенты.

Stream-first архитектура: LLM ВСЕГДА вызывается как stream.
"""

from .factory import (
    LLMClient,
    MessageInput,
    StreamEvent,
    get_llm,
    get_llm_for_state,
    setup_mock_responses,
)
from .mock import MockLLM, get_global_mock_llm

__all__ = [
    "get_llm",
    "get_llm_for_state",
    "LLMClient",
    "MessageInput",
    "MockLLM",
    "setup_mock_responses",
    "get_global_mock_llm",
    "StreamEvent",
]
