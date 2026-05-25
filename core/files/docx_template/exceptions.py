"""
Исключения рендера DOCX-шаблонов (docxtpl / Jinja2 в документе).
"""

from __future__ import annotations

from core.errors import ImanBaseError
from core.types import JsonObject


class DocxTemplateError(ImanBaseError):
    code: str = "DOCX_TEMPLATE_ERROR"
    message: str = "Ошибка шаблонизации DOCX"


class DocxTemplateInvalidError(DocxTemplateError):
    """Файл не является корректным DOCX (ZIP OOXML) или пустой."""

    code: str = "DOCX_TEMPLATE_INVALID"
    message: str = "Некорректный или пустой DOCX-шаблон"

    def __init__(
        self,
        message: str | None = None,
        *,
        reason: str | None = None,
    ) -> None:
        payload: JsonObject = {}
        if reason is not None:
            payload["reason"] = reason
        super().__init__(
            message=message or self.message,
            payload=payload,
        )


class DocxTemplateSyntaxError(DocxTemplateError):
    """Синтаксическая ошибка Jinja2 в XML шаблона."""

    code: str = "DOCX_TEMPLATE_SYNTAX"
    message: str = "Синтаксическая ошибка в шаблоне DOCX"

    def __init__(
        self,
        message: str,
        *,
        line: int | None = None,
        name: str | None = None,
    ) -> None:
        payload: JsonObject = {"detail": message}
        if line is not None:
            payload["line"] = line
        if name is not None:
            payload["name"] = name
        super().__init__(message=message, payload=payload)


class DocxTemplateSourceError(DocxTemplateError):
    """Шаблон не найден в списке files, нет path или файл отсутствует на диске."""

    code: str = "DOCX_TEMPLATE_SOURCE"
    message: str = "Не удалось загрузить шаблон DOCX из files"


class DocxTemplateContextError(DocxTemplateError):
    """Контекст не соответствует шаблону (strict) или содержит неподдерживаемые типы."""

    code: str = "DOCX_TEMPLATE_CONTEXT"
    message: str = "Ошибка контекста шаблона DOCX"

    def __init__(
        self,
        message: str,
        *,
        missing_variables: list[str] | None = None,
        extra_keys: list[str] | None = None,
    ) -> None:
        payload: JsonObject = {"detail": message}
        if missing_variables is not None:
            payload["missing_variables"] = missing_variables
        if extra_keys is not None:
            payload["extra_keys"] = extra_keys
        super().__init__(message=message, payload=payload)


__all__ = [
    "DocxTemplateError",
    "DocxTemplateInvalidError",
    "DocxTemplateSourceError",
    "DocxTemplateSyntaxError",
    "DocxTemplateContextError",
]
