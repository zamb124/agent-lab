"""
LLM клиенты.

Stream-first архитектура: LLM ВСЕГДА вызывается как stream.
"""

from .client import LLMClient
from .errors import (
    LLMStreamIdleTimeoutError,
    LLMStreamUserCancelledError,
)
from .messages import LLMToolCall, LLMToolCallFunction, MessageInput, StreamEvent
from .mock import MockLLM, get_global_mock_llm, get_or_create_global_mock_llm
from .runtime import setup_mock_responses

__all__ = [
    "LLMClient",
    "LLMStreamIdleTimeoutError",
    "LLMStreamUserCancelledError",
    "MessageInput",
    "LLMToolCall",
    "LLMToolCallFunction",
    "MockLLM",
    "setup_mock_responses",
    "get_global_mock_llm",
    "get_or_create_global_mock_llm",
    "StreamEvent",
]
