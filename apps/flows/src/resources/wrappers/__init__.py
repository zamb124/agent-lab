"""
Resource Wrappers - объекты доступные в namespace.

Каждый wrapper предоставляет API для работы с ресурсом.
"""

from apps.flows.src.resources.wrappers.code_module import CodeModule
from apps.flows.src.resources.wrappers.llm_resource import LLMResource
from apps.flows.src.resources.wrappers.files_resource import FilesResource

__all__ = [
    "CodeModule",
    "LLMResource",
    "FilesResource",
]
