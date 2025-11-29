"""
API для работы с агентами в Builder.

Кастомные endpoints для специфичной логики работы с графами агентов.
Стандартные CRUD операции доступны через автоматические роутеры: /agents/api/v1/agent/...
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Dict, Any, List

from apps.frontend.dependencies import AgentRepositoryDep
from apps.agents.models import GraphDefinition, GraphNode, GraphEdge, AgentConfig

router = APIRouter(prefix="/agents", tags=["builder-agents"])


@router.get("/", response_model=List[AgentConfig])
async def list_agents(
    agent_repo: AgentRepositoryDep,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0)
) -> List[AgentConfig]:
    """Список всех агентов"""
    return await agent_repo.list_all(limit=limit, offset=offset)


@router.post("/", response_model=AgentConfig)
async def create_agent(
    agent: AgentConfig,
    agent_repo: AgentRepositoryDep
) -> AgentConfig:
    """Создать агента"""
    await agent_repo.set(agent)
    return agent


@router.get("/{agent_id:path}/graph")
async def get_agent_graph(agent_id: str, agent_repo: AgentRepositoryDep) -> Dict[str, Any]:
    """Получить граф агента"""
    agent = await agent_repo.get(agent_id)
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


@router.put("/{agent_id:path}/graph")
async def update_agent_graph(
    agent_id: str,
    graph_data: Dict[str, Any],
    agent_repo: AgentRepositoryDep
):
    """Обновить граф агента"""
    agent = await agent_repo.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
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
    
    await agent_repo.set(agent)
    return {"message": "Agent graph updated successfully"}


@router.get("/{agent_id:path}", response_model=AgentConfig)
async def get_agent(
    agent_id: str,
    agent_repo: AgentRepositoryDep
) -> AgentConfig:
    """Получить агента"""
    agent = await agent_repo.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.put("/{agent_id:path}", response_model=AgentConfig)
async def update_agent(
    agent_id: str,
    agent: AgentConfig,
    agent_repo: AgentRepositoryDep
) -> AgentConfig:
    """Обновить агента"""
    if agent.agent_id != agent_id:
         raise HTTPException(status_code=400, detail="Agent ID mismatch")
    await agent_repo.set(agent)
    return agent


@router.delete("/{agent_id:path}")
async def delete_agent(
    agent_id: str,
    agent_repo: AgentRepositoryDep
):
    """Удалить агента"""
    await agent_repo.delete(agent_id)
    return {"status": "deleted", "agent_id": agent_id}
