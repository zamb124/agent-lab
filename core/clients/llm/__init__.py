"""
LLM - клиенты для работы с языковыми моделями.
"""

from core.clients.llm.factory import get_llm, setup_mock_responses, get_global_mock_llm

__all__ = [
    "get_llm",
    "setup_mock_responses",
    "get_global_mock_llm",
]

