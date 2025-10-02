"""
API для работы с агентами в Builder.
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import List, Optional, Dict, Any
import uuid

from app.models import AgentConfig, AgentType, CodeMode
from app.core.storage import Storage
from app.core.container import get_container

router = APIRouter(prefix="/agents", tags=["builder-agents"])


async def get_storage() -> Storage:
    """Получить Storage из контейнера"""
    container = get_container()
    return container.get_storage()


@router.get("/", response_model=List[AgentConfig])
async def list_agents(storage: Storage = Depends(get_storage)) -> List[AgentConfig]:
    """Получить список всех агентов"""
    # Получаем все ключи с префиксом "agent:"
    agent_keys = await storage.list_by_prefix("agent:")
    
    agents = []
    for key in agent_keys:
        # Извлекаем agent_id из ключа (убираем префикс компании и "agent:")
        agent_id = key.split(":")[-1]  # Берем последнюю часть после ":"
        agent = await storage.get_agent_config(agent_id)
        if agent:
            agents.append(agent)
    
    return agents


@router.get("/{agent_id}", response_model=AgentConfig)
async def get_agent(agent_id: str, storage: Storage = Depends(get_storage)) -> AgentConfig:
    """Получить агента по ID"""
    agent = await storage.get_agent_config(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.post("/", response_model=AgentConfig)
async def create_agent(
    name: str = "Новый Agent",
    description: Optional[str] = None,
    agent_type: AgentType = AgentType.REACT,
    prompt: Optional[str] = None,
    storage: Storage = Depends(get_storage)
) -> AgentConfig:
    """Создать нового агента и сразу сохранить в БД"""
    agent_id = f"agent_{uuid.uuid4().hex[:8]}"
    
    agent_config = AgentConfig(
        agent_id=agent_id,
        name=name,
        description=description or "",
        type=agent_type,
        prompt=prompt or "Вы полезный ассистент.",
        code_mode=CodeMode.INLINE_CODE,
        source="canvas_created"
    )
    
    # Сразу сохраняем в БД
    await storage.set_agent_config(agent_config)
    
    return agent_config


@router.put("/{agent_id}", response_model=AgentConfig)
async def update_agent(
    agent_id: str,
    updates: Dict[str, Any],
    storage: Storage = Depends(get_storage)
) -> AgentConfig:
    """Обновить агента"""
    agent = await storage.get_agent_config(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    # Обновляем только разрешенные поля
    allowed_fields = {
        "name", "description", "type", "prompt", "code_mode", 
        "function_class", "inline_code", "tools", "llm_config", "history_from"
    }
    for field, value in updates.items():
        if field in allowed_fields:
            setattr(agent, field, value)
    
    await storage.set_agent_config(agent)
    return agent


@router.delete("/{agent_id}")
async def delete_agent(agent_id: str, storage: Storage = Depends(get_storage)):
    """Удалить агента"""
    agent = await storage.get_agent_config(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    await storage.delete_agent_config(agent_id)
    return {"message": "Agent deleted successfully"}


@router.get("/{agent_id}/graph")
async def get_agent_graph(agent_id: str, storage: Storage = Depends(get_storage)) -> Dict[str, Any]:
    """Получить граф агента"""
    agent = await storage.get_agent_config(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    if not agent.graph_definition:
        return {
            "agent_id": agent_id,
            "nodes": [],
            "edges": [],
            "entry_point": None
        }
    
    return {
        "agent_id": agent_id,
        "nodes": [
            {
                **node.dict(),
                "ui": node.params.get("ui", {"x": 0, "y": 0, "width": 200, "height": 100})
            }
            for node in agent.graph_definition.nodes
        ],
        "edges": [edge.dict() for edge in agent.graph_definition.edges],
        "entry_point": agent.graph_definition.entry_point
    }


@router.put("/{agent_id}/graph")
async def update_agent_graph(
    agent_id: str,
    graph_data: Dict[str, Any],
    storage: Storage = Depends(get_storage)
):
    """Обновить граф агента"""
    agent = await storage.get_agent_config(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    from app.models import GraphDefinition, GraphNode, GraphEdge
    
    # Обновляем UI данные в params нод
    nodes = []
    for node_data in graph_data.get("nodes", []):
        ui_data = node_data.pop("ui", {})
        node = GraphNode(**node_data)
        node.params["ui"] = ui_data
        nodes.append(node)
    
    edges = [GraphEdge(**edge_data) for edge_data in graph_data.get("edges", [])]
    
    agent.graph_definition = GraphDefinition(
        nodes=nodes,
        edges=edges,
        entry_point=graph_data.get("entry_point", "")
    )
    
    await storage.set_agent_config(agent)
    return {"message": "Agent graph updated successfully"}
