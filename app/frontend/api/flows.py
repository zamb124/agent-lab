"""
API для работы с флоу в Builder.
"""

import logging
from fastapi import APIRouter, HTTPException
from typing import List, Optional, Dict, Any
import uuid

from app.models import FlowConfig
from app.frontend.dependencies import StorageDep, CanvasServiceDep

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/flows", tags=["builder-flows"])


@router.get("/", response_model=List[FlowConfig])
async def list_flows(storage: StorageDep) -> List[FlowConfig]:
    """Получить список всех флоу"""
    # Получаем все ключи с префиксом "flow:"
    flow_keys = await storage.list_by_prefix("flow:")
    
    flows = []
    for key in flow_keys:
        # Извлекаем flow_id из ключа (убираем префикс компании и "flow:")
        flow_id = key.split(":")[-1]  # Берем последнюю часть после ":"
        flow = await storage.get_flow_config(flow_id)
        if flow:
            flows.append(flow)
    
    return flows


@router.post("/", response_model=FlowConfig)
async def create_flow(
    name: str = "Новый Flow",
    description: Optional[str] = None,
    entry_point_agent: Optional[str] = None,
    storage: StorageDep = None
) -> FlowConfig:
    """Создать новый флоу и сразу сохранить в БД"""
    flow_id = f"flow_{uuid.uuid4().hex[:8]}"
    
    flow_config = FlowConfig(
        flow_id=flow_id,
        name=name,
        description=description or "",
        entry_point_agent=entry_point_agent or "",
        source="canvas_created"
    )
    
    # Сразу сохраняем в БД
    await storage.set_flow_config(flow_config)
    
    return flow_config


@router.get("/{flow_id:path}/canvas")
async def get_flow_canvas(flow_id: str, storage: StorageDep) -> Dict[str, Any]:
    """Получить данные канваса для флоу"""
    flow = await storage.get_flow_config(flow_id)
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
async def get_flow(flow_id: str, storage: StorageDep) -> FlowConfig:
    """Получить флоу по ID"""
    flow = await storage.get_flow_config(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    return flow


@router.put("/{flow_id:path}", response_model=FlowConfig)
async def update_flow(
    flow_id: str,
    updates: Dict[str, Any],
    storage: StorageDep
) -> FlowConfig:
    """Обновить флоу"""
    flow = await storage.get_flow_config(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    
    # Создаем обновленные данные с валидацией через модель
    flow_dict = flow.model_dump()
    
    # Обновляем только разрешенные поля
    allowed_fields = {"name", "description", "entry_point_agent", "platforms", "timeout", "max_retries", "canvas_data"}
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
            
            registration_result = await factory.register_platform(
                platform=platform_name,
                username=username,
                flow_id=validated_flow.flow_id
            )
            logger.info(f"📋 Регистрация {platform_name} для {validated_flow.flow_id}: {registration_result}")
    
    return validated_flow


@router.delete("/{flow_id:path}")
async def delete_flow(flow_id: str, storage: StorageDep):
    """Удалить флоу"""
    flow = await storage.get_flow_config(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    
    await storage.delete_flow_config(flow_id)
    return {"message": "Flow deleted successfully"}
