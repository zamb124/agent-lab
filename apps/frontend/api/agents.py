"""
API для работы с агентами в Builder.
"""

from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any
import uuid

from apps.agents.models import AgentConfig, AgentType, CodeMode
from apps.frontend.dependencies import AgentRepositoryDep

router = APIRouter(prefix="/agents", tags=["builder-agents"])


@router.get("/", response_model=List[AgentConfig])
async def list_agents(
    agent_repo: AgentRepositoryDep,
    public_only: bool = False
) -> List[AgentConfig]:
    """Получить список всех агентов (оптимизировано)
    
    Args:
        public_only: Если True, возвращает только публичные агенты
    """
    all_agents = await agent_repo.list_all(limit=1000)
    
    if public_only:
        return [agent for agent in all_agents if getattr(agent, 'is_public', False)]
    
    return all_agents


@router.get("/{agent_id:path}", response_model=AgentConfig)
async def get_agent(agent_id: str, agent_repo: AgentRepositoryDep) -> AgentConfig:
    """Получить агента по ID"""
    agent = await agent_repo.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.post("/", response_model=AgentConfig)
async def create_agent(
    request_data: Dict[str, Any],
    agent_repo: AgentRepositoryDep
) -> AgentConfig:
    """Создать нового агента и сразу сохранить в БД"""

    print(f"DEBUG API: Raw request data: {request_data}")

    agent_type = request_data.get('agent_type', 'react')
    name = request_data.get('name', 'Новый Agent')
    description = request_data.get('description', '')
    prompt = request_data.get('prompt')

    print(f"DEBUG API: Extracted agent_type={agent_type} (type: {type(agent_type)})")

    # Преобразуем строку в enum если нужно
    if isinstance(agent_type, str):
        agent_type = AgentType(agent_type.lower())
        print(f"DEBUG API: Converted string to enum: {agent_type}")

    agent_id = f"agent_{uuid.uuid4().hex[:8]}"

    print(f"DEBUG API: Creating agent with type={agent_type}")

    from apps.agents.models import LLMConfig
    from core.config import get_settings

    settings = get_settings()

    # Создаем дефолтную LLM конфигурацию из настроек
    llm_config = LLMConfig(
        model=settings.llm.default_model,  # Дефолтная модель из конфига
        temperature=0.2
    )

    agent_config = AgentConfig(
        agent_id=agent_id,
        name=name,
        description=description or "",
        type=agent_type,
        prompt=prompt or "Вы полезный ассистент.",
        llm_config=llm_config,
        code_mode=CodeMode.INLINE_CODE,
        source="canvas_created"
    )

    print(f"DEBUG API: Created agent config with type={agent_config.type}")
    print(f"DEBUG API: Agent config dict: {agent_config.model_dump()}")
    
    # Сохраняем в БД через репозиторий
    await agent_repo.set(agent_config)
    
    return agent_config


@router.put("/{agent_id:path}", response_model=AgentConfig)
async def update_agent(
    agent_id: str,
    updates: Dict[str, Any],
    agent_repo: AgentRepositoryDep
) -> AgentConfig:
    """Обновить агента"""
    agent = await agent_repo.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    # Создаем обновленные данные с валидацией через модель
    # Исключаем frozen поля из model_dump
    agent_dict = agent.model_dump(exclude={'agent_id'})

    # Обновляем только разрешенные поля
    allowed_fields = {
        "name", "description", "type", "prompt", "code_mode",
        "function_class", "inline_code", "tools", "llm_config", "history_from",
        "local_variables", "store", "graph_definition"
    }
    
    # Сначала обрабатываем graph_definition отдельно
    if "graph_definition" in updates:
        graph_data = updates["graph_definition"]
        if graph_data:
            from apps.agents.models import GraphDefinition, GraphNode, GraphEdge
            
            nodes = []
            for node_data in graph_data.get("nodes", []):
                # Сохраняем ui данные отдельно, если они есть в params
                params = node_data.get("params", {}).copy()
                ui_data = params.pop("ui", None)
                
                node = GraphNode(**{**node_data, "params": params})
                
                # Сохраняем ui обратно в params (для отображения на канвасе)
                if ui_data:
                    node.params["ui"] = ui_data
                nodes.append(node)
            
            edges = [GraphEdge(**edge_data) for edge_data in graph_data.get("edges", [])]
            
            # Определяем entry_point: берем первую ноду без входящих рёбер
            entry_point = graph_data.get("entry_point", "")
            if not entry_point and nodes:
                # Находим первую ноду без входящих рёбер (или просто первую если все имеют входящие)
                target_nodes = {edge.target for edge in edges}
                entry_node = next((n for n in nodes if n.id not in target_nodes), nodes[0])
                entry_point = entry_node.id
            
            agent_dict["graph_definition"] = GraphDefinition(
                nodes=nodes,
                edges=edges,
                entry_point=entry_point
            )
        else:
            agent_dict["graph_definition"] = None
    
    # Обновляем остальные поля
    for field, value in updates.items():
        if field in allowed_fields and field != "graph_definition":
            agent_dict[field] = value

    # Валидируем через модель - валидаторы автоматически преобразуют типы
    # Устанавливаем agent_id явно, так как он frozen
    agent_dict['agent_id'] = agent_id
    validated_agent = AgentConfig(**agent_dict)
    
    await agent_repo.set(validated_agent)
    return validated_agent


@router.delete("/{agent_id:path}")
async def delete_agent(agent_id: str, agent_repo: AgentRepositoryDep):
    """Удалить агента"""
    agent = await agent_repo.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    await agent_repo.delete(agent_id)
    return {"message": "Agent deleted successfully"}


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
    
    from apps.agents.models import GraphDefinition, GraphNode, GraphEdge
    
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
