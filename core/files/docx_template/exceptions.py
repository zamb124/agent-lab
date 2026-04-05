"""
Исключения рендера DOCX-шаблонов (docxtpl / Jinja2 в документе).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from core.errors import ImanBaseError


class DocxTemplateError(ImanBaseError):
    code = "DOCX_TEMPLATE_ERROR"
    message = "Ошибка шаблонизации DOCX"


class DocxTemplateInvalidError(DocxTemplateError):
    """Файл не является корректным DOCX (ZIP OOXML) или пустой."""

    code = "DOCX_TEMPLATE_INVALID"
    message = "Некорректный или пустой DOCX-шаблон"

    def __init__(
        self,
        message: Optional[str] = None,
        *,
        reason: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        payload: Dict[str, Any] = {}
        if reason:
            payload["reason"] = reason
        super().__init__(
            message=message or self.message,
            payload=payload,
            **kwargs,
        )


class DocxTemplateSyntaxError(DocxTemplateError):
    """Синтаксическая ошибка Jinja2 в XML шаблона."""

    code = "DOCX_TEMPLATE_SYNTAX"
    message = "Синтаксическая ошибка в шаблоне DOCX"

    def __init__(
        self,
        message: str,
        *,
        line: Optional[int] = None,
        name: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        payload: Dict[str, Any] = {"detail": message}
        if line is not None:
            payload["line"] = line
        if name is not None:
            payload["name"] = name
        super().__init__(message=message, payload=payload, **kwargs)


class DocxTemplateSourceError(DocxTemplateError):
    """Шаблон не найден в списке files, нет path или файл отсутствует на диске."""

    code = "DOCX_TEMPLATE_SOURCE"
    message = "Не удалось загрузить шаблон DOCX из files"


class DocxTemplateContextError(DocxTemplateError):
    """Контекст не соответствует шаблону (strict) или содержит неподдерживаемые типы."""

    code = "DOCX_TEMPLATE_CONTEXT"
    message = "Ошибка контекста шаблона DOCX"

    def __init__(
        self,
        message: str,
        *,
        missing_variables: Optional[List[str]] = None,
        extra_keys: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> None:
        payload: Dict[str, Any] = {"detail": message}
        if missing_variables is not None:
            payload["missing_variables"] = missing_variables
        if extra_keys is not None:
            payload["extra_keys"] = extra_keys
        super().__init__(message=message, payload=payload, **kwargs)


__all__ = [
    "DocxTemplateError",
    "DocxTemplateInvalidError",
    "DocxTemplateSourceError",
    "DocxTemplateSyntaxError",
    "DocxTemplateContextError",
]
