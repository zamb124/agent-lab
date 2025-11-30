"""
API для работы с флоу в Builder.

CRUD endpoints для frontend UI.
"""

import logging
from fastapi import APIRouter, HTTPException, Query
from typing import Dict, Any, List
import uuid

from apps.agents.models import AgentConfig, AgentType, CodeMode, FlowConfig
from apps.frontend.dependencies import CanvasServiceDep, FlowRepositoryDep, AgentRepositoryDep, VariablesServiceDep, InterfaceFactoryDep
from apps.agents.container import get_agents_container
from pydantic import BaseModel
from typing import Optional
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/flows", tags=["builder-flows"])


@router.get("/", response_model=List[FlowConfig])
async def list_flows(
    flow_repo: FlowRepositoryDep,
    limit: int = Query(100, ge=1, le=1000)
) -> List[FlowConfig]:
    """Получить список flows"""
    return await flow_repo.list_all(limit=limit)


@router.post("/", response_model=FlowConfig)
async def create_flow(
    flow_data: Dict[str, Any],
    flow_repo: FlowRepositoryDep = None,
    agent_repo: AgentRepositoryDep = None
) -> FlowConfig:
    """Создать новый флоу и сразу сохранить в БД"""
    
    flow_id = flow_data.get("flow_id")
    if not flow_id:
        flow_id = f"flow_{uuid.uuid4().hex[:8]}"
    
    entry_point_agent = flow_data.get("entry_point_agent", "")
    
    if entry_point_agent and not await agent_repo.get(entry_point_agent):
        agent_config = AgentConfig(
            agent_id=entry_point_agent,
            name=flow_data.get("name", "Новый Agent"),
            description=flow_data.get("description", ""),
            type=AgentType.REACT,
            prompt="",
            code_mode=CodeMode.INLINE_CODE,
            source="auto_created"
        )
        await agent_repo.set(agent_config)
    
    flow_config = FlowConfig(
        flow_id=flow_id,
        name=flow_data.get("name", "Новый Flow"),
        description=flow_data.get("description", ""),
        entry_point_agent=entry_point_agent,
        platforms=flow_data.get("platforms", {}),
        timeout=flow_data.get("timeout"),
        max_retries=flow_data.get("max_retries", 3),
        variables=flow_data.get("variables", {}),
        store=flow_data.get("store", {}),
        enable_reasoning=flow_data.get("enable_reasoning", False),
        source="ui_created"
    )
    
    await flow_repo.set(flow_config)
    
    return flow_config


# Специфичные роуты ДОЛЖНЫ быть перед общим /{flow_id:path}

@router.get("/{flow_id:path}/variables")
async def get_flow_variables(
    flow_id: str,
    flow_repo: FlowRepositoryDep,
    agent_repo: AgentRepositoryDep
) -> Dict[str, Any]:
    """
    Получить все переменные flow для автокомплита в code editor.
    Возвращает: variables, store, available_tools
    """
    flow = await flow_repo.get(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    
    available_tools = []
    
    if flow.entry_point_agent:
        agent = await agent_repo.get(flow.entry_point_agent)
        if agent and agent.tools:
            available_tools = [
                {
                    "name": tool.tool_id,
                    "title": tool.title or tool.tool_id,
                    "description": tool.description or ""
                }
                for tool in agent.tools
            ]
    
    return {
        "variables": flow.variables or {},
        "store": flow.store or {},
        "available_tools": available_tools
    }


@router.get("/{flow_id:path}/canvas")
async def get_flow_canvas(flow_id: str, flow_repo: FlowRepositoryDep) -> Dict[str, Any]:
    """Получить данные канваса для флоу"""
    flow = await flow_repo.get(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    
    if flow.canvas_data:
        return {
            "flow_id": flow_id,
            **flow.canvas_data
        }
    
    return {
        "flow_id": flow_id,
        "nodes": [],
        "edges": [],
        "entry_point": None
    }


@router.put("/{flow_id:path}/canvas")
async def update_flow_canvas(
    flow_id: str,
    canvas_data: Dict[str, Any],
    canvas_service: CanvasServiceDep
):
    """Обновить данные канваса для флоу"""
    try:
        await canvas_service.save_canvas_data(flow_id, canvas_data)
        return {"message": "Canvas updated successfully"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


class InstallFlowRequest(BaseModel):
    variables: Optional[Dict[str, str]] = None


@router.post("/{flow_id:path}/install")
async def install_flow(
    flow_id: str,
    flow_repo: FlowRepositoryDep,
    variables_service: VariablesServiceDep,
    request: Optional[InstallFlowRequest] = None,
):
    """
    Установить flow из Store.
    Запускает install() и after_install_hook если они определены в flow.
    """
    migrator = get_agents_container().migrator

    flows_with_ids = await migrator.get_public_flows()

    flow_config = None
    for full_flow_id, flow in flows_with_ids:
        if full_flow_id == flow_id:
            flow_config = flow
            break

    if not flow_config:
        raise HTTPException(status_code=404, detail="Flow не найден в коде")

    if request and request.variables:
        for key, value in request.variables.items():
            if value is None or value == "":
                logger.info(f"Пропускаем пустую переменную {key} для flow {flow_id}")
                continue

            var_def = None
            if hasattr(flow_config, 'variables_definitions') and flow_config.variables_definitions:
                for vd in flow_config.variables_definitions:
                    if vd.key == key:
                        var_def = vd
                        break

            is_secret = var_def.is_secret if var_def else False
            description = var_def.description if var_def else f"Переменная {key}"

            await variables_service.set_var(
                key=key,
                value=value,
                is_secret=is_secret,
                description=description
            )
            logger.info(f"Создана переменная {key} для flow {flow_id}")

    flow_factory = get_agents_container().flow_factory
    result = await flow_factory.install_flow(flow_id)

    logger.info(f"Flow {flow_id} успешно установлен")

    return {
        "message": f"Flow '{flow_config.name}' успешно установлен",
        "flow_id": result["flow_id"],
        "additional_url": result.get("additional_url")
    }


@router.post("/{flow_id:path}/uninstall")
async def uninstall_flow(flow_id: str, flow_repo: FlowRepositoryDep, agent_repo: AgentRepositoryDep):
    """
    Удалить установленный flow.
    """
    flow = await flow_repo.get(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow не найден")
    
    await flow_repo.delete(flow_id)
    
    if flow.entry_point_agent:
        await agent_repo.delete(flow.entry_point_agent)
    
    logger.info(f"Flow {flow_id} успешно удалён")
    
    return {
        "message": f"Flow '{flow.name}' успешно удалён",
        "flow_id": flow_id
    }


# Общие роуты /{flow_id:path} ПОСЛЕ специфичных

@router.get("/{flow_id:path}")
async def get_flow(
    flow_id: str,
    flow_repo: FlowRepositoryDep
) -> FlowConfig:
    """Получить flow по ID"""
    flow = await flow_repo.get(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    return flow


@router.put("/{flow_id:path}", response_model=FlowConfig)
async def update_flow(
    flow_id: str,
    updates: Dict[str, Any],
    flow_repo: FlowRepositoryDep,
    interface_factory: InterfaceFactoryDep
) -> FlowConfig:
    """Обновить флоу"""
    flow = await flow_repo.get(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    
    flow_dict = flow.model_dump(exclude={'flow_id'})

    allowed_fields = {"name", "description", "entry_point_agent", "platforms", "timeout", "max_retries", "canvas_data", "variables", "store", "enable_reasoning", "rag_config"}
    for field, value in updates.items():
        if field in allowed_fields:
            flow_dict[field] = value

    flow_dict['flow_id'] = flow_id
    validated_flow = FlowConfig(**flow_dict)
    
    if "platforms" in updates:
        for platform_name, platform_config in updates["platforms"].items():
            username = platform_config.get("username")
            if not username:
                continue
            
            all_flows = await flow_repo.list_all(limit=1000)
            for other_flow in all_flows:
                if other_flow.flow_id == flow_id:
                    continue
                
                other_platform_config = other_flow.platforms.get(platform_name)
                if other_platform_config and other_platform_config.get("username") == username:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Username {username} уже используется в flow {other_flow.flow_id} ({other_flow.name})"
                    )
    
    await flow_repo.set(validated_flow)
    
    if "platforms" in updates:
        for platform_name, platform_config in updates["platforms"].items():
            username = platform_config.get("username")
            if not username:
                continue
            
            if platform_name == "telegram":
                if not platform_config.get("token"):
                    logger.warning(f"Канал telegram для {validated_flow.flow_id} не имеет token, пропускаем регистрацию")
                    continue
            
            try:
                registration_result = await interface_factory.register_platform(
                    platform=platform_name,
                    username=username,
                    flow_id=validated_flow.flow_id
                )
                logger.info(f"Регистрация {platform_name} для {validated_flow.flow_id}: {registration_result}")
            except ValueError as e:
                logger.error(f"Ошибка регистрации {platform_name}: {e}")
                raise HTTPException(
                    status_code=400,
                    detail=f"Ошибка регистрации {platform_name}: {str(e)}"
                )
            except Exception as e:
                logger.error(f"Неожиданная ошибка регистрации {platform_name}: {e}")
                raise HTTPException(
                    status_code=400,
                    detail=f"Не удалось зарегистрировать {platform_name}: {str(e)}"
                )
    
    return validated_flow
