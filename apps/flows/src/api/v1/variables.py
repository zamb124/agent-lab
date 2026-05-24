"""
API endpoints для переменных.
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from apps.flows.src.dependencies import ContainerDep
from core.context import get_context
from core.db.repositories.variable_repository import Variable
from core.logging import get_logger
from core.models import StrictBaseModel
from core.pagination import OffsetPage
from core.types import JsonObject, JsonValue

logger = get_logger(__name__)

router = APIRouter(tags=["variables"])


class VariableCreateRequest(StrictBaseModel):
    """Запрос на создание переменной"""

    key: str
    value: str
    secret: bool = False


class VariableResponse(StrictBaseModel):
    """Ответ с данными переменной"""

    key: str
    value: JsonValue
    secret: bool
    system: bool = False


@router.get("/", response_model=OffsetPage[VariableResponse])
async def list_variables(
    container: ContainerDep,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OffsetPage[VariableResponse]:
    db_variables = await container.variable_repository.list(limit=limit, offset=offset)
    result = [
        VariableResponse(key=v.key, value="***" if v.secret else v.value, secret=v.secret, system=False)
        for v in db_variables
    ]

    now = datetime.now()
    system_variables: JsonObject = {
        "current_date": now.strftime("%Y-%m-%d"),
        "current_time": now.strftime("%H:%M"),
        "current_datetime": now.strftime("%Y-%m-%d %H:%M:%S"),
        "current_year": now.year,
        "current_month": now.month,
        "current_day": now.day,
    }

    for key, value in system_variables.items():
        result.append(VariableResponse(key=key, value=value, secret=False, system=True))

    context = get_context()
    if context and context.user:
        result.append(VariableResponse(key="user_id", value=context.user.user_id, secret=False, system=True))
        result.append(VariableResponse(key="user_name", value=context.user.name, secret=False, system=True))
        if context.metadata.get("email"):
            result.append(VariableResponse(key="user_email", value=context.metadata["email"], secret=False, system=True))

    return OffsetPage[VariableResponse](items=result, total=len(result), limit=limit, offset=offset)


@router.get("/{key}", response_model=VariableResponse)
async def get_variable(
    key: str,
    container: ContainerDep,
    unmask: bool = False,
) -> VariableResponse:
    """Получает переменную по ключу (включая системные)

    Args:
        key: Ключ переменной
        unmask: Если True, возвращает реальное значение даже для secret переменных
    """
    # Проверяем системные переменные (всегда доступны)
    now = datetime.now()
    system_variables: JsonObject = {
        "current_date": now.strftime("%Y-%m-%d"),
        "current_time": now.strftime("%H:%M"),
        "current_datetime": now.strftime("%Y-%m-%d %H:%M:%S"),
        "current_year": now.year,
        "current_month": now.month,
        "current_day": now.day,
    }

    if key in system_variables:
        return VariableResponse(
            key=key, value=system_variables[key], secret=False, system=True
        )

    # Проверяем переменные пользователя (из контекста)
    context = get_context()
    if context and context.user:
        if key == "user_id":
            return VariableResponse(key=key, value=context.user.user_id, secret=False, system=True)
        if key == "user_name":
            return VariableResponse(key=key, value=context.user.name, secret=False, system=True)
        if key == "user_email" and context.metadata.get("email"):
            return VariableResponse(key=key, value=context.metadata["email"], secret=False, system=True)

    # Ищем в БД
    variable = await container.variable_repository.get(key)
    if variable is None:
        raise HTTPException(status_code=404, detail="Variable not found")

    value = variable.value
    if variable.secret and not unmask:
        value = "***"

    return VariableResponse(
        key=variable.key, value=value, secret=variable.secret, system=False
    )


@router.post("/", response_model=VariableResponse)
async def create_variable(
    request: VariableCreateRequest, container: ContainerDep
) -> VariableResponse:
    """Создает переменную

    Нельзя создать системную переменную (current_date, current_time, etc.)
    """
    # Проверяем, не пытаются ли создать системную переменную
    system_keys = {
        "current_date", "current_time", "current_datetime", "current_year", "current_month", "current_day",
        "user_id", "user_name", "user_email"  # Переменные пользователя тоже системные
    }
    if request.key in system_keys:
        raise HTTPException(
            status_code=400,
            detail=f"Variable '{request.key}' is a system variable and cannot be created or modified"
        )

    variable = Variable(key=request.key, value=request.value, secret=request.secret)

    _ = await container.variable_repository.set(variable)

    return VariableResponse(
        key=variable.key, value="***" if variable.secret else variable.value, secret=variable.secret, system=False
    )


@router.delete("/{key}")
async def delete_variable(
    key: str, container: ContainerDep
) -> dict[str, str]:
    """Удаляет переменную

    Нельзя удалить системную переменную (current_date, current_time, etc.)
    """
    # Проверяем, не пытаются ли удалить системную переменную
    system_keys = {
        "current_date", "current_time", "current_datetime", "current_year", "current_month", "current_day",
        "user_id", "user_name", "user_email"  # Переменные пользователя тоже системные
    }
    if key in system_keys:
        raise HTTPException(
            status_code=400,
            detail=f"Variable '{key}' is a system variable and cannot be deleted"
        )

    deleted = await container.variable_repository.delete(key)
    if not deleted:
        raise HTTPException(status_code=404, detail="Variable not found")
    return {"status": "deleted", "key": key}
