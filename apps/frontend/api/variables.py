"""
API для работы с переменными.
"""

import logging
from fastapi import APIRouter, HTTPException
from typing import List, Any, Dict
from pydantic import BaseModel


from core.variables import VariableResolver
from core.context import get_context
from apps.agents.dependencies import get_variables_service
from apps.agents.container import get_agents_container
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/variables", tags=["variables"])


class VariableRequest(BaseModel):
    """Запрос на установку переменной"""
    key: str
    value: str
    secret: bool = False
    groups: list[str] = []
    description: str = ""


@router.get("/admin/variables")
async def list_variables() -> Dict[str, Any]:
    """Получить все переменные компании"""
    variables_service = get_agents_container().variables_service
    return await variables_service.list_vars()


@router.post("/admin/variables")
async def set_variable(request: VariableRequest):
    """Установить переменную компании"""
    variables_service = get_agents_container().variables_service
    
    await variables_service.set_var(
        key=request.key,
        value=request.value,
        is_secret=request.secret,
        groups=request.groups,
        description=request.description
    )
    
    return {"success": True, "key": request.key}


@router.get("/admin/variables/{key}")
async def get_variable(key: str) -> Dict[str, Any]:
    """Получить переменную компании"""
    variables_service = get_agents_container().variables_service
    variable_repo = variables_service.variable_repository
    
    variable = await variable_repo.get(key)
    
    if not variable:
        raise HTTPException(status_code=404, detail=f"Variable {key} not found")
    
    return {
        "key": key,
        "value": variable.value if not variable.secret else "***",
        "secret": variable.secret,
        "groups": variable.groups,
        "description": variable.description
    }


@router.put("/admin/variables/{key}")
async def update_variable(key: str, request: VariableRequest):
    """Обновить переменную компании"""
    variables_service = get_agents_container().variables_service
    
    await variables_service.set_var(
        key=key,
        value=request.value,
        is_secret=request.secret,
        groups=request.groups,
        description=request.description
    )
    
    return {"success": True, "key": key}


@router.delete("/admin/variables/{key}")
async def delete_variable(key: str):
    """Удалить переменную компании"""
    variables_service = get_agents_container().variables_service
    success = await variables_service.delete_var(key)
    
    if not success:
        raise HTTPException(status_code=404, detail=f"Variable {key} not found")
    
    return {"success": True, "key": key}


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
    store: List[Variable]


@router.get("/flow/{flow_id}", response_model=VariablesResponse)
async def get_flow_variables(flow_id: str) -> VariablesResponse:
    """
    Получить все доступные переменные для flow.
    
    Возвращает:
    - Системные переменные (текущая дата, время и т.д.)
    - Переменные компании
    - Переменные пользователя
    - Переменные flow
    - Локальные переменные агента
    - Session Store переменные агента
    """
    # Для нового flow возвращаем пустые переменные (только системные и компании/пользователя)
    if flow_id == 'new':
        flow_config = None
        agent_config = None
    else:
        # Получаем flow config
        agents_container = get_agents_container()
        flow_repo = agents_container.flow_repository
        agent_repo = agents_container.agent_repository
        
        flow_config = await flow_repo.get(flow_id)
        if not flow_config:
            raise HTTPException(status_code=404, detail="Flow not found")
        
        # Получаем agent config
        agent_config = None
        if flow_config.entry_point_agent:
            agent_config = await agent_repo.get(flow_config.entry_point_agent)
    
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
    
    # Переменные flow (резолвим значения + показываем description из company vars)
    flow_vars = []
    logger.info(f"🔍 Flow variables для {flow_id}: {flow_config.variables if hasattr(flow_config, 'variables') else 'НЕТ'}")
    if hasattr(flow_config, 'variables') and flow_config.variables:
        # Резолвим @var:key для показа значений
        variables_service = await get_variables_service()
        resolved_flow_vars = await variables_service.resolve(flow_config.variables, auto_create=True)
        logger.info(f"✅ Резолвнутые flow variables: {resolved_flow_vars}")
        
        def flatten_vars(obj, prefix=""):
            """Разворачивает вложенные dict/list в плоский список"""
            result = []
            if isinstance(obj, dict):
                for k, v in obj.items():
                    full_key = f"{prefix}.{k}" if prefix else k
                    if isinstance(v, (dict, list)):
                        result.extend(flatten_vars(v, full_key))
                    else:
                        result.append((full_key, v))
            elif isinstance(obj, list):
                for i, v in enumerate(obj):
                    full_key = f"{prefix}[{i}]"
                    if isinstance(v, (dict, list)):
                        result.extend(flatten_vars(v, full_key))
                    else:
                        result.append((full_key, v))
            else:
                result.append((prefix, obj))
            return result
        
        # Flatten для нерезолвнутых (оригинальных) переменных
        flat_vars_orig = flatten_vars(flow_config.variables)
        # Flatten для резолвнутых значений
        flat_vars_resolved = flatten_vars(resolved_flow_vars)
        
        for (key, orig_value), (_, resolved_value) in zip(flat_vars_orig, flat_vars_resolved):
            # Description и ссылка из company variable
            description = "Flow переменная"
            value_display = str(resolved_value)
            
            if isinstance(orig_value, str) and orig_value.startswith("@var:"):
                var_key = orig_value[5:]
                comp_var = next((v for v in company_vars if v.name == var_key), None)
                
                # Формируем description с указанием ссылки (подсвечиваем)
                ref_text = f"Ссылка: <code style='color: var(--primary-color); background: var(--primary-color-alpha); padding: 0.2rem 0.4rem; border-radius: 4px; font-size: 0.85em;'>{orig_value}</code>"
                if comp_var and comp_var.description:
                    description = f"{comp_var.description} ({ref_text})"
                else:
                    description = ref_text
                
                # Если значение отличается от ссылки - показываем оба
                if str(resolved_value) != orig_value:
                    value_display = f"{resolved_value}"
            
            flow_vars.append(Variable(
                name=key,
                description=description,
                category="flow",
                value=value_display,
                editable=True
            ))
    
    # Локальные переменные агента
    local_vars = []
    if agent_config and hasattr(agent_config, 'local_variables') and agent_config.local_variables:
        for key, value in agent_config.local_variables.items():
            local_vars.append(Variable(
                name=key,
                description="Локальная переменная агента",
                category="local",
                value=value,
                editable=True
            ))
    
    # Session Store переменные агента
    store_vars = []
    if agent_config and hasattr(agent_config, 'store') and agent_config.store:
        for key, value in agent_config.store.items():
            store_vars.append(Variable(
                name=key,
                description="Session Store переменная",
                category="store",
                value=value,
                editable=True
            ))
    
    return VariablesResponse(
        system=system_vars,
        company=company_vars,
        user=user_vars,
        flow=flow_vars,
        local=local_vars,
        store=store_vars
    )
