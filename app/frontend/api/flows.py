"""
API для работы с флоу в Builder.
"""

import logging
from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any
import uuid

from app.models import FlowConfig
from app.frontend.dependencies import StorageDep, CanvasServiceDep, FlowRepositoryDep, AgentRepositoryDep
from app.core.migration import Migrator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/flows", tags=["builder-flows"])


@router.get("/", response_model=List[FlowConfig])
async def list_flows(storage: StorageDep, flow_repo: FlowRepositoryDep) -> List[FlowConfig]:
    """Получить список всех флоу"""
    # Получаем все ключи с префиксом "flow:"
    flow_keys = await storage.list_by_prefix("flow:")
    
    flows = []
    for key in flow_keys:
        # Извлекаем flow_id из ключа (убираем префикс компании и "flow:")
        flow_id = key.split(":")[-1]  # Берем последнюю часть после ":"
        flow = await flow_repo.get(flow_id)
        if flow:
            flows.append(flow)
    
    return flows


@router.post("/", response_model=FlowConfig)
async def create_flow(
    flow_data: Dict[str, Any],
    storage: StorageDep = None,
    flow_repo: FlowRepositoryDep = None,
    agent_repo: AgentRepositoryDep = None
) -> FlowConfig:
    """Создать новый флоу и сразу сохранить в БД"""
    
    flow_id = flow_data.get("flow_id")
    if not flow_id:
        flow_id = f"flow_{uuid.uuid4().hex[:8]}"
    
    entry_point_agent = flow_data.get("entry_point_agent", "")
    
    if entry_point_agent and not await agent_repo.get(entry_point_agent):
        from app.models import AgentConfig, AgentType, CodeMode
        
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
        source="ui_created"
    )
    
    await flow_repo.set(flow_config)
    
    return flow_config


@router.get("/{flow_id:path}/canvas")
async def get_flow_canvas(flow_id: str, storage: StorageDep, flow_repo: FlowRepositoryDep) -> Dict[str, Any]:
    """Получить данные канваса для флоу"""
    flow = await flow_repo.get(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    
    # Получаем данные канваса из FlowConfig
    if flow.canvas_data:
        print(f"Найдены сохраненные данные канваса для флоу {flow_id}")
        print(f"Количество нод: {len(flow.canvas_data.get('nodes', []))}")
        return {
            "flow_id": flow_id,
            **flow.canvas_data
        }
    
    # Если нет сохраненного канваса, возвращаем пустой
    print(f"Нет сохраненных данных канваса для флоу {flow_id}")
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


@router.get("/{flow_id:path}", response_model=FlowConfig)
async def get_flow(flow_id: str, storage: StorageDep, flow_repo: FlowRepositoryDep) -> FlowConfig:
    """Получить флоу по ID"""
    flow = await flow_repo.get(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    return flow


@router.put("/{flow_id:path}", response_model=FlowConfig)
async def update_flow(
    flow_id: str,
    updates: Dict[str, Any],
    storage: StorageDep,
    flow_repo: FlowRepositoryDep
) -> FlowConfig:
    """Обновить флоу"""
    flow = await flow_repo.get(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    
    # Создаем обновленные данные с валидацией через модель
    flow_dict = flow.model_dump()
    
    # Обновляем только разрешенные поля
    allowed_fields = {"name", "description", "entry_point_agent", "platforms", "timeout", "max_retries", "canvas_data", "variables"}
    for field, value in updates.items():
        if field in allowed_fields:
            flow_dict[field] = value
    
    # Валидируем через модель - валидаторы автоматически преобразуют типы
    validated_flow = FlowConfig(**flow_dict)
    
    # Если обновили platforms - проверяем уникальность username
    if "platforms" in updates:
        for platform_name, platform_config in updates["platforms"].items():
            username = platform_config.get("username")
            if not username:
                continue
            
            # Ищем все flow с этим username на этой платформе
            all_keys = await storage.list_by_prefix("", limit=1000, force_global=True)
            for key in all_keys:
                if ":flow:" not in key:
                    continue
                
                other_flow_data = await storage.get(key, force_global=True)
                if not other_flow_data:
                    continue
                
                other_flow = FlowConfig.model_validate_json(other_flow_data)
                if other_flow.flow_id == flow_id:
                    continue
                
                other_platform_config = other_flow.platforms.get(platform_name)
                if other_platform_config and other_platform_config.get("username") == username:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Username {username} уже используется в flow {other_flow.flow_id} ({other_flow.name})"
                    )
    
    await storage.set_flow_config(validated_flow)
    
    # Если обновили platforms - регистрируем их
    if "platforms" in updates:
        from app.interfaces.factory import InterfaceFactory
        
        factory = InterfaceFactory()
        
        for platform_name, platform_config in updates["platforms"].items():
            username = platform_config.get("username")
            if not username:
                continue
            
            # Проверяем что есть token для платформ требующих его
            if platform_name == "telegram":
                if not platform_config.get("token"):
                    logger.warning(f"⚠️ Платформа telegram для {validated_flow.flow_id} не имеет token, пропускаем регистрацию")
                    continue
            
            try:
                registration_result = await factory.register_platform(
                    platform=platform_name,
                    username=username,
                    flow_id=validated_flow.flow_id
                )
                logger.info(f"📋 Регистрация {platform_name} для {validated_flow.flow_id}: {registration_result}")
            except ValueError as e:
                logger.error(f"❌ Ошибка регистрации {platform_name}: {e}")
                raise HTTPException(
                    status_code=400,
                    detail=f"Ошибка регистрации {platform_name}: {str(e)}"
                )
            except Exception as e:
                logger.error(f"❌ Неожиданная ошибка регистрации {platform_name}: {e}")
                raise HTTPException(
                    status_code=400,
                    detail=f"Не удалось зарегистрировать {platform_name}: {str(e)}"
                )
    
    return validated_flow


@router.delete("/{flow_id:path}")
async def delete_flow(flow_id: str, storage: StorageDep, flow_repo: FlowRepositoryDep):
    """Удалить флоу"""
    flow = await flow_repo.get(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    
    await flow_repo.delete(flow_id)
    return {"message": "Flow deleted successfully"}


@router.post("/{flow_id:path}/install")
async def install_flow(flow_id: str, storage: StorageDep, flow_repo: FlowRepositoryDep):
    """
    Установить flow из Store.
    Запускает install() и after_install_hook если они определены в flow.
    """
    from app.core.flow_factory import FlowFactory
    
    migrator = Migrator()
    migrator.storage = storage
    
    flows_with_ids = await migrator.get_public_flows()
    
    flow_config = None
    for full_flow_id, flow in flows_with_ids:
        if full_flow_id == flow_id:
            flow_config = flow
            break
    
    if not flow_config:
        raise HTTPException(status_code=404, detail="Flow не найден в коде")
    
    flow_factory = FlowFactory()
    result = await flow_factory.install_flow(flow_id)
    
    logger.info(f"✅ Flow {flow_id} успешно установлен")
    logger.info(f"📋 Result from install_flow: {result}")
    
    response_data = {
        "message": f"Flow '{flow_config.name}' успешно установлен",
        "flow_id": result["flow_id"],
        "additional_url": result.get("additional_url")
    }
    logger.info(f"📤 Returning response: {response_data}")
    
    return response_data


@router.post("/{flow_id:path}/uninstall")
async def uninstall_flow(flow_id: str, storage: StorageDep, flow_repo: FlowRepositoryDep):
    """
    Удалить установленный flow.
    Запускает uninstall() хук если он определен в flow.
    """
    flow = await flow_repo.get(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow не найден")
    
    await flow_repo.delete(flow_id)
    
    if flow.entry_point_agent:
        await storage.delete_agent_config(flow.entry_point_agent)
    
    logger.info(f"✅ Flow {flow_id} успешно удалён")
    
    return {
        "message": f"Flow '{flow.name}' успешно удалён",
        "flow_id": flow_id
    }
