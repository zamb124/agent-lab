"""Модели контракта статического анализа кода."""

from __future__ import annotations

from pydantic import Field

from core.models import StrictBaseModel


class CodeContract(StrictBaseModel):
    """Статически выведенный контракт кода.

    - ``reads`` — обязательные чтения `state` (subscript, attribute, helper с literal key).
    - ``optional_reads`` — опциональные чтения через `state.get("key")`.
    - ``writes`` — поля `state`, которые код присваивает.
    - ``variable_writes`` — ключи локального dict `variables`, присваиваемые перед
      ``return {"variables": variables}`` (prompt-переменные LLM).
    - ``return_keys`` — ключи словаря/объекта, возвращаемого кодом.
    """

    reads: list[str]
    optional_reads: list[str] = Field(default_factory=list)
    writes: list[str]
    variable_writes: list[str] = Field(default_factory=list)
    return_keys: list[str]


class CodeContractAnalyzeRequest(StrictBaseModel):
    """Запрос статического анализа кода в code-runner."""

    language: str
    code: str


class CodeContractAnalyzeResponse(StrictBaseModel):
    """Ответ статического анализа кода code-runner."""

    language: str
    contract: CodeContract


__all__ = [
    "CodeContract",
    "CodeContractAnalyzeRequest",
    "CodeContractAnalyzeResponse",
]
