"""
Resource Wrappers - объекты доступные в namespace.

Каждый wrapper предоставляет API для работы с ресурсом.
"""

from apps.flows.src.resources.wrappers.code_module import CodeModule
from apps.flows.src.resources.wrappers.rag_resource import RAGResource
from apps.flows.src.resources.wrappers.llm_resource import LLMResource
from apps.flows.src.resources.wrappers.http_resource import HTTPResource
from apps.flows.src.resources.wrappers.files_resource import FilesResource
from apps.flows.src.resources.wrappers.cache_resource import CacheResource
from apps.flows.src.resources.wrappers.prompt_resource import PromptResource

__all__ = [
    "CodeModule",
    "RAGResource",
    "LLMResource",
    "HTTPResource",
    "FilesResource",
    "CacheResource",
    "PromptResource",
]
