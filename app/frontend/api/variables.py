"""
API для работы с переменными.
"""

from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any
from pydantic import BaseModel

from app.frontend.dependencies import StorageDep
from app.core.variables import VariableResolver
from app.core.context import get_context

router = APIRouter(prefix="/variables", tags=["variables"])


class Variable(BaseModel):
    """Модель переменной для API"""
    name: str
    description: str
    category: str
    value: Any = None
    editable: bool = False


class VariablesResponse(BaseModel):
    """Ответ с переменными"""
    system: List[Variable]
    company: List[Variable]
    user: List[Variable]
    flow: List[Variable]
    local: List[Variable]


@router.get("/flow/{flow_id}", response_model=VariablesResponse)
async def get_flow_variables(flow_id: str, storage: StorageDep) -> VariablesResponse:
    """
    Получить все доступные переменные для flow.
    
    Возвращает:
    - Системные переменные (текущая дата, время и т.д.)
    - Переменные компании
    - Переменные пользователя
    - Переменные flow
    - Локальные переменные агента
    """
    # Получаем flow config
    flow_config = await storage.get_flow_config(flow_id)
    if not flow_config:
        raise HTTPException(status_code=404, detail="Flow not found")
    
    # Получаем agent config
    agent_config = None
    if flow_config.entry_point_agent:
        agent_config = await storage.get_agent_config(flow_config.entry_point_agent)
    
    # Резолвим все переменные
    context = get_context()
    all_variables = VariableResolver.resolve_all()
    
    # Системные переменные
    system_vars = [
        Variable(
            name="current_date",
            description="Текущая дата (YYYY-MM-DD)",
            category="system",
            value=all_variables.get("current_date"),
            editable=False
        ),
        Variable(
            name="current_time",
            description="Текущее время (HH:MM)",
            category="system",
            value=all_variables.get("current_time"),
            editable=False
        ),
        Variable(
            name="current_datetime",
            description="Дата и время",
            category="system",
            value=all_variables.get("current_datetime"),
            editable=False
        ),
        Variable(
            name="current_year",
            description="Текущий год",
            category="system",
            value=all_variables.get("current_year"),
            editable=False
        ),
        Variable(
            name="current_month",
            description="Текущий месяц",
            category="system",
            value=all_variables.get("current_month"),
            editable=False
        ),
        Variable(
            name="current_day",
            description="Текущий день",
            category="system",
            value=all_variables.get("current_day"),
            editable=False
        ),
    ]
    
    # Переменные компании
    company_vars = []
    if context and context.active_company:
        company_vars = [
            Variable(
                name="company_name",
                description="Название компании",
                category="company",
                value=context.active_company.name,
                editable=False
            ),
            Variable(
                name="company_id",
                description="ID компании",
                category="company",
                value=context.active_company.company_id,
                editable=False
            ),
            Variable(
                name="company_subdomain",
                description="Поддомен компании",
                category="company",
                value=context.active_company.subdomain,
                editable=False
            ),
        ]
        
        if context.company_variables:
            for key, value in context.company_variables.items():
                company_vars.append(Variable(
                    name=key,
                    description=f"Переменная компании: {key}",
                    category="company",
                    value=value,
                    editable=True
                ))
    
    # Переменные пользователя
    user_vars = []
    if context and context.user:
        user_vars = [
            Variable(
                name="user_name",
                description="Имя пользователя",
                category="user",
                value=context.user.name,
                editable=False
            ),
            Variable(
                name="user_id",
                description="ID пользователя",
                category="user",
                value=context.user.user_id,
                editable=False
            ),
        ]
    
    # Переменные flow
    flow_vars = []
    if hasattr(flow_config, 'variables') and flow_config.variables:
        for key, value in flow_config.variables.items():
            flow_vars.append(Variable(
                name=key,
                description=f"Flow переменная",
                category="flow",
                value=value,
                editable=True
            ))
    
    # Локальные переменные агента
    local_vars = []
    if agent_config and hasattr(agent_config, 'local_variables') and agent_config.local_variables:
        for key, value in agent_config.local_variables.items():
            local_vars.append(Variable(
                name=key,
                description=f"Локальная переменная агента",
                category="local",
                value=value,
                editable=True
            ))
    
    return VariablesResponse(
        system=system_vars,
        company=company_vars,
        user=user_vars,
        flow=flow_vars,
        local=local_vars
    )
