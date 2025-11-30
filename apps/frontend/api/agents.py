"""
API для работы с агентами в Builder.

CRUD endpoints для frontend UI.
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Dict, Any, List
import uuid

from apps.frontend.dependencies import AgentRepositoryDep
from apps.agents.models import AgentConfig, AgentType, CodeMode, GraphDefinition, GraphNode, GraphEdge, LLMConfig

router = APIRouter(prefix="/agents", tags=["builder-agents"])


@router.get("/", response_model=List[AgentConfig])
async def list_agents(
    agent_repo: AgentRepositoryDep,
    limit: int = Query(100, ge=1, le=1000)
) -> List[AgentConfig]:
    """Получить список агентов"""
    return await agent_repo.list_all(limit=limit)


@router.post("/", response_model=AgentConfig)
async def create_agent(
    agent_data: Dict[str, Any],
    agent_repo: AgentRepositoryDep
) -> AgentConfig:
    """Создать нового агента"""
    agent_id = agent_data.get("agent_id")
    if not agent_id:
        agent_id = f"agent_{uuid.uuid4().hex[:8]}"
    
    agent_config = AgentConfig(
        agent_id=agent_id,
        name=agent_data.get("name", "Новый агент"),
        description=agent_data.get("description", ""),
        type=AgentType(agent_data.get("type", "react")),
        prompt=agent_data.get("prompt", ""),
        code_mode=CodeMode(agent_data.get("code_mode", "inline_code")),
        llm_config=LLMConfig(**agent_data.get("llm_config", {})) if agent_data.get("llm_config") else LLMConfig(),
        source="ui_created"
    )
    
    await agent_repo.set(agent_config)
    return agent_config


@router.get("/{agent_id:path}/graph")
async def get_agent_graph(agent_id: str, agent_repo: AgentRepositoryDep) -> Dict[str, Any]:
    """Получить граф агента для визуального редактора"""
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
                **node.model_dump(),
                "ui": node.params.get("ui", {"x": 0, "y": 0, "width": 200, "height": 100})
            }
            for node in agent.graph_definition.nodes
        ],
        "edges": [edge.model_dump() for edge in agent.graph_definition.edges],
        "entry_point": agent.graph_definition.entry_point
    }


@router.put("/{agent_id:path}/graph")
async def update_agent_graph(
    agent_id: str,
    graph_data: Dict[str, Any],
    agent_repo: AgentRepositoryDep
) -> Dict[str, str]:
    """Обновить граф агента из визуального редактора"""
    agent = await agent_repo.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
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
