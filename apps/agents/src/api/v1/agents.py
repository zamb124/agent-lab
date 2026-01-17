"""
API endpoints для flows.
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from apps.agents.src.container import AgentContainer, get_container
from core.logging import get_logger
from apps.agents.src.models import Edge, AgentConfig, SkillConfig, NodeConfig, AgentType, ExternalAgentStatus, TriggerConfig
from apps.agents.src.services.agent_validator import AgentValidator

logger = get_logger(__name__)


def _generate_agent_url(agent_id: str, agent_type: Optional[AgentType] = None, external_url: Optional[str] = None) -> str:
    """Генерирует URL для агента"""
    if agent_type == AgentType.EXTERNAL and external_url:
        return external_url
    
    from core.config import get_settings
    settings = get_settings()
    return f"https://{settings.server.host}:{settings.server.port}/agents/{agent_id}"


async def _inline_tools_in_nodes(
    nodes: Dict[str, Dict[str, Any]], 
    container: AgentContainer
) -> Dict[str, Dict[str, Any]]:
    """
    Инлайнит tools в nodes агента.
    
    Для каждой ноды:
    - Инлайнит tools (поле tools в react_node)
    - Инлайнит code для нод типа tool с tool_id
    """
    for node_id, node_config in nodes.items():
        # Инлайним tools для react_node
        tools = node_config.get("tools", [])
        if tools:
            node_config["tools"] = await _inline_tools_list(tools, container)
        
        # Инлайним code для tool нод с tool_id
        if node_config.get("type") == "tool" and node_config.get("tool_id") and not node_config.get("code"):
            tool_id = node_config["tool_id"]
            tool_ref = await container.tool_repository.get(tool_id)
            if tool_ref and tool_ref.code:
                node_config["code"] = tool_ref.code
                if tool_ref.args_schema:
                    node_config["args_schema"] = {
                        k: {"type": v.type, "description": v.description}
                        for k, v in tool_ref.args_schema.items()
                    }
                if tool_ref.description and not node_config.get("description"):
                    node_config["description"] = tool_ref.description
    return nodes


async def _inline_tools_list(
    tools: List[Any], 
    container: AgentContainer
) -> List[Dict[str, Any]]:
    """Инлайнит список tools."""
    inlined = []
    for tool in tools:
        inlined_tool = await _inline_single_tool(tool, container)
        if inlined_tool:
            inlined.append(inlined_tool)
    return inlined


async def _inline_single_tool(
    tool: Any, 
    container: AgentContainer
) -> Dict[str, Any] | None:
    """Инлайнит один tool."""
    if isinstance(tool, str):
        # tool_id - достаём из библиотеки
        tool_ref = await container.tool_repository.get(tool)
        if tool_ref:
            return tool_ref.model_dump()
        
        # Может быть node (react_node as tool)
        node = await container.node_repository.get(tool)
        if node:
            return await _node_to_inline_tool(node, container)
        
        # Может быть agent
        agent = await container.agent_repository.get(tool)
        if agent:
            return _agent_to_inline_tool(agent)
        
        raise HTTPException(status_code=400, detail=f"Tool '{tool}' not found in library")
    
    elif isinstance(tool, dict):
        tool_id = tool.get("tool_id")
        
        # Если это react_node - рекурсивно инлайним его tools
        if tool.get("type") == "react_node" or tool.get("prompt"):
            if "tools" in tool:
                tool["tools"] = await _inline_tools_list(tool["tools"], container)
            return tool
        
        # Если нет code - дополняем из библиотеки
        if tool_id and not tool.get("code"):
            tool_ref = await container.tool_repository.get(tool_id)
            if tool_ref and tool_ref.code:
                merged = tool_ref.model_dump()
                merged.update(tool)  # Переопределения из запроса приоритетнее
                return merged
        
        return tool
    
    return None


async def _node_to_inline_tool(node: NodeConfig, container: AgentContainer) -> Dict[str, Any]:
    """Конвертирует NodeConfig в inline tool."""
    result = {
        "tool_id": node.node_id,
        "type": node.type.value if hasattr(node.type, "value") else node.type,
        "name": node.name,
        "description": node.description,
        "prompt": node.prompt,
    }
    if node.llm_override:
        result["llm"] = node.llm_override.model_dump()
    if node.code:
        result["code"] = node.code
    if node.tools:
        tools_list = [t.model_dump() if hasattr(t, "model_dump") else t for t in node.tools]
        result["tools"] = await _inline_tools_list(tools_list, container)
    return result


def _agent_to_inline_tool(agent: AgentConfig) -> Dict[str, Any]:
    """Конвертирует AgentConfig в inline tool."""
    return {
        "tool_id": agent.agent_id,
        "type": "agent",
        "name": agent.name,
        "description": agent.description,
        "entry": agent.entry,
        "nodes": agent.nodes,
        "edges": [e.model_dump() for e in agent.edges] if agent.edges else [],
    }

router = APIRouter(tags=["agents"])


class EdgeRequest(BaseModel):
    """Edge в запросе"""

    model_config = {"populate_by_name": True}

    from_node: str
    to_node: Optional[str]
    condition: Optional[str] = None


class SkillRequest(BaseModel):
    """Skill в запросе"""

    name: str
    description: str = ""
    tags: List[str] = []
    entry: Optional[str] = None
    nodes: Optional[Dict[str, Any]] = None
    edges: Optional[List[Dict[str, Any]]] = None
    variables: Dict[str, Any] = {}


class SkillResponse(BaseModel):
    """Skill в ответе"""

    name: str
    description: str = ""
    tags: List[str] = []
    entry: Optional[str] = None
    nodes: Optional[Dict[str, Any]] = None
    edges: Optional[List[Dict[str, Any]]] = None
    variables: Dict[str, Any] = {}
    nodes_mode: Optional[str] = None
    edges_mode: Optional[str] = None
    variables_mode: Optional[str] = None


def _skill_config_to_response(skill: SkillConfig) -> SkillResponse:
    """Конвертирует SkillConfig в SkillResponse."""
    edges = None
    if skill.edges:
        edges = []
        for e in skill.edges:
            if e is None:
                continue
            edges.append({
                "from": e.from_node,
                "to": e.to_node,
                "condition": e.condition
            })
        if not edges:
            edges = None
    
    # Конвертируем mode в строку (может быть Enum или уже строка)
    nodes_mode = None
    if skill.nodes_mode:
        nodes_mode = skill.nodes_mode.value if hasattr(skill.nodes_mode, 'value') else str(skill.nodes_mode)
    
    edges_mode = None
    if skill.edges_mode:
        edges_mode = skill.edges_mode.value if hasattr(skill.edges_mode, 'value') else str(skill.edges_mode)
    
    variables_mode = None
    if skill.variables_mode:
        variables_mode = skill.variables_mode.value if hasattr(skill.variables_mode, 'value') else str(skill.variables_mode)
    
    return SkillResponse(
        name=skill.name,
        description=skill.description,
        tags=skill.tags,
        entry=skill.entry,
        nodes=skill.nodes,
        edges=edges,
        variables=skill.variables,
        nodes_mode=nodes_mode,
        edges_mode=edges_mode,
        variables_mode=variables_mode,
    )


def _skill_request_to_config(skill_id: str, skill: SkillRequest) -> SkillConfig:
    """Конвертирует SkillRequest в SkillConfig."""
    edges = None
    if skill.edges:
        edges = [
            Edge(
                from_node=e.get("from") or e.get("from_node"),
                to_node=e.get("to") or e.get("to_node"),
                condition=e.get("condition"),
            )
            for e in skill.edges
        ]
    return SkillConfig(
        name=skill.name,
        description=skill.description,
        tags=skill.tags,
        entry=skill.entry,
        nodes=skill.nodes,
        edges=edges,
        variables=skill.variables,
    )


async def get_container_dep() -> AgentContainer:
    """Dependency для получения контейнера"""
    return get_container()


class AgentCreateRequest(BaseModel):
    """Запрос на создание агента"""

    agent_id: str
    name: str
    description: Optional[str] = None
    entry: str
    nodes: Dict[str, Any]
    edges: List[Dict[str, Any]]
    variables: Dict[str, Any] = {}
    tags: List[str] = []
    skills: Dict[str, SkillRequest] = {}
    evaluation: Optional[Dict[str, Any]] = None
    triggers: Dict[str, Any] = {}
    resources: Dict[str, Any] = {}


class AgentResponse(BaseModel):
    """Ответ с данными агента"""

    agent_id: str
    version: str = ""
    name: str
    description: Optional[str]
    type: Optional[AgentType] = AgentType.LOCAL
    
    # LOCAL agent fields
    entry: Optional[str] = None
    nodes: Optional[Dict[str, Any]] = None
    edges: Optional[List[Dict[str, Any]]] = None
    variables: Dict[str, Any] = {}
    tags: List[str] = []
    skills: Dict[str, SkillResponse] = {}
    evaluation: Optional[Dict[str, Any]] = None
    hidden: bool = False
    
    # EXTERNAL agent fields
    url: Optional[str] = None
    auth_headers: Optional[Dict[str, str]] = None
    status: Optional[str] = None
    last_health_check: Optional[str] = None
    agent_card: Optional[Dict[str, Any]] = None
    
    # A2A capabilities
    capabilities: Dict[str, Any] = {
        "streaming": True,
        "pushNotifications": True,
    }
    
    # Триггеры агента
    triggers: Dict[str, Any] = {}
    
    # Ресурсы агента
    resources: Dict[str, Any] = {}


class AgentValidateRequest(BaseModel):
    """Запрос на валидацию агента"""

    nodes: Dict[str, Any]
    edges: List[Dict[str, Any]]
    entry: str
    variables: Dict[str, Any] = {}
    agent_id: Optional[str] = None


class ValidationErrorResponse(BaseModel):
    """Ошибка валидации"""

    code: str
    message: str
    severity: str
    node_id: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


class AgentValidateResponse(BaseModel):
    """Ответ на валидацию агента"""

    valid: bool
    errors: List[ValidationErrorResponse] = []
    state_keys_used: List[str] = []
    var_keys_used: List[str] = []


@router.post("/validate", response_model=AgentValidateResponse)
async def validate_flow(
    request: AgentValidateRequest,
    container: AgentContainer = Depends(get_container_dep),
) -> AgentValidateResponse:
    """
    Валидирует конфигурацию агента без сохранения.
    
    Проверяет:
    - Структуру графа (entry, edges, достижимость нод)
    - Ссылки на агенты, tools, subflows
    - Переменные @var:
    - Парсит inline code на обращения к state
    - Пробует собрать Agent
    """
    validator = AgentValidator(
        agent_repository=container.agent_repository,
        tool_repository=container.tool_repository,
        node_repository=container.node_repository,
    )
    
    result = await validator.validate(
        nodes=request.nodes,
        edges=request.edges,
        entry=request.entry,
        variables=request.variables,
        agent_id=request.agent_id,
    )
    
    return AgentValidateResponse(
        valid=result.valid,
        errors=[
            ValidationErrorResponse(
                code=e.code,
                message=e.message,
                severity=e.severity.value,
                node_id=e.node_id,
                details=e.details,
            )
            for e in result.errors
        ],
        state_keys_used=list(result.state_keys_used),
        var_keys_used=list(result.var_keys_used),
    )


@router.get("/", response_model=List[AgentResponse])
async def list_flows(
    type: Optional[AgentType] = None,
    limit: int = Query(1000, ge=1, le=10000, description="Максимум агентов"),
    container: AgentContainer = Depends(get_container_dep),
) -> List[AgentResponse]:
    """Список всех flows с опциональным фильтром по типу (local/external)"""
    flows = await container.agent_repository.list_all(limit=limit)
    
    # Фильтруем по типу если указан
    if type is not None:
        flows = [f for f in flows if f.type == type]
    
    result = []
    for f in flows:
        skills_response = {
            skill_id: _skill_config_to_response(skill)
            for skill_id, skill in (f.skills or {}).items()
        }
        evaluation_dict = None
        if f.evaluation:
            evaluation_dict = {k: v.model_dump() if hasattr(v, 'model_dump') else v for k, v in f.evaluation.items()}
        hidden = getattr(f, 'hidden', False)
        
        response_data = {
            "agent_id": f.agent_id,
            "version": f.version,
            "name": f.name,
            "description": f.description,
            "type": f.type,
            "tags": f.tags,
            "hidden": hidden,
        }
        
        # LOCAL agent fields
        if f.type == AgentType.LOCAL:
            response_data.update({
                "entry": f.entry,
                "nodes": f.nodes,
                "edges": [
                    {"from": e.from_node, "to": e.to_node, "condition": e.condition}
                    for e in f.edges
                ],
                "variables": f.variables,
                "skills": skills_response,
                "evaluation": evaluation_dict,
            })
        # EXTERNAL agent fields
        elif f.type == AgentType.EXTERNAL:
            status_value = f.status.value if isinstance(f.status, ExternalAgentStatus) else f.status
            response_data.update({
                "url": f.url,
                "auth_headers": f.auth_headers,
                "status": status_value,
                "last_health_check": f.last_health_check.isoformat() if f.last_health_check else None,
                "agent_card": f.agent_card,
            })
        
        result.append(AgentResponse(**response_data))
    return result


async def _validate_tool_nodes(
    nodes: Dict[str, Dict[str, Any]], 
    container: AgentContainer
) -> None:
    """Валидирует tool_id в tool нодах."""
    for node_id, node_config in nodes.items():
        if node_config.get("type") == "tool":
            tool_id = node_config.get("tool_id")
            has_code = "code" in node_config and node_config.get("code")
            
            if tool_id and not has_code:
                tool = await container.tool_repository.get(tool_id)
                if tool is None:
                    node = await container.node_repository.get(tool_id)
                    if node is None:
                        agent = await container.agent_repository.get(tool_id)
                        if agent is None:
                            raise HTTPException(
                                status_code=400, 
                                detail=f"Tool '{tool_id}' not found in library"
                            )


@router.post("/", response_model=AgentResponse)
async def create_flow(
    request: AgentCreateRequest, container: AgentContainer = Depends(get_container_dep)
) -> AgentResponse:
    """Создает нового агента"""
    # Валидируем tool_id в tool нодах
    await _validate_tool_nodes(dict(request.nodes), container)
    
    # Инлайним tools - заменяем tool_id на полные конфиги с кодом ПЕРЕД валидацией
    nodes = await _inline_tools_in_nodes(dict(request.nodes), container)
    
    # Валидируем ссылки (node_id, tool_id, agent_id) после инлайна
    validator = AgentValidator(
        agent_repository=container.agent_repository,
        tool_repository=container.tool_repository,
        node_repository=container.node_repository,
    )
    validation_result = await validator.validate(
        nodes=nodes,
        edges=request.edges,
        entry=request.entry,
        variables=request.variables or {},
    )
    
    if not validation_result.valid:
        errors = [e.message for e in validation_result.errors]
        raise HTTPException(
            status_code=400,
            detail="; ".join(errors)
        )

    edges = [
        Edge(
            from_node=e.get("from") or e.get("from_node"),
            to_node=e.get("to") or e.get("to_node"),
            condition=e.get("condition"),
        )
        for e in request.edges
    ]

    skills = {
        skill_id: _skill_request_to_config(skill_id, skill)
        for skill_id, skill in request.skills.items()
    }

    agent_config = AgentConfig(
        agent_id=request.agent_id,
        name=request.name,
        description=request.description,
        entry=request.entry,
        nodes=nodes,  # Инлайненные nodes
        edges=edges,
        variables=request.variables,
        tags=request.tags,
        skills=skills,
        evaluation=request.evaluation,
        source="api",
    )

    await container.agent_repository.set(agent_config)

    skills_response = {
        skill_id: _skill_config_to_response(skill)
        for skill_id, skill in agent_config.skills.items()
    }


    return AgentResponse(
        agent_id=agent_config.agent_id,
        version=agent_config.version or "",
        name=agent_config.name,
        description=agent_config.description,
        type=agent_config.type or AgentType.LOCAL,
        entry=agent_config.entry,
        nodes=agent_config.nodes,
        edges=[
            {"from": e.from_node, "to": e.to_node, "condition": e.condition}
            for e in agent_config.edges
        ],
        variables=agent_config.variables,
        tags=agent_config.tags,
        skills=skills_response,
        evaluation=request.evaluation,
        hidden=getattr(agent_config, 'hidden', False),
        url=_generate_agent_url(agent_config.agent_id, agent_config.type, getattr(agent_config, 'url', None)),
    )


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_flow(
    agent_id: str, container: AgentContainer = Depends(get_container_dep)
) -> AgentResponse:
    """Получает agent по ID"""
    try:
        agent = await container.agent_repository.get(agent_id)
        if agent is None:
            raise HTTPException(status_code=404, detail="Agent not found")
        
        evaluation_dict = None
        if agent.evaluation:
            if hasattr(agent.evaluation, "model_dump"):
                evaluation_dict = agent.evaluation.model_dump()
            else:
                evaluation_dict = agent.evaluation
        
        skills_response = {}
        if agent.skills:
            for skill_id, skill in agent.skills.items():
                try:
                    skills_response[skill_id] = _skill_config_to_response(skill)
                except Exception as e:
                    logger.error(f"Ошибка конвертации skill '{skill_id}': {e}", exc_info=True)
                    raise HTTPException(
                        status_code=500,
                        detail=f"Ошибка обработки skill '{skill_id}': {str(e)}"
                    )
        
        edges_list = []
        if agent.edges:
            for e in agent.edges:
                if e is None:
                    continue
                edges_list.append({
                    "from": e.from_node,
                    "to": e.to_node,
                    "condition": e.condition
                })
        
        triggers_response = {}
        if agent.triggers:
            for trigger_id, trigger in agent.triggers.items():
                triggers_response[trigger_id] = trigger.model_dump() if hasattr(trigger, 'model_dump') else trigger
        
        return AgentResponse(
            agent_id=agent.agent_id,
            version=agent.version or "",
            name=agent.name,
            description=agent.description,
            type=agent.type or AgentType.LOCAL,
            entry=agent.entry,
            nodes=agent.nodes or {},
            edges=edges_list,
            variables=agent.variables or {},
            tags=agent.tags or [],
            skills=skills_response,
            evaluation=evaluation_dict,
            hidden=getattr(agent, 'hidden', False),
            url=_generate_agent_url(agent.agent_id, agent.type, getattr(agent, 'url', None)),
            triggers=triggers_response,
            resources=agent.resources or {},
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка получения agent '{agent_id}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка получения agent: {str(e)}")


@router.put("/{agent_id}", response_model=AgentResponse)
async def update_flow(
    agent_id: str,
    request: AgentCreateRequest,
    container: AgentContainer = Depends(get_container_dep),
) -> AgentResponse:
    """Обновляет существующего агента (создаёт новую версию)"""
    existing = await container.agent_repository.get(agent_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Инлайним tools - заменяем tool_id на полные конфиги с кодом
    nodes = await _inline_tools_in_nodes(dict(request.nodes), container)

    edges = [
        Edge(
            from_node=e.get("from") or e.get("from_node"),
            to_node=e.get("to") or e.get("to_node"),
            condition=e.get("condition"),
        )
        for e in request.edges
    ]

    skills = {
        skill_id: _skill_request_to_config(skill_id, skill)
        for skill_id, skill in request.skills.items()
    }

    triggers = {
        trigger_id: TriggerConfig(**trigger_data) if isinstance(trigger_data, dict) else trigger_data
        for trigger_id, trigger_data in request.triggers.items()
    }

    resources = request.resources or {}

    agent_config = AgentConfig(
        agent_id=agent_id,
        name=request.name,
        description=request.description,
        entry=request.entry,
        nodes=nodes,  # Инлайненные nodes
        edges=edges,
        variables=request.variables,
        tags=request.tags,
        skills=skills,
        evaluation=request.evaluation,
        source=existing.source,
        triggers=triggers,
        resources=resources,
    )

    await container.agent_repository.set(agent_config)

    skills_response = {
        skill_id: _skill_config_to_response(skill)
        for skill_id, skill in agent_config.skills.items()
    }

    triggers_response = {
        trigger_id: trigger.model_dump() if hasattr(trigger, 'model_dump') else trigger
        for trigger_id, trigger in agent_config.triggers.items()
    }

    return AgentResponse(
        agent_id=agent_config.agent_id,
        version=agent_config.version or "",
        name=agent_config.name,
        description=agent_config.description,
        type=agent_config.type or AgentType.LOCAL,
        entry=agent_config.entry,
        nodes=agent_config.nodes,
        edges=[
            {"from": e.from_node, "to": e.to_node, "condition": e.condition}
            for e in agent_config.edges
        ],
        variables=agent_config.variables,
        tags=agent_config.tags,
        skills=skills_response,
        evaluation=request.evaluation,
        hidden=getattr(agent_config, 'hidden', False),
        url=_generate_agent_url(agent_config.agent_id, agent_config.type, getattr(agent_config, 'url', None)),
        triggers=triggers_response,
        resources=agent_config.resources or {},
    )


@router.delete("/{agent_id}")
async def delete_flow(
    agent_id: str, container: AgentContainer = Depends(get_container_dep)
) -> dict:
    """Удаляет агента"""
    deleted = await container.agent_repository.delete(agent_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Agent not found")
    return {"status": "deleted", "agent_id": agent_id}


@router.get("/{agent_id}/versions", response_model=List[str])
async def list_versions(
    agent_id: str, container: AgentContainer = Depends(get_container_dep)
) -> List[str]:
    """Список всех версий агента"""
    versions = await container.agent_repository.list_versions(agent_id)
    return versions


@router.get("/{agent_id}/versions/{version}", response_model=AgentResponse)
async def get_version(
    agent_id: str,
    version: str,
    container: AgentContainer = Depends(get_container_dep),
) -> AgentResponse:
    """Получает конкретную версию агента"""
    agent = await container.agent_repository.get_version(agent_id, version)
    if agent is None:
        raise HTTPException(status_code=404, detail="Version not found")
    
    skills_response = {
        skill_id: _skill_config_to_response(skill)
        for skill_id, skill in (agent.skills or {}).items()
    }
    
    edges_list = [
        {"from": e.from_node, "to": e.to_node, "condition": e.condition}
        for e in (agent.edges or []) if e
    ]
    
    return AgentResponse(
        agent_id=agent.agent_id,
        version=agent.version or "",
        name=agent.name,
        description=agent.description,
        type=agent.type or AgentType.LOCAL,
        entry=agent.entry,
        nodes=agent.nodes or {},
        edges=edges_list,
        variables=agent.variables or {},
        tags=agent.tags or [],
        skills=skills_response,
        hidden=getattr(agent, 'hidden', False),
        url=_generate_agent_url(agent.agent_id, agent.type, getattr(agent, 'url', None)),
    )


@router.post("/{agent_id}/versions/{version}/rollback")
async def rollback_version(
    agent_id: str,
    version: str,
    container: AgentContainer = Depends(get_container_dep),
) -> Dict[str, Any]:
    """
    Откатывает агента к указанной версии.
    
    Делает указанную версию latest (не удаляет новые версии).
    """
    success = await container.agent_repository.rollback_to_version(agent_id, version)
    if not success:
        raise HTTPException(status_code=404, detail="Version not found")
    
    return {
        "status": "success",
        "message": f"Agent '{agent_id}' rolled back to version {version}",
        "agent_id": agent_id,
        "version": version,
    }
