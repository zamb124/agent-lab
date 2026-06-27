"""
FastAPI Dependencies для HumanitecAgent.
"""


from fastapi import HTTPException

from core.context import Context, get_context
from core.models.identity_models import Company, User


def require_context() -> Context:
    context = get_context()
    if context is None:
        raise HTTPException(status_code=401, detail="Необходима авторизация")
    return context


def require_user() -> User:
    return require_context().user


def require_active_company() -> Company:
    company = require_context().active_company
    if company is None:
        raise HTTPException(status_code=400, detail="Компания не выбрана")
    return company
