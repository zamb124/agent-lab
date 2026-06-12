"""
Рендер DOCX по шаблону docxtpl (Jinja2 в OOXML). Только bytes + context → bytes.
"""

from __future__ import annotations

import zipfile
from io import BytesIO

from docxtpl import DocxTemplate
from jinja2 import Environment, StrictUndefined
from jinja2.exceptions import TemplateSyntaxError, UndefinedError

from core.files.docx_template.exceptions import (
    DocxTemplateContextError,
    DocxTemplateInvalidError,
    DocxTemplateSyntaxError,
)
from core.files.docx_template.normalize import normalize_template_context
from core.types import DocxTemplateContext


def _validate_docx_zip(template_bytes: bytes) -> None:
    if not template_bytes:
        raise DocxTemplateInvalidError(
            reason="empty",
            message="Шаблон DOCX пустой (0 байт)",
        )
    if not template_bytes.startswith(b"PK"):
        raise DocxTemplateInvalidError(
            reason="not_zip",
            message="Файл не похож на DOCX (ожидается ZIP OOXML)",
        )
    bio = BytesIO(template_bytes)
    if not zipfile.is_zipfile(bio):
        raise DocxTemplateInvalidError(
            reason="invalid_zip",
            message="Байты не являются корректным ZIP (невалидный DOCX)",
        )


def render_docx_template_bytes(
    template_bytes: bytes,
    context: DocxTemplateContext,
    *,
    strict: bool = False,
    date_iso: bool = True,
) -> bytes:
    """
    Подставляет context в шаблон .docx (синтаксис Jinja2 в тексте Word, см. docxtpl).

    Шаблон считается доверенным. Контекст нормализуется: только скаляры, list, dict,
    date/datetime (ISO при date_iso), Decimal; объекты RichText/InlineImage docxtpl допускаются.

    strict=True: каждая переменная верхнего уровня из шаблона должна быть в context;
    лишние ключи верхнего уровня в context запрещены; при рендере используется StrictUndefined.
    """
    _validate_docx_zip(template_bytes)
    normalized = normalize_template_context(context, date_iso=date_iso)

    env_plain = Environment()

    if strict:
        analyze_tpl = DocxTemplate(BytesIO(template_bytes))
        all_vars = analyze_tpl.get_undeclared_template_variables(jinja_env=env_plain)
        missing = analyze_tpl.get_undeclared_template_variables(
            jinja_env=env_plain,
            context=normalized,
        )
        if missing:
            raise DocxTemplateContextError(
                message=(
                    "В контексте не хватает переменных, используемых в шаблоне: "
                    + ", ".join(sorted(missing))
                ),
                missing_variables=sorted(missing),
            )
        extra = set(normalized.keys()) - all_vars
        if extra:
            raise DocxTemplateContextError(
                message=(
                    "В контексте есть лишние ключи верхнего уровня относительно шаблона: "
                    + ", ".join(sorted(extra))
                ),
                extra_keys=sorted(extra),
            )

    tpl = DocxTemplate(BytesIO(template_bytes))
    jinja_env = Environment(undefined=StrictUndefined) if strict else Environment()

    try:
        tpl.render(normalized, jinja_env=jinja_env, autoescape=False)
    except TemplateSyntaxError as exc:
        raise DocxTemplateSyntaxError(
            message=str(exc),
            line=exc.lineno,
            name=exc.name,
        ) from exc
    except UndefinedError as exc:
        raise DocxTemplateContextError(
            message=f"Неопределённая переменная в шаблоне: {exc}",
        ) from exc

    out = BytesIO()
    tpl.save(out)
    data = out.getvalue()
    if not data:
        raise DocxTemplateInvalidError(
            reason="render_empty",
            message="После рендера получен пустой DOCX",
        )
    return data


__all__ = ["render_docx_template_bytes"]
