"""
FastAPI Dependencies для Frontend сервиса
"""
from typing import Annotated

from fastapi import Depends, HTTPException

from apps.frontend.container import FrontendContainer, get_frontend_container
from core.context import Context, get_context
from core.models.identity_models import Company, User


def get_container() -> FrontendContainer:
    """Dependency для получения контейнера"""
    return get_frontend_container()


def require_frontend_context() -> Context:
    context = get_context()
    if context is None:
        raise HTTPException(status_code=401, detail="Необходима авторизация")
    return context


def require_frontend_user() -> User:
    return require_frontend_context().user


def require_frontend_active_company() -> Company:
    company = require_frontend_context().active_company
    if company is None:
        raise HTTPException(status_code=400, detail="Компания не выбрана")
    return company


ContainerDep = Annotated[FrontendContainer, Depends(get_container)]

