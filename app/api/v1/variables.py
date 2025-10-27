"""
API для управления переменными компании.
"""

import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any

from app.core.container import get_container

logger = logging.getLogger(__name__)

router = APIRouter()


class VariableRequest(BaseModel):
    """Запрос на установку переменной"""
    key: str
    value: str
    secret: bool = False
    groups: list[str] = []
    description: str = ""


class VariableResponse(BaseModel):
    """Ответ после установки переменной"""
    success: bool
    key: str


@router.post("/admin/variables")
async def set_variable(request: VariableRequest):
    """
    Устанавливает переменную компании.
    
    Примеры:
    - key=telegram_bot_token, value=123:ABC..., secret=true
    - key=bot_name, value=My Bot, secret=false
    """
    variables_service = get_container().variables_service
    
    await variables_service.set_var(
        key=request.key,
        value=request.value,
        is_secret=request.secret,
        groups=request.groups,
        description=request.description
    )
    
    return VariableResponse(
        success=True,
        key=request.key
    )


@router.get("/admin/variables")
async def list_variables() -> Dict[str, Any]:
    """Получает все переменные компании"""
    variables_service = get_container().variables_service
    return await variables_service.list_vars()


@router.get("/admin/variables/{key}")
async def get_variable(key: str) -> Dict[str, Any]:
    """Получает переменную компании со всеми данными"""
    variables_service = get_container().variables_service
    storage_key = f"var:{key}"
    import json
    data = await variables_service.storage.get(storage_key)
    
    if not data:
        raise HTTPException(status_code=404, detail=f"Variable {key} not found")
    
    var_data = json.loads(data)
    
    return {
        "key": key,
        "value": var_data.get("value", ""),
        "secret": var_data.get("secret", False),
        "groups": var_data.get("groups", []),
        "description": var_data.get("description", "")
    }


@router.delete("/admin/variables/{key}")
async def delete_variable(key: str):
    """Удаляет переменную компании"""
    variables_service = get_container().variables_service
    success = await variables_service.delete_var(key)
    
    if not success:
        raise HTTPException(status_code=404, detail=f"Variable {key} not found")
    
    return {
        "success": True,
        "key": key,
        "message": "Variable deleted"
    }

