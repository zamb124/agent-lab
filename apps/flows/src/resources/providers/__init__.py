"""
Resource Providers - резолвинг ресурсов.

Каждый провайдер создаёт wrapper для своего типа ресурса.
"""

from apps.flows.src.resources.providers.base import BaseResourceProvider
from apps.flows.src.resources.providers.code import CodeResourceProvider
from apps.flows.src.resources.providers.rag import RAGResourceProvider
from apps.flows.src.resources.providers.llm import LLMResourceProvider
from apps.flows.src.resources.providers.http import HTTPResourceProvider
from apps.flows.src.resources.providers.files import FilesResourceProvider
from apps.flows.src.resources.providers.cache import CacheResourceProvider
from apps.flows.src.resources.providers.prompt import PromptResourceProvider
from apps.flows.src.resources.providers.secret import SecretResourceProvider

__all__ = [
    "BaseResourceProvider",
    "CodeResourceProvider",
    "RAGResourceProvider",
    "LLMResourceProvider",
    "HTTPResourceProvider",
    "FilesResourceProvider",
    "CacheResourceProvider",
    "PromptResourceProvider",
    "SecretResourceProvider",
]
