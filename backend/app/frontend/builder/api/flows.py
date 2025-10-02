"""
API для работы с флоу в Builder.
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import List, Optional, Dict, Any
import uuid
import json

from app.models import FlowConfig, AgentConfig, ToolReference, AgentType, CodeMode
from app.core.storage import Storage
from app.core.container import get_container

router = APIRouter(prefix="/flows", tags=["builder-flows"])


async def get_storage() -> Storage:
    """Получить Storage из контейнера"""
    container = get_container()
    return container.get_storage()


@router.get("/", response_model=List[FlowConfig])
async def list_flows(storage: Storage = Depends(get_storage)) -> List[FlowConfig]:
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


@router.get("/{flow_id}", response_model=FlowConfig)
async def get_flow(flow_id: str, storage: Storage = Depends(get_storage)) -> FlowConfig:
    """Получить флоу по ID"""
    flow = await storage.get_flow_config(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    return flow


@router.post("/", response_model=FlowConfig)
async def create_flow(
    name: str = "Новый Flow",
    description: Optional[str] = None,
    entry_point_agent: Optional[str] = None,
    storage: Storage = Depends(get_storage)
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


@router.put("/{flow_id}", response_model=FlowConfig)
async def update_flow(
    flow_id: str,
    updates: Dict[str, Any],
    storage: Storage = Depends(get_storage)
) -> FlowConfig:
    """Обновить флоу"""
    flow = await storage.get_flow_config(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    
    # Обновляем только разрешенные поля
    allowed_fields = {"name", "description", "entry_point_agent", "platforms", "timeout", "max_retries", "canvas_data"}
    for field, value in updates.items():
        if field in allowed_fields:
            setattr(flow, field, value)
    
    await storage.set_flow_config(flow)
    return flow


@router.delete("/{flow_id}")
async def delete_flow(flow_id: str, storage: Storage = Depends(get_storage)):
    """Удалить флоу"""
    flow = await storage.get_flow_config(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    
    await storage.delete_flow_config(flow_id)
    return {"message": "Flow deleted successfully"}


@router.get("/{flow_id}/canvas")
async def get_flow_canvas(flow_id: str, storage: Storage = Depends(get_storage)) -> Dict[str, Any]:
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


@router.put("/{flow_id}/canvas")
async def update_flow_canvas(
    flow_id: str,
    canvas_data: Dict[str, Any],
    storage: Storage = Depends(get_storage)
):
    """Обновить данные канваса для флоу"""
    flow = await storage.get_flow_config(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    
    print(f"Сохраняем данные канваса для флоу {flow_id}")
    print(f"Количество нод: {len(canvas_data.get('nodes', []))}")
    print(f"Количество связей: {len(canvas_data.get('edges', []))}")
    
    # Обновляем entry_point_agent для Flow на основе связей
    await update_flow_entry_point(flow, canvas_data, storage)
    
    # Сохраняем данные канваса прямо в FlowConfig
    flow.canvas_data = canvas_data
    await storage.set_flow_config(flow)
    
    print(f"✅ Данные канваса сохранены в FlowConfig")
    
    # Обновляем агентов на основе связей на канвасе
    await update_agents_from_canvas(canvas_data, storage)
    
    return {"message": "Canvas updated successfully"}


async def update_flow_entry_point(flow: FlowConfig, canvas_data: Dict[str, Any], storage: Storage):
    """Обновляет entry_point_agent для Flow на основе связей на канвасе"""
    
    # Находим ноду Flow на канвасе
    flow_node = None
    for node in canvas_data.get("nodes", []):
        if node.get("type") == "flow_node" and node.get("params", {}).get("flow_id") == flow.flow_id:
            flow_node = node
            break
    
    if not flow_node:
        return
    
    # Находим связь от Flow к Agent
    for edge in canvas_data.get("edges", []):
        if edge.get("source") == flow_node.get("id"):
            # Находим целевую ноду
            target_node_id = edge.get("target")
            for node in canvas_data.get("nodes", []):
                if node.get("id") == target_node_id and node.get("type") == "agent_node":
                    # Обновляем entry_point_agent
                    agent_id = node.get("params", {}).get("agent_id")
                    if agent_id:
                        flow.entry_point_agent = agent_id
                        print(f"✅ Обновлен entry_point_agent для Flow {flow.flow_id}: {agent_id}")
                        return


async def update_agents_from_canvas(canvas_data: Dict[str, Any], storage: Storage):
    """Обновляет агентов в БД на основе связей на канвасе"""
    
    # Группируем связи по источникам (агентам)
    agent_connections = {}
    
    for edge in canvas_data.get("edges", []):
        source_id = edge.get("source")
        target_id = edge.get("target")
        
        if not source_id or not target_id:
            continue
        
        # Находим ноды источника и цели
        source_node = None
        target_node = None
        
        for node in canvas_data.get("nodes", []):
            if node.get("id") == source_id:
                source_node = node
            elif node.get("id") == target_id:
                target_node = node
        
        if not source_node or not target_node:
            continue
        
        # Если источник - агент, добавляем цель в его tools
        if source_node.get("type") == "agent_node":
            agent_id = source_node.get("params", {}).get("agent_id")
            if agent_id:
                if agent_id not in agent_connections:
                    agent_connections[agent_id] = []
                
                # Определяем тип цели
                if target_node.get("type") == "tool_node":
                    tool_id = target_node.get("params", {}).get("tool_id")
                    if tool_id:
                        agent_connections[agent_id].append({
                            "type": "tool",
                            "id": tool_id
                        })
                elif target_node.get("type") == "agent_node":
                    sub_agent_id = target_node.get("params", {}).get("agent_id")
                    if sub_agent_id:
                        agent_connections[agent_id].append({
                            "type": "agent",
                            "id": sub_agent_id
                        })
    
    # Обновляем каждого агента
    for agent_id, connections in agent_connections.items():
        try:
            agent = await storage.get_agent_config(agent_id)
            if agent:
                # Создаем новый список tools на основе связей
                new_tools = []
                
                for connection in connections:
                    if connection["type"] == "tool":
                        tool_ref = ToolReference(
                            tool_id=connection["id"],
                            params={}
                        )
                        new_tools.append(tool_ref)
                    elif connection["type"] == "agent":
                        # Агенты добавляются как tools с префиксом agent:
                        agent_tool_ref = ToolReference(
                            tool_id=f"agent:{connection['id']}",
                            params={}
                        )
                        new_tools.append(agent_tool_ref)
                
                # Обновляем tools агента
                agent.tools = new_tools
                await storage.set_agent_config(agent)
                
        except Exception as e:
            print(f"Ошибка обновления агента {agent_id}: {e}")
            continue
