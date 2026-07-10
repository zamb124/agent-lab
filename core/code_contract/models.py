"""Модели контракта статического анализа кода."""

from __future__ import annotations

from core.models import StrictBaseModel


class CodeContract(StrictBaseModel):
    """Статически выведенный контракт кода.

    - ``reads`` — поля `state`, которые код читает.
    - ``writes`` — поля `state`, которые код присваивает.
    - ``return_keys`` — ключи словаря/объекта, возвращаемого кодом.
    """

    reads: list[str]
    writes: list[str]
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
