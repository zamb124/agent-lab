"""
API endpoints для flows.
"""

import asyncio
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
import yaml

from apps.flows.src.container import FlowContainer
from apps.flows.src.dependencies import ContainerDep
from apps.flows.src.services.flows_loader import FlowsLoader
from core.logging import get_logger
from core.pagination import OffsetPage
from apps.flows.src.models import Edge, FlowConfig, SkillConfig, NodeConfig, FlowType, ExternalAgentStatus, TriggerConfig
from apps.flows.src.services.flow_validator import FlowValidator

logger = get_logger(__name__)


def _flow_semantic_payload(flow_cfg: FlowConfig) -> Dict[str, Any]:
    """Детерминированный payload для сравнения текущего flow и bundle."""
    payload = flow_cfg.model_dump(
        mode="json",
        exclude={
            "version",
            "created_at",
            "updated_at",
            "source",
            "public_fields",
        },
    )
    return payload


def _build_bundle_index(flows_root: Path) -> Dict[str, str]:
    """flow_id -> bundle_id для записей из registry.yaml."""
    registry_path = flows_root / "registry.yaml"
    bundles_dir = flows_root / "bundles"

    if not registry_path.exists():
        raise HTTPException(status_code=500, detail=f"Registry not found: {registry_path}")

    with open(registry_path, "r", encoding="utf-8") as f:
        registry_data = yaml.safe_load(f) or {}

    registry_flows = registry_data.get("flows")
    if not isinstance(registry_flows, list):
        raise HTTPException(status_code=500, detail="Registry field 'flows' must be a list")

    flow_to_bundle: Dict[str, str] = {}
    for entry in registry_flows:
        if isinstance(entry, str):
            bundle_id = entry
        elif isinstance(entry, dict):
            bundle_id = entry.get("id")
        else:
            raise HTTPException(status_code=500, detail="Registry flow entry must be string or object")
        if not isinstance(bundle_id, str) or not bundle_id:
            raise HTTPException(status_code=500, detail="Registry flow entry must include non-empty string 'id'")

        flow_path = bundles_dir / bundle_id / "flow.json"
        if not flow_path.exists():
            raise HTTPException(status_code=500, detail=f"Bundle flow.json not found for '{bundle_id}'")

        with open(flow_path, "r", encoding="utf-8") as f:
            raw_flow = json.load(f)

        flow_id = raw_flow.get("flow_id") or raw_flow.get("id")
        if not isinstance(flow_id, str) or not flow_id:
            raise HTTPException(status_code=500, detail=f"Bundle '{bundle_id}' must define non-empty flow_id")

        flow_to_bundle[flow_id] = bundle_id

    return flow_to_bundle


async def _get_bundle_update_flags(
    flows: List[FlowConfig],
    container: ContainerDep,
    flows_root: Path,
) -> Dict[str, bool]:
    """Возвращает признак наличия обновлений bundle для flow с source=file."""
    flow_to_bundle = _build_bundle_index(flows_root)
    file_flow_ids = [f.flow_id for f in flows if (getattr(f, "source", None) or "manual") == "file"]
    if not file_flow_ids:
        return {}

    bundles_dir = flows_root / "bundles"
    loader = FlowsLoader(
        bundles_dir=bundles_dir,
        flow_repository=container.flow_repository,
        node_repository=container.node_repository,
        tool_repository=container.tool_repository,
        registry_path=flows_root / "registry.yaml",
    )
    await loader._load_tools_cache()
    await loader._load_nodes_cache()

    flags: Dict[str, bool] = {}
    for flow_cfg in flows:
        source_value = getattr(flow_cfg, "source", None) or "manual"
        if source_value != "file":
            continue

        bundle_id = flow_to_bundle.get(flow_cfg.flow_id)
        if not bundle_id:
            raise HTTPException(status_code=500, detail=f"Bundle mapping not found for flow '{flow_cfg.flow_id}'")

        await loader._preload_nodes_to_cache(bundle_id)
        bundle_cfg = await loader.build_flow_bundle_config(bundle_id)
        if bundle_cfg is None:
            raise HTTPException(status_code=500, detail=f"Failed to build bundle config for '{bundle_id}'")

        flags[flow_cfg.flow_id] = _flow_semantic_payload(flow_cfg) != _flow_semantic_payload(bundle_cfg)

    return flags


def _generate_flow_url(flow_id: str, flow_kind: Optional[FlowType] = None, external_url: Optional[str] = None) -> str:
    """Публичный URL flow (или внешний base URL для EXTERNAL)."""
    if flow_kind == FlowType.EXTERNAL and external_url:
        return external_url
    
    from core.config import get_settings
    settings = get_settings()
    return f"https://{settings.server.host}:{settings.server.port}/flows/{flow_id}"


async def _inline_tools_in_nodes(
    nodes: Dict[str, Dict[str, Any]], 
    container: FlowContainer
) -> Dict[str, Dict[str, Any]]:
    """
    Инлайнит tools в nodes flow.
    
    Для каждой ноды:
    - Инлайнит tools (поле tools в llm_node)
    - Инлайнит code для нод типа tool с tool_id
    """
    for node_id, node_config in nodes.items():
        # Инлайним tools для llm_node
        tools = node_config.get("tools", [])
        if tools:
            node_config["tools"] = await _inline_tools_list(tools, container)
        
        # Инлайним code для code-нод с tool_id без кода
        if node_config.get("type") == "code" and node_config.get("tool_id") and not node_config.get("code"):
            tool_id = node_config["tool_id"]
            tool_ref = await container.tool_repository.get(tool_id)
            if tool_ref and tool_ref.code:
                node_config["code"] = tool_ref.code
                if tool_ref.args_schema:
                    node_config["args_schema"] = {
                        k: {"type": v.type, "description": v.description}
                        for k, v in tool_ref.args_schema.items()
                    }
                if tool_ref.parameters_schema:
                    node_config["parameters_schema"] = tool_ref.parameters_schema
                if tool_ref.description and not node_config.get("description"):
                    node_config["description"] = tool_ref.description
    return nodes


async def _inline_tools_list(
    tools: List[Any], 
    container: FlowContainer
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
    container: FlowContainer
) -> Dict[str, Any] | None:
    """Инлайнит один tool."""
    if isinstance(tool, str):
        # tool_id - достаём из библиотеки
        tool_ref = await container.tool_repository.get(tool)
        if tool_ref:
            return tool_ref.model_dump()
        
        # Может быть node (llm_node as tool)
        node = await container.node_repository.get(tool)
        if node:
            return await _node_to_inline_tool(node, container)
        
        # Может быть flow из репозитория (как tool по flow_id)
        flow_cfg = await container.flow_repository.get(tool)
        if flow_cfg:
            return _flow_config_to_inline_tool(flow_cfg)
        
        raise HTTPException(status_code=400, detail=f"Tool '{tool}' not found in library")
    
    elif isinstance(tool, dict):
        tool_id = tool.get("tool_id")
        
        # Если это llm_node - рекурсивно инлайним его tools
        if tool.get("type") == "llm_node" or tool.get("prompt"):
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


async def _node_to_inline_tool(node: NodeConfig, container: FlowContainer) -> Dict[str, Any]:
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


def _flow_config_to_inline_tool(flow_cfg: FlowConfig) -> Dict[str, Any]:
    """Конвертирует FlowConfig в inline tool."""
    return {
        "tool_id": flow_cfg.flow_id,
        "type": "flow",
        "name": flow_cfg.name,
        "description": flow_cfg.description,
        "entry": flow_cfg.entry,
        "nodes": flow_cfg.nodes,
        "edges": [e.model_dump() for e in flow_cfg.edges] if flow_cfg.edges else [],
    }

router = APIRouter(tags=["flows"])


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


class FlowCreateRequest(BaseModel):
    """Запрос на создание агента"""

    flow_id: str
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


class FlowResponse(BaseModel):
    """Ответ с данными агента"""

    flow_id: str
    version: str = ""
    name: str
    description: Optional[str]
    type: Optional[FlowType] = FlowType.LOCAL
    
    # LOCAL flow
    entry: Optional[str] = None
    nodes: Optional[Dict[str, Any]] = None
    edges: Optional[List[Dict[str, Any]]] = None
    variables: Dict[str, Any] = {}
    tags: List[str] = []
    skills: Dict[str, SkillResponse] = {}
    evaluation: Optional[Dict[str, Any]] = None
    hidden: bool = False
    has_bundle_update: bool = False
    
    # EXTERNAL flow (A2A)
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

    # manual | api | file (bundle в репозитории)
    source: str = "manual"


class ReloadFlowFromBundleResponse(BaseModel):
    flow_id: str
    message: str


class FlowStoreBundleResponse(BaseModel):
    bundle_id: str
    flow_id: str
    name: str
    description: Optional[str] = None
    tags: List[str] = []
    installed: bool


class FlowValidateRequest(BaseModel):
    """Запрос на валидацию агента"""

    nodes: Dict[str, Any]
    edges: List[Dict[str, Any]]
    entry: str
    variables: Dict[str, Any] = {}
    flow_id: Optional[str] = None


class ValidationErrorResponse(BaseModel):
    """Ошибка валидации"""

    code: str
    message: str
    severity: str
    node_id: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


class FlowValidateResponse(BaseModel):
    """Ответ на валидацию агента"""

    valid: bool
    errors: List[ValidationErrorResponse] = []
    state_keys_used: List[str] = []
    var_keys_used: List[str] = []


@router.post("/validate", response_model=FlowValidateResponse)
async def validate_flow(
    request: FlowValidateRequest,
    container: ContainerDep,
) -> FlowValidateResponse:
    """
    Валидирует конфигурацию агента без сохранения.
    
    Проверяет:
    - Структуру графа (entry, edges, достижимость нод)
    - Ссылки на агенты, tools, subflows
    - Переменные @var:
    - Парсит inline code на обращения к state
    - Пробует собрать исполняемый flow
    """
    validator = FlowValidator(
        flow_repository=container.flow_repository,
        tool_repository=container.tool_repository,
        node_repository=container.node_repository,
    )
    
    result = await validator.validate(
        nodes=request.nodes,
        edges=request.edges,
        entry=request.entry,
        variables=request.variables,
        flow_id=request.flow_id,
    )
    
    return FlowValidateResponse(
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


@router.get("/", response_model=OffsetPage[FlowResponse])
async def list_flows(
    container: ContainerDep,
    type: Optional[FlowType] = None,
    limit: int = Query(500, ge=1, le=2000, description="Максимум flows"),
    offset: int = Query(0, ge=0, description="Смещение для пагинации"),
) -> OffsetPage[FlowResponse]:
    """Список всех flows с опциональным фильтром по типу (local/external)"""
    flows, total = await asyncio.gather(
        container.flow_repository.list(limit=limit, offset=offset),
        container.flow_repository.count_all(),
    )

    if type is not None:
        flows = [f for f in flows if f.type == type]

    flows_root = Path(__file__).resolve().parents[3]
    bundle_update_flags = await _get_bundle_update_flags(flows, container, flows_root)

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
            "flow_id": f.flow_id,
            "version": f.version,
            "name": f.name,
            "description": f.description,
            "type": f.type,
            "tags": f.tags,
            "hidden": hidden,
            "source": getattr(f, "source", None) or "manual",
            "has_bundle_update": bundle_update_flags.get(f.flow_id, False),
        }
        
        # LOCAL flow
        if f.type == FlowType.LOCAL:
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
        # EXTERNAL flow (A2A endpoint)
        elif f.type == FlowType.EXTERNAL:
            status_value = f.status.value if isinstance(f.status, ExternalAgentStatus) else f.status
            response_data.update({
                "url": f.url,
                "auth_headers": f.auth_headers,
                "status": status_value,
                "last_health_check": f.last_health_check.isoformat() if f.last_health_check else None,
                "agent_card": f.agent_card,
            })
        
        result.append(FlowResponse(**response_data))
    return OffsetPage[FlowResponse](items=result, total=total, limit=limit, offset=offset)


@router.get("/store/bundles", response_model=List[FlowStoreBundleResponse])
async def list_store_bundles(container: ContainerDep) -> List[FlowStoreBundleResponse]:
    """
    Каталог bundle-агентов для UI Store.

    Возвращает только public=true из registry.yaml, исключая hidden=true в flow.json.
    """
    flows_root = Path(__file__).resolve().parents[3]
    registry_path = flows_root / "registry.yaml"
    bundles_dir = flows_root / "bundles"

    if not registry_path.exists():
        raise HTTPException(status_code=500, detail=f"Registry not found: {registry_path}")

    with open(registry_path, "r", encoding="utf-8") as f:
        registry_data = yaml.safe_load(f) or {}

    registry_flows = registry_data.get("flows")
    if not isinstance(registry_flows, list):
        raise HTTPException(status_code=500, detail="Registry field 'flows' must be a list")

    result: list[FlowStoreBundleResponse] = []
    for entry in registry_flows:
        if isinstance(entry, str):
            bundle_id = entry
            is_public = True
        elif isinstance(entry, dict):
            bundle_id = entry.get("id")
            is_public = entry.get("public", False)
        else:
            raise HTTPException(status_code=500, detail="Registry flow entry must be string or object")

        if not is_public:
            continue

        if not isinstance(bundle_id, str) or not bundle_id:
            raise HTTPException(status_code=500, detail="Registry flow entry must include non-empty string 'id'")

        flow_path = bundles_dir / bundle_id / "flow.json"
        if not flow_path.exists():
            raise HTTPException(status_code=500, detail=f"Bundle flow.json not found for '{bundle_id}'")

        with open(flow_path, "r", encoding="utf-8") as f:
            raw_flow = json.load(f)

        hidden_value = raw_flow.get("hidden", False)
        if not isinstance(hidden_value, bool):
            raise HTTPException(status_code=500, detail=f"Field 'hidden' must be boolean in bundle '{bundle_id}'")
        if hidden_value:
            continue

        flow_id = raw_flow.get("flow_id") or raw_flow.get("id")
        if not isinstance(flow_id, str) or not flow_id:
            raise HTTPException(status_code=500, detail=f"Bundle '{bundle_id}' must define non-empty flow_id")

        name = raw_flow.get("name")
        if not isinstance(name, str) or not name:
            raise HTTPException(status_code=500, detail=f"Bundle '{bundle_id}' must define non-empty name")

        description = raw_flow.get("description")
        if description is not None and not isinstance(description, str):
            raise HTTPException(status_code=500, detail=f"Bundle '{bundle_id}' field 'description' must be string")

        tags = raw_flow.get("tags", [])
        if not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags):
            raise HTTPException(status_code=500, detail=f"Bundle '{bundle_id}' field 'tags' must be list[str]")

        installed = await container.flow_repository.get(flow_id) is not None
        result.append(
            FlowStoreBundleResponse(
                bundle_id=bundle_id,
                flow_id=flow_id,
                name=name,
                description=description,
                tags=tags,
                installed=installed,
            )
        )

    return result


async def _validate_tool_nodes(
    nodes: Dict[str, Dict[str, Any]], 
    container: FlowContainer
) -> None:
    """Валидирует tool_id в code-нодах при отсутствии inline code."""
    for node_id, node_config in nodes.items():
        if node_config.get("type") == "code":
            tool_id = node_config.get("tool_id")
            has_code = "code" in node_config and node_config.get("code")
            
            if tool_id and not has_code:
                tool = await container.tool_repository.get(tool_id)
                if tool is None:
                    node = await container.node_repository.get(tool_id)
                    if node is None:
                        flow_cfg = await container.flow_repository.get(tool_id)
                        if flow_cfg is None:
                            raise HTTPException(
                                status_code=400, 
                                detail=f"Tool '{tool_id}' not found in library"
                            )


@router.post("/", response_model=FlowResponse)
async def create_flow(
    request: FlowCreateRequest, container: ContainerDep
) -> FlowResponse:
    """Создаёт flow."""
    # Валидируем tool_id в tool нодах
    await _validate_tool_nodes(dict(request.nodes), container)
    
    # Инлайним tools - заменяем tool_id на полные конфиги с кодом ПЕРЕД валидацией
    nodes = await _inline_tools_in_nodes(dict(request.nodes), container)
    
    # Валидируем ссылки (node_id, tool_id, flow_id) после инлайна
    validator = FlowValidator(
        flow_repository=container.flow_repository,
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

    flow_config = FlowConfig(
        flow_id=request.flow_id,
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

    await container.flow_repository.set(flow_config)

    skills_response = {
        skill_id: _skill_config_to_response(skill)
        for skill_id, skill in flow_config.skills.items()
    }


    return FlowResponse(
        flow_id=flow_config.flow_id,
        version=flow_config.version or "",
        name=flow_config.name,
        description=flow_config.description,
        type=flow_config.type or FlowType.LOCAL,
        entry=flow_config.entry,
        nodes=flow_config.nodes,
        edges=[
            {"from": e.from_node, "to": e.to_node, "condition": e.condition}
            for e in flow_config.edges
        ],
        variables=flow_config.variables,
        tags=flow_config.tags,
        skills=skills_response,
        evaluation=request.evaluation,
        hidden=getattr(flow_config, 'hidden', False),
        url=_generate_flow_url(flow_config.flow_id, flow_config.type, getattr(flow_config, 'url', None)),
        source=flow_config.source,
    )


@router.get("/{flow_id}", response_model=FlowResponse)
async def get_flow(
    flow_id: str, container: ContainerDep
) -> FlowResponse:
    """Получает flow по ID."""
    try:
        flow_cfg = await container.flow_repository.get(flow_id)
        if flow_cfg is None:
            raise HTTPException(status_code=404, detail="Flow not found")
        
        evaluation_dict = None
        if flow_cfg.evaluation:
            if hasattr(flow_cfg.evaluation, "model_dump"):
                evaluation_dict = flow_cfg.evaluation.model_dump()
            else:
                evaluation_dict = flow_cfg.evaluation
        
        skills_response = {}
        if flow_cfg.skills:
            for skill_id, skill in flow_cfg.skills.items():
                try:
                    skills_response[skill_id] = _skill_config_to_response(skill)
                except Exception as e:
                    logger.error(f"Ошибка конвертации skill '{skill_id}': {e}", exc_info=True)
                    raise HTTPException(
                        status_code=500,
                        detail=f"Ошибка обработки skill '{skill_id}': {str(e)}"
                    )
        
        edges_list = []
        if flow_cfg.edges:
            for e in flow_cfg.edges:
                if e is None:
                    continue
                edges_list.append({
                    "from": e.from_node,
                    "to": e.to_node,
                    "condition": e.condition
                })
        
        triggers_response = {}
        if flow_cfg.triggers:
            for trigger_id, trigger in flow_cfg.triggers.items():
                triggers_response[trigger_id] = trigger.model_dump() if hasattr(trigger, 'model_dump') else trigger
        
        source_value = getattr(flow_cfg, "source", None) or "manual"
        bundle_update = False
        if source_value == "file":
            flows_root = Path(__file__).resolve().parents[3]
            bundle_flags = await _get_bundle_update_flags([flow_cfg], container, flows_root)
            bundle_update = bundle_flags.get(flow_cfg.flow_id, False)

        return FlowResponse(
            flow_id=flow_cfg.flow_id,
            version=flow_cfg.version or "",
            name=flow_cfg.name,
            description=flow_cfg.description,
            type=flow_cfg.type or FlowType.LOCAL,
            entry=flow_cfg.entry,
            nodes=flow_cfg.nodes or {},
            edges=edges_list,
            variables=flow_cfg.variables or {},
            tags=flow_cfg.tags or [],
            skills=skills_response,
            evaluation=evaluation_dict,
            hidden=getattr(flow_cfg, 'hidden', False),
            url=_generate_flow_url(flow_cfg.flow_id, flow_cfg.type, getattr(flow_cfg, 'url', None)),
            triggers=triggers_response,
            resources=flow_cfg.resources or {},
            source=getattr(flow_cfg, "source", None) or "manual",
            has_bundle_update=bundle_update,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка получения flow '{flow_id}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка получения flow: {str(e)}")


@router.post("/{flow_id}/reload-from-bundle", response_model=ReloadFlowFromBundleResponse)
async def reload_flow_from_bundle(
    flow_id: str,
    container: ContainerDep,
) -> ReloadFlowFromBundleResponse:
    """
    Загружает/перезаписывает flow в БД из каталога ``apps/flows/bundles/<flow_id>/``.
    """
    flows_root = Path(__file__).resolve().parents[3]
    bundles_dir = flows_root / "bundles"
    registry_path = flows_root / "registry.yaml"

    loader = FlowsLoader(
        bundles_dir=bundles_dir,
        flow_repository=container.flow_repository,
        node_repository=container.node_repository,
        tool_repository=container.tool_repository,
        registry_path=registry_path,
    )

    try:
        loaded_id = await loader.reload_flow_bundle(flow_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    return ReloadFlowFromBundleResponse(
        flow_id=loaded_id,
        message=f"Flow '{loaded_id}' перезагружен из bundle",
    )


@router.put("/{flow_id}", response_model=FlowResponse)
async def update_flow(
    flow_id: str,
    request: FlowCreateRequest,
    container: ContainerDep,
) -> FlowResponse:
    """Обновляет flow (новая версия)."""
    existing = await container.flow_repository.get(flow_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Flow not found")

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

    flow_config = FlowConfig(
        flow_id=flow_id,
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

    await container.flow_repository.set(flow_config)

    skills_response = {
        skill_id: _skill_config_to_response(skill)
        for skill_id, skill in flow_config.skills.items()
    }

    triggers_response = {
        trigger_id: trigger.model_dump() if hasattr(trigger, 'model_dump') else trigger
        for trigger_id, trigger in flow_config.triggers.items()
    }

    return FlowResponse(
        flow_id=flow_config.flow_id,
        version=flow_config.version or "",
        name=flow_config.name,
        description=flow_config.description,
        type=flow_config.type or FlowType.LOCAL,
        entry=flow_config.entry,
        nodes=flow_config.nodes,
        edges=[
            {"from": e.from_node, "to": e.to_node, "condition": e.condition}
            for e in flow_config.edges
        ],
        variables=flow_config.variables,
        tags=flow_config.tags,
        skills=skills_response,
        evaluation=request.evaluation,
        hidden=getattr(flow_config, 'hidden', False),
        url=_generate_flow_url(flow_config.flow_id, flow_config.type, getattr(flow_config, 'url', None)),
        triggers=triggers_response,
        resources=flow_config.resources or {},
        source=flow_config.source,
    )


@router.delete("/{flow_id}")
async def delete_flow(
    flow_id: str, container: ContainerDep
) -> dict:
    """Удаляет flow."""
    deleted = await container.flow_repository.delete(flow_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Flow not found")
    return {"status": "deleted", "flow_id": flow_id}


@router.get("/{flow_id}/versions", response_model=List[str])
async def list_versions(
    flow_id: str, container: ContainerDep
) -> List[str]:
    """Список версий flow."""
    versions = await container.flow_repository.list_versions(flow_id)
    return versions


@router.get("/{flow_id}/versions/{version}", response_model=FlowResponse)
async def get_version(
    flow_id: str,
    version: str,
    container: ContainerDep,
) -> FlowResponse:
    """Конкретная версия flow."""
    version_cfg = await container.flow_repository.get_version(flow_id, version)
    if version_cfg is None:
        raise HTTPException(status_code=404, detail="Version not found")
    
    skills_response = {
        skill_id: _skill_config_to_response(skill)
        for skill_id, skill in (version_cfg.skills or {}).items()
    }
    
    edges_list = [
        {"from": e.from_node, "to": e.to_node, "condition": e.condition}
        for e in (version_cfg.edges or []) if e
    ]
    
    return FlowResponse(
        flow_id=version_cfg.flow_id,
        version=version_cfg.version or "",
        name=version_cfg.name,
        description=version_cfg.description,
        type=version_cfg.type or FlowType.LOCAL,
        entry=version_cfg.entry,
        nodes=version_cfg.nodes or {},
        edges=edges_list,
        variables=version_cfg.variables or {},
        tags=version_cfg.tags or [],
        skills=skills_response,
        hidden=getattr(version_cfg, 'hidden', False),
        url=_generate_flow_url(version_cfg.flow_id, version_cfg.type, getattr(version_cfg, 'url', None)),
        source=getattr(version_cfg, "source", None) or "manual",
    )


@router.post("/{flow_id}/versions/{version}/rollback")
async def rollback_version(
    flow_id: str,
    version: str,
    container: ContainerDep,
) -> Dict[str, Any]:
    """
    Откатывает flow к указанной версии.
    
    Делает указанную версию latest (не удаляет новые версии).
    """
    success = await container.flow_repository.rollback_to_version(flow_id, version)
    if not success:
        raise HTTPException(status_code=404, detail="Version not found")
    
    return {
        "status": "success",
        "message": f"Flow '{flow_id}' rolled back to version {version}",
        "flow_id": flow_id,
        "version": version,
    }
