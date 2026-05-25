"""
Переменные flow из авторизованного HTTP-контекста (JWT → Context.user / company).

Попадают в state.variables и в шаблоны промптов ({user_name}, {?user_email}, …).
Клиентский metadata.variables не может их перезаписать: мерж в BaseChannel.process_task идёт после запросных variables.
"""

from __future__ import annotations

from core.models.context_models import Context
from core.models.i18n_models import Language
from core.types import JsonObject


def flow_variables_from_request_context(context: Context | None) -> JsonObject:
    """
    Словарь скаляров для runtime_flow.variables / ExecutionState.variables.

    Без секретов: токен в промпт не передаётся.
    """
    if context is None:
        return {}

    user = context.user
    primary_email = ""
    if user.emails:
        primary_email = user.emails[0]

    company_id = ""
    company_name = ""
    if context.active_company is not None:
        company_id = context.active_company.company_id
        company_name = context.active_company.name or ""

    lang = context.language.value
    if context.language == Language.EN:
        interface_language_code = "en"
        interface_language_name = "английском"
    else:
        interface_language_code = "ru"
        interface_language_name = "русском"

    active_namespace = (context.active_namespace or "").strip()
    if not active_namespace:
        raise ValueError(
            "flow_variables_from_request_context: Context.active_namespace пуст — "
            "переменная active_namespace для промпта не определена (Zero-Guess)."
        )

    return {
        "user_id": user.user_id,
        "user_name": user.name or "",
        "user_email": primary_email,
        "user_first_name": user.first_name or "",
        "user_last_name": user.last_name or "",
        "company_id": company_id,
        "company_name": company_name,
        "active_namespace": active_namespace,
        "user_language": lang,
        "interface_language_code": interface_language_code,
        "interface_language_name": interface_language_name,
    }
