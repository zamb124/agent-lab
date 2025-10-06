"""
API для работы с флоу в Builder.
"""

from fastapi import APIRouter, HTTPException
from typing import List, Optional, Dict, Any
import uuid

from app.models import FlowConfig
from app.frontend.dependencies import StorageDep, CanvasServiceDep

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
    
    await storage.set_flow_config(validated_flow)
    return validated_flow


@router.delete("/{flow_id:path}")
async def delete_flow(flow_id: str, storage: StorageDep):
    """Удалить флоу"""
    flow = await storage.get_flow_config(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    
    await storage.delete_flow_config(flow_id)
    return {"message": "Flow deleted successfully"}
