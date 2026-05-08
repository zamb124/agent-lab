"""
API endpoints для flows.
"""

import asyncio
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, field_validator
import yaml

from apps.flows.src.container import FlowContainer
from apps.flows.src.dependencies import ContainerDep
from apps.flows.src.services.flows_loader import FlowsLoader, load_tools_to_db
from core.context import get_context
from core.logging import get_logger
from core.pagination import OffsetPage, ListResponse
from core.ui_events import publish_ui_event_to_user
from apps.flows.src.models import Edge, FlowConfig, BranchConfig, NodeConfig, FlowType, ExternalAgentStatus, TriggerConfig, MergeMode
from apps.flows.src.services.bundle_node_repair import (
    get_bundle_base_nodes_for_flow,
    repair_node_map_with_canonical_top_level,
)
from apps.flows.src.services.flow_contract_normalize import normalize_flow_config_dict
from apps.flows.src.services.flow_node_merge import merge_incoming_node_dict_for_persist
from apps.flows.src.services.flow_validator import FlowValidator
from apps.flows.src.models.flow_speech_settings import FlowSpeechSettings
from apps.flows.src.services.flow_speech_resolve import (
    effective_flow_speech_settings,
    flow_speech_to_triple_override,
    triple_to_voice_ws_query_dict,
)

logger = get_logger(__name__)


def _speech_to_json(settings: FlowSpeechSettings | None) -> Optional[Dict[str, Any]]:
    if settings is None:
        return None
    dumped = settings.model_dump(mode="json", exclude_none=True)
    return dumped if dumped else None


def _drop_files_fields(value: Any) -> Any:
    """Рекурсивно удаляет поле files из payload для семантического сравнения."""
    if isinstance(value, dict):
        return {
            key: _drop_files_fields(item)
            for key, item in value.items()
            if key != "files"
        }
    if isinstance(value, list):
        return [_drop_files_fields(item) for item in value]
    return value


def _flow_semantic_payload(flow_cfg: FlowConfig) -> Dict[str, Any]:
    """
    Детерминированный payload для сравнения текущего flow и bundle.

    Исключаются поля, которые ``build_flow_bundle_config`` не задаёт из flow.json
    (defaults FlowConfig), поля редактора/платформы (metadata, speech, resources)
    и служебные — иначе ``has_bundle_update`` ложноположительный.
    """
    payload = flow_cfg.model_dump(
        mode="json",
        exclude={
            "version",
            "created_at",
            "updated_at",
            "source",
            "public_fields",
            "store_card_image_url",
            "metadata",
            "speech",
            "resources",
            "channels",
            "store",
            "mock",
            "permission",
            "timeout",
            "max_retries",
            "hidden",
        },
    )
    return _drop_files_fields(payload)


def _canonical_flow_semantic_payload(flow_cfg: FlowConfig) -> Dict[str, Any]:
    """
    Payload для сравнения с bundle после того же пайплайна, что при READ из БД:
    ``model_dump`` → ``normalize_flow_config_dict`` → ``FlowConfig.model_validate``.
    Иначе свежесобранный bundle и конфиг из репозитория расходятся в ``nodes.tools`` и т.п.
    """
    normalized = normalize_flow_config_dict(flow_cfg.model_dump(mode="json"))
    canonical = FlowConfig.model_validate(normalized)
    return _flow_semantic_payload(canonical)


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
    # Иначе _defaults пустой: _apply_defaults не мержит registry.yaml defaults.llm,
    # а после reload в БД llm уже с defaults — вечный has_bundle_update.
    loader.load_registry_yaml()
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

        flags[flow_cfg.flow_id] = _canonical_flow_semantic_payload(flow_cfg) != _canonical_flow_semantic_payload(
            bundle_cfg
        )

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


class BranchRequest(BaseModel):
    """Ветка (branch) в запросе"""

    name: str
    description: str = ""
    tags: List[str] = []
    entry: Optional[str] = None
    nodes: Optional[Dict[str, Any]] = None
    nodes_mode: Optional[str] = None
    edges: Optional[List[Dict[str, Any]]] = None
    edges_mode: Optional[str] = None
    variables: Dict[str, Any] = {}
    variables_mode: Optional[str] = None
    speech: Optional[FlowSpeechSettings] = None


class BranchResponse(BaseModel):
    """Ветка (branch) в ответе"""

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
    speech: Optional[Dict[str, Any]] = None


def _branch_config_to_response(branch_cfg: BranchConfig) -> BranchResponse:
    """Конвертирует BranchConfig в BranchResponse."""
    edges = None
    if branch_cfg.edges:
        edges = []
        for e in branch_cfg.edges:
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
    if branch_cfg.nodes_mode:
        nodes_mode = branch_cfg.nodes_mode.value if hasattr(branch_cfg.nodes_mode, 'value') else str(branch_cfg.nodes_mode)

    edges_mode = None
    if branch_cfg.edges_mode:
        edges_mode = branch_cfg.edges_mode.value if hasattr(branch_cfg.edges_mode, 'value') else str(branch_cfg.edges_mode)

    variables_mode = None
    if branch_cfg.variables_mode:
        variables_mode = branch_cfg.variables_mode.value if hasattr(branch_cfg.variables_mode, 'value') else str(branch_cfg.variables_mode)

    return BranchResponse(
        name=branch_cfg.name,
        description=branch_cfg.description,
        tags=branch_cfg.tags,
        entry=branch_cfg.entry,
        nodes=branch_cfg.nodes,
        edges=edges,
        variables=branch_cfg.variables,
        nodes_mode=nodes_mode,
        edges_mode=edges_mode,
        variables_mode=variables_mode,
        speech=_speech_to_json(branch_cfg.speech),
    )


def _branch_request_to_config(
    branch_id: str,
    branch_req: BranchRequest,
    existing: Optional[BranchConfig] = None,
) -> BranchConfig:
    """Конвертирует BranchRequest в BranchConfig."""
    edges = None
    if branch_req.edges:
        edges = [
            Edge(
                from_node=e.get("from") or e.get("from_node"),
                to_node=e.get("to") or e.get("to_node"),
                condition=e.get("condition"),
            )
            for e in branch_req.edges
        ]

    def _mode(
        raw: Optional[str],
        ex: Optional[MergeMode],
        default: MergeMode,
    ) -> MergeMode:
        if raw is not None and raw != "":
            return MergeMode(raw)
        if ex is not None:
            return ex
        return default

    ex_n = existing.nodes_mode if existing is not None else None
    ex_e = existing.edges_mode if existing is not None else None
    ex_v = existing.variables_mode if existing is not None else None
    speech_val: Optional[FlowSpeechSettings] = None
    if branch_req.speech is not None:
        speech_val = branch_req.speech
    elif existing is not None:
        speech_val = existing.speech

    return BranchConfig(
        name=branch_req.name,
        description=branch_req.description,
        tags=branch_req.tags,
        entry=branch_req.entry,
        nodes=branch_req.nodes,
        edges=edges,
        variables=branch_req.variables,
        nodes_mode=_mode(branch_req.nodes_mode, ex_n, MergeMode.REPLACE),
        edges_mode=_mode(branch_req.edges_mode, ex_e, MergeMode.REPLACE),
        variables_mode=_mode(branch_req.variables_mode, ex_v, MergeMode.MERGE),
        speech=speech_val,
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
    branches: Dict[str, BranchRequest] = {}
    evaluation: Optional[Dict[str, Any]] = None
    triggers: Dict[str, Any] = {}
    resources: Dict[str, Any] = {}
    store_card_image_url: Optional[str] = None
    speech: Optional[FlowSpeechSettings] = None

    @field_validator("store_card_image_url", mode="before")
    @classmethod
    def _empty_store_card_image_url(cls, value: Any) -> Optional[str]:
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        return value


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
    branches: Dict[str, BranchResponse] = {}
    evaluation: Optional[Dict[str, Any]] = None
    hidden: bool = False
    has_bundle_update: bool = False
    
    # EXTERNAL flow (A2A)
    url: Optional[str] = None
    headers: Optional[Dict[str, str]] = None
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

    # UI-метаданные (sticky_notes и пр.)
    metadata: Dict[str, Any] = {}

    # URL обложки агента (после загрузки файла или из bundle)
    store_card_image_url: Optional[str] = None

    # manual | api | file (bundle в репозитории)
    source: str = "manual"

    speech: Optional[Dict[str, Any]] = None


class FlowVoiceSessionQueryResponse(BaseModel):
    """Query-параметры для WS voice-сессии (effective flow + branch speech)."""

    query: Dict[str, str]


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


@router.get("", response_model=OffsetPage[FlowResponse])
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
        branches_response = {
            branch_id: _branch_config_to_response(branch_cfg)
            for branch_id, branch_cfg in (f.branches or {}).items()
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
            "store_card_image_url": getattr(f, "store_card_image_url", None),
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
                "branches": branches_response,
                "evaluation": evaluation_dict,
            })
        # EXTERNAL flow (A2A endpoint)
        elif f.type == FlowType.EXTERNAL:
            status_value = f.status.value if isinstance(f.status, ExternalAgentStatus) else f.status
            response_data.update({
                "url": f.url,
                "headers": f.headers,
                "status": status_value,
                "last_health_check": f.last_health_check.isoformat() if f.last_health_check else None,
                "agent_card": f.agent_card,
            })
        
        result.append(FlowResponse(**response_data))
    return OffsetPage[FlowResponse](items=result, total=total, limit=limit, offset=offset)


@router.get("/store/bundles", response_model=ListResponse[FlowStoreBundleResponse])
async def list_store_bundles(container: ContainerDep) -> ListResponse[FlowStoreBundleResponse]:
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

    return ListResponse[FlowStoreBundleResponse](items=result)


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


@router.post("", response_model=FlowResponse)
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

    branches_payload = {
        branch_id: _branch_request_to_config(branch_id, branch_req, None)
        for branch_id, branch_req in request.branches.items()
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
        branches=branches_payload,
        evaluation=request.evaluation,
        source="api",
        store_card_image_url=request.store_card_image_url,
        speech=request.speech,
    )

    await container.flow_repository.set(flow_config)

    branches_response = {
        branch_id: _branch_config_to_response(branch_cfg)
        for branch_id, branch_cfg in flow_config.branches.items()
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
        branches=branches_response,
        evaluation=request.evaluation,
        hidden=getattr(flow_config, 'hidden', False),
        url=_generate_flow_url(flow_config.flow_id, flow_config.type, getattr(flow_config, 'url', None)),
        source=flow_config.source,
        store_card_image_url=getattr(flow_config, "store_card_image_url", None),
        speech=_speech_to_json(flow_config.speech),
    )


@router.get("/{flow_id}/voice-session-query", response_model=FlowVoiceSessionQueryResponse)
async def get_flow_voice_session_query(
    flow_id: str,
    container: ContainerDep,
    branch_id: str = Query("default", description="ID ветки графа для мержа speech"),
) -> FlowVoiceSessionQueryResponse:
    cfg = await container.flow_repository.get(flow_id)
    if cfg is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    eff = effective_flow_speech_settings(cfg, branch_id)
    stt, tts, vad = flow_speech_to_triple_override(eff)
    return FlowVoiceSessionQueryResponse(query=triple_to_voice_ws_query_dict(stt, tts, vad))


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
        
        branches_response = {}
        if flow_cfg.branches:
            for branch_id, branch_cfg in flow_cfg.branches.items():
                try:
                    branches_response[branch_id] = _branch_config_to_response(branch_cfg)
                except Exception as e:
                    logger.error(f"Ошибка конвертации ветки '{branch_id}': {e}", exc_info=True)
                    raise HTTPException(
                        status_code=500,
                        detail=f"Ошибка обработки ветки '{branch_id}': {str(e)}"
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
            branches=branches_response,
            evaluation=evaluation_dict,
            hidden=getattr(flow_cfg, 'hidden', False),
            url=_generate_flow_url(flow_cfg.flow_id, flow_cfg.type, getattr(flow_cfg, 'url', None)),
            triggers=triggers_response,
            resources=flow_cfg.resources or {},
            metadata=getattr(flow_cfg, "metadata", None) or {},
            source=getattr(flow_cfg, "source", None) or "manual",
            has_bundle_update=bundle_update,
            store_card_image_url=getattr(flow_cfg, "store_card_image_url", None),
            speech=_speech_to_json(flow_cfg.speech),
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
    # Для установки bundle в компанию требуются все code-tools из runtime-модулей.
    # Иначе инлайнинг упадёт на tool_id, которого нет в tool_repository текущей компании.
    await load_tools_to_db(container.tool_repository)

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
        msg = str(e).lower()
        if "не найден" in msg or "not found" in msg:
            raise HTTPException(status_code=404, detail=str(e)) from e
        raise HTTPException(status_code=400, detail=str(e)) from e

    reloaded_cfg = await container.flow_repository.get(loaded_id)
    if reloaded_cfg is None:
        raise HTTPException(status_code=500, detail=f"Flow '{loaded_id}' missing after reload-from-bundle")

    ctx = get_context()
    if ctx and ctx.user and ctx.user.user_id:
        await publish_ui_event_to_user(
            user_id=ctx.user.user_id,
            type="flows/flow/updated",
            payload={"flow_id": loaded_id, "version": reloaded_cfg.version or ""},
        )

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

    # Патч только с координатами не затирает семантику ноды, сохранённую ранее
    merged_top_nodes = merge_incoming_node_dict_for_persist(
        dict(request.nodes), existing.nodes or {}
    )
    branches: Dict[str, BranchConfig] = {}
    for branch_id, branch_req in request.branches.items():
        ex = (existing.branches or {}).get(branch_id)
        ex_n = (ex.nodes if ex else None) or {}
        if branch_req.nodes is None:
            merged_n = branch_req.nodes
        else:
            merged_n = merge_incoming_node_dict_for_persist(dict(branch_req.nodes), ex_n)
        ex_cfg = (existing.branches or {}).get(branch_id)
        branches[branch_id] = _branch_request_to_config(
            branch_id, branch_req.model_copy(update={"nodes": merged_n}), ex_cfg
        )

    # Инлайним tools - заменяем tool_id на полные конфиги с кодом
    nodes = await _inline_tools_in_nodes(merged_top_nodes, container)
    if (getattr(existing, "source", None) or "manual") == "file":
        b_nodes = get_bundle_base_nodes_for_flow(flow_id)
        if b_nodes:
            nodes = repair_node_map_with_canonical_top_level(nodes, b_nodes)

    edges = [
        Edge(
            from_node=e.get("from") or e.get("from_node"),
            to_node=e.get("to") or e.get("to_node"),
            condition=e.get("condition"),
        )
        for e in request.edges
    ]

    triggers = {
        trigger_id: TriggerConfig(**trigger_data) if isinstance(trigger_data, dict) else trigger_data
        for trigger_id, trigger_data in request.triggers.items()
    }

    resources = request.resources or {}

    speech_merged = request.speech if request.speech is not None else existing.speech

    flow_config = FlowConfig(
        flow_id=flow_id,
        name=request.name,
        description=request.description,
        entry=request.entry,
        nodes=nodes,  # Инлайненные nodes
        edges=edges,
        variables=request.variables,
        tags=request.tags,
        branches=branches,
        evaluation=request.evaluation,
        source=existing.source,
        triggers=triggers,
        resources=resources,
        metadata=getattr(existing, "metadata", None) or {},
        store_card_image_url=request.store_card_image_url,
        speech=speech_merged,
    )

    await container.flow_repository.set(flow_config)

    ctx = get_context()
    if ctx and ctx.user and ctx.user.user_id:
        await publish_ui_event_to_user(
            user_id=ctx.user.user_id,
            type="flows/flow/updated",
            payload={"flow_id": flow_id, "version": flow_config.version or ""},
        )

    branches_response = {
        branch_id: _branch_config_to_response(branch_cfg)
        for branch_id, branch_cfg in flow_config.branches.items()
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
        branches=branches_response,
        evaluation=request.evaluation,
        hidden=getattr(flow_config, 'hidden', False),
        url=_generate_flow_url(flow_config.flow_id, flow_config.type, getattr(flow_config, 'url', None)),
        triggers=triggers_response,
        resources=flow_config.resources or {},
        metadata=getattr(flow_config, "metadata", None) or {},
        source=flow_config.source,
        store_card_image_url=getattr(flow_config, "store_card_image_url", None),
        speech=_speech_to_json(flow_config.speech),
    )


class BulkDeleteNodesRequest(BaseModel):
    """Запрос на массовое удаление нод с отчисткой связанных рёбер."""

    node_ids: List[str]


class BulkDeleteNodesResponse(BaseModel):
    """Результат массового удаления."""

    flow_id: str
    deleted_node_ids: List[str]
    deleted_edge_count: int


@router.post("/{flow_id}/nodes/bulk_delete", response_model=BulkDeleteNodesResponse)
async def bulk_delete_nodes(
    flow_id: str,
    request: BulkDeleteNodesRequest,
    container: ContainerDep,
) -> BulkDeleteNodesResponse:
    """Удаляет несколько нод из flow вместе со связанными рёбрами."""
    if not request.node_ids:
        raise HTTPException(status_code=400, detail="node_ids is required")

    existing = await container.flow_repository.get(flow_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Flow not found")

    target_ids = set(request.node_ids)
    deleted_ids: List[str] = []
    new_nodes: Dict[str, Any] = {}
    for node_id, node_value in (existing.nodes or {}).items():
        if node_id in target_ids:
            deleted_ids.append(node_id)
            continue
        new_nodes[node_id] = node_value

    new_edges: List[Edge] = []
    deleted_edge_count = 0
    for edge in existing.edges or []:
        if edge.from_node in target_ids or edge.to_node in target_ids:
            deleted_edge_count += 1
            continue
        new_edges.append(edge)

    new_entry = existing.entry if existing.entry not in target_ids else None

    flow_config = FlowConfig(
        flow_id=existing.flow_id,
        name=existing.name,
        description=existing.description,
        type=existing.type or FlowType.LOCAL,
        entry=new_entry,
        nodes=new_nodes,
        edges=new_edges,
        variables=existing.variables or {},
        tags=existing.tags or [],
        branches=existing.branches or {},
        evaluation=existing.evaluation,
        source=existing.source,
        triggers=existing.triggers or {},
        resources=existing.resources or {},
        metadata=getattr(existing, "metadata", None) or {},
        store_card_image_url=getattr(existing, "store_card_image_url", None),
        speech=getattr(existing, "speech", None),
    )
    await container.flow_repository.set(flow_config)

    ctx = get_context()
    if ctx and ctx.user and ctx.user.user_id:
        await publish_ui_event_to_user(
            user_id=ctx.user.user_id,
            type="flows/flow/updated",
            payload={"flow_id": flow_id, "version": flow_config.version or ""},
        )

    return BulkDeleteNodesResponse(
        flow_id=flow_id,
        deleted_node_ids=deleted_ids,
        deleted_edge_count=deleted_edge_count,
    )


class FlowMetadataRequest(BaseModel):
    """PATCH-обновление flow.config.metadata (sticky_notes, etc.)."""

    sticky_notes: Optional[List[Dict[str, Any]]] = None


class FlowMetadataResponse(BaseModel):
    flow_id: str
    metadata: Dict[str, Any]


@router.patch("/{flow_id}/metadata", response_model=FlowMetadataResponse)
async def update_flow_metadata(
    flow_id: str,
    request: FlowMetadataRequest,
    container: ContainerDep,
) -> FlowMetadataResponse:
    """Обновляет метаданные flow (sticky_notes и пр.) без полной перезаписи."""
    existing = await container.flow_repository.get(flow_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Flow not found")

    metadata: Dict[str, Any] = dict(getattr(existing, "metadata", None) or {})
    if request.sticky_notes is not None:
        metadata["sticky_notes"] = request.sticky_notes

    flow_config = FlowConfig(
        flow_id=existing.flow_id,
        name=existing.name,
        description=existing.description,
        type=existing.type or FlowType.LOCAL,
        entry=existing.entry,
        nodes=existing.nodes or {},
        edges=existing.edges or [],
        variables=existing.variables or {},
        tags=existing.tags or [],
        branches=existing.branches or {},
        evaluation=existing.evaluation,
        source=existing.source,
        triggers=existing.triggers or {},
        resources=existing.resources or {},
        metadata=metadata,
        store_card_image_url=getattr(existing, "store_card_image_url", None),
        speech=getattr(existing, "speech", None),
    )
    await container.flow_repository.set(flow_config)

    return FlowMetadataResponse(flow_id=flow_id, metadata=metadata)


@router.delete("/{flow_id}")
async def delete_flow(
    flow_id: str, container: ContainerDep
) -> dict:
    """Удаляет flow."""
    deleted = await container.flow_repository.delete(flow_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Flow not found")

    ctx = get_context()
    if ctx and ctx.user and ctx.user.user_id:
        await publish_ui_event_to_user(
            user_id=ctx.user.user_id,
            type="flows/flow/deleted",
            payload={"flow_id": flow_id},
        )

    return {"status": "deleted", "flow_id": flow_id}


@router.get("/{flow_id}/versions", response_model=ListResponse[str])
async def list_versions(
    flow_id: str, container: ContainerDep
) -> ListResponse[str]:
    """Список версий flow."""
    versions = await container.flow_repository.list_versions(flow_id)
    return ListResponse[str](items=versions)


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
    
    branches_response = {
        branch_id: _branch_config_to_response(branch_cfg)
        for branch_id, branch_cfg in (version_cfg.branches or {}).items()
    }
    
    edges_list = [
        {"from": e.from_node, "to": e.to_node, "condition": e.condition}
        for e in (version_cfg.edges or []) if e
    ]
    
    triggers_response = {}
    if version_cfg.triggers:
        for trigger_id, trigger in version_cfg.triggers.items():
            triggers_response[trigger_id] = trigger.model_dump() if hasattr(trigger, 'model_dump') else trigger

    evaluation_dict = None
    if version_cfg.evaluation:
        evaluation_dict = {k: v.model_dump() if hasattr(v, 'model_dump') else v for k, v in version_cfg.evaluation.items()}

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
        branches=branches_response,
        evaluation=evaluation_dict,
        hidden=getattr(version_cfg, 'hidden', False),
        url=_generate_flow_url(version_cfg.flow_id, version_cfg.type, getattr(version_cfg, 'url', None)),
        triggers=triggers_response,
        resources=version_cfg.resources or {},
        metadata=getattr(version_cfg, "metadata", None) or {},
        source=getattr(version_cfg, "source", None) or "manual",
        store_card_image_url=getattr(version_cfg, "store_card_image_url", None),
        speech=_speech_to_json(version_cfg.speech),
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
