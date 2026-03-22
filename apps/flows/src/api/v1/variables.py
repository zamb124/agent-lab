"""
API endpoints для переменных.
"""

from datetime import datetime
from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from apps.flows.src.container import FlowContainer, get_container
from core.context import get_context
from core.db.repositories.variable_repository import Variable
from core.logging import get_logger
from core.variables import VariableResolver

logger = get_logger(__name__)

router = APIRouter(tags=["variables"])


async def get_container_dep() -> FlowContainer:
    """Dependency для получения контейнера"""
    return get_container()


class VariableCreateRequest(BaseModel):
    """Запрос на создание переменной"""

    key: str
    value: Any
    secret: bool = False


class VariableResponse(BaseModel):
    """Ответ с данными переменной"""

    key: str
    value: Any
    secret: bool
    system: bool = False


@router.get("/", response_model=List[VariableResponse])
async def list_variables(
    container: FlowContainer = Depends(get_container_dep),
) -> List[VariableResponse]:
    """Список всех переменных (включая системные)"""
    # Получаем пользовательские переменные из БД
    db_variables = await container.variable_repository.list_all()
    result = [
        VariableResponse(key=v.key, value="***" if v.secret else v.value, secret=v.secret, system=False)
        for v in db_variables
    ]
    
    # Добавляем системные переменные (всегда доступны)
    now = datetime.now()
    system_variables = {
        "current_date": now.strftime("%Y-%m-%d"),
        "current_time": now.strftime("%H:%M"),
        "current_datetime": now.strftime("%Y-%m-%d %H:%M:%S"),
        "current_year": now.year,
        "current_month": now.month,
        "current_day": now.day,
    }
    
    for key, value in system_variables.items():
        result.append(
            VariableResponse(key=key, value=value, secret=False, system=True)
        )
    
    # Добавляем переменные пользователя (из контекста, если доступны)
    context = get_context()
    if context and context.user:
        result.append(
            VariableResponse(key="user_id", value=context.user.user_id, secret=False, system=True)
        )
        result.append(
            VariableResponse(key="user_name", value=context.user.name, secret=False, system=True)
        )
        if context.metadata.get("email"):
            result.append(
                VariableResponse(key="user_email", value=context.metadata["email"], secret=False, system=True)
            )
    
    return result


@router.get("/{key}", response_model=VariableResponse)
async def get_variable(
    key: str, 
    unmask: bool = False,
    container: FlowContainer = Depends(get_container_dep)
) -> VariableResponse:
    """Получает переменную по ключу (включая системные)
    
    Args:
        key: Ключ переменной
        unmask: Если True, возвращает реальное значение даже для secret переменных
    """
    # Проверяем системные переменные (всегда доступны)
    now = datetime.now()
    system_variables = {
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
    request: VariableCreateRequest, container: FlowContainer = Depends(get_container_dep)
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

    await container.variable_repository.set(variable)

    return VariableResponse(
        key=variable.key, value="***" if variable.secret else variable.value, secret=variable.secret, system=False
    )


@router.delete("/{key}")
async def delete_variable(
    key: str, container: FlowContainer = Depends(get_container_dep)
) -> dict:
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
