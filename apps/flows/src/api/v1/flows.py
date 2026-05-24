"""
API endpoints для flows.
"""

import asyncio
import copy
import uuid
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, ClassVar

import yaml
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator

from apps.flows.src.container import FlowContainer
from apps.flows.src.dependencies import ContainerDep
from apps.flows.src.models import (
    BranchConfig,
    DataflowInspectResult,
    Edge,
    ExternalAgentStatus,
    FlowConfig,
    FlowType,
    FlowVariableConfig,
    GraphNodeConfig,
    MergeMode,
    NodeConfig,
    ResourceReference,
    TestCaseConfig,
    TriggerConfig,
)
from apps.flows.src.models.flow_speech_settings import FlowSpeechSettings
from apps.flows.src.services.flow_dataflow_inspector import (
    inspect_flow_dataflow,
)
from apps.flows.src.services.flow_speech_resolve import (
    effective_flow_speech_settings,
    flow_speech_to_triple_override,
    triple_to_voice_ws_query_dict,
)
from apps.flows.src.services.flow_validator import FlowValidator
from apps.flows.src.services.flows_loader import FlowsLoader, load_tools_to_db
from core.clients.voice_resolver import resolve_effective_tts_voice_for_ws
from core.config import get_settings
from core.context import get_context
from core.identity.flow_preview_handoff import store_flow_preview_handoff
from core.identity.runtime_users import ensure_persisted_runtime_user
from core.logging import get_logger
from core.models.embed_models import EmbedConfig, EmbedMapping, EmbedStatus
from core.pagination import ListResponse, OffsetPage
from core.short_links.service import require_platform_public_base_url
from core.types import (
    JsonArray,
    JsonObject,
    JsonValue,
    parse_json_object,
    require_json_array,
    require_json_object,
    require_json_value,
)
from core.ui_events.dispatcher import publish_ui_event_to_user
from core.utils.tokens import get_token_service

logger = get_logger(__name__)

_FLOW_PREVIEW_SHARE_TTL_SECONDS = 86400
_GRAPH_NODE_MAP_ADAPTER: TypeAdapter[dict[str, GraphNodeConfig]] = TypeAdapter(dict[str, GraphNodeConfig])


def _preview_share_base_urls(request: Request) -> tuple[str, str]:
    """Возвращает (flows_base_url, platform_ui_origin) для сценария встраивания."""
    settings = get_settings()
    if settings.server.env == "production":
        base = require_platform_public_base_url().rstrip("/")
        return f"{base}/flows", base

    forwarded_proto = request.headers.get("x-forwarded-proto")
    scheme = (forwarded_proto or request.url.scheme or "").strip().lower()
    if scheme not in ("http", "https"):
        raise ValueError("_preview_share_base_urls: ожидалась схема http или https")

    forwarded_host = request.headers.get("x-forwarded-host")
    host = (forwarded_host or request.headers.get("host") or request.url.netloc or "").strip()
    if not host:
        raise ValueError("_preview_share_base_urls: host is required")

    base = f"{scheme}://{host}".rstrip("/")
    return f"{base}/flows", base


class FlowPreviewShareRequest(BaseModel):
    branch_id: str = Field(default="default", description="Ветка графа (skill)")
    guest_max_user_messages: int | None = Field(
        default=None,
        ge=1,
        le=500,
        description="Лимит пользовательских сообщений гостя на один диалог (embed-session); не задано — без лимита",
    )


class FlowPreviewShareResponse(BaseModel):
    share_url: str


def _speech_to_json(settings: FlowSpeechSettings | None) -> JsonObject | None:
    if settings is None:
        return None
    dumped = parse_json_object(settings.model_dump_json(exclude_none=True), "speech")
    return dumped if dumped else None


def _drop_files_fields(value: JsonValue) -> JsonValue:
    """Рекурсивно удаляет поле files из payload для семантического сравнения."""
    if isinstance(value, dict):
        out: JsonObject = {}
        for key, item in value.items():
            if key != "files":
                out[key] = _drop_files_fields(item)
        return out
    if isinstance(value, list):
        out_array: JsonArray = []
        for item in value:
            out_array.append(_drop_files_fields(item))
        return out_array
    return value


def _flow_semantic_payload(flow_cfg: FlowConfig) -> JsonObject:
    """
    Детерминированный payload для сравнения текущего flow и bundle.

    Исключаются поля, которые ``build_flow_bundle_config`` не задаёт из flow.json
    (defaults FlowConfig), поля редактора/платформы (metadata, speech, resources)
    и служебные — иначе ``has_bundle_update`` ложноположительный.
    """
    payload = parse_json_object(
        flow_cfg.model_dump_json(
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
        ),
        "flow.semantic_payload",
    )
    return require_json_object(_drop_files_fields(payload), "flow.semantic_payload")


def _build_bundle_index(flows_root: Path) -> dict[str, str]:
    """flow_id -> bundle_id для записей из registry.yaml."""
    registry_path = flows_root / "registry.yaml"
    bundles_dir = flows_root / "bundles"

    if not registry_path.exists():
        raise HTTPException(status_code=500, detail=f"Registry not found: {registry_path}")

    with open(registry_path, "r", encoding="utf-8") as f:
        registry_data = require_json_object(yaml.safe_load(f) or {}, "registry.yaml")

    try:
        registry_flows = require_json_array(registry_data.get("flows", []), "registry.flows")
    except ValueError as exc:
        raise HTTPException(status_code=500, detail="Registry field 'flows' must be a list") from exc

    flow_to_bundle: dict[str, str] = {}
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
            raw_flow = parse_json_object(f.read(), f"bundles.{bundle_id}.flow")

        flow_id = raw_flow.get("flow_id") or raw_flow.get("id")
        if not isinstance(flow_id, str) or not flow_id:
            raise HTTPException(status_code=500, detail=f"Bundle '{bundle_id}' must define non-empty flow_id")

        flow_to_bundle[flow_id] = bundle_id

    return flow_to_bundle


async def _get_bundle_update_flags(
    flows: list[FlowConfig],
    container: ContainerDep,
    flows_root: Path,
) -> dict[str, bool]:
    """Возвращает признак наличия обновлений bundle для flow с source=file."""
    flow_to_bundle = _build_bundle_index(flows_root)
    file_flow_ids = [f.flow_id for f in flows if (f.source or "manual") == "file"]
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
    await loader.load_tools_cache()
    await loader.load_nodes_cache()

    flags: dict[str, bool] = {}
    for flow_cfg in flows:
        source_value = flow_cfg.source or "manual"
        if source_value != "file":
            continue

        bundle_id = flow_to_bundle.get(flow_cfg.flow_id)
        if not bundle_id:
            raise HTTPException(status_code=500, detail=f"Bundle mapping not found for flow '{flow_cfg.flow_id}'")

        await loader.preload_nodes_to_cache(bundle_id)
        bundle_cfg = await loader.build_flow_bundle_config(bundle_id)
        if bundle_cfg is None:
            raise HTTPException(status_code=500, detail=f"Failed to build bundle config for '{bundle_id}'")

        flags[flow_cfg.flow_id] = _flow_semantic_payload(flow_cfg) != _flow_semantic_payload(bundle_cfg)

    return flags


def _generate_flow_url(flow_id: str, flow_kind: FlowType | None = None, external_url: str | None = None) -> str:
    """Публичный URL flow (или внешний base URL для EXTERNAL)."""
    if flow_kind == FlowType.EXTERNAL and external_url:
        return external_url

    settings = get_settings()
    return f"https://{settings.server.host}:{settings.server.port}/flows/{flow_id}"


def _edge_to_json(edge: Edge) -> JsonObject:
    return parse_json_object(edge.model_dump_json(by_alias=True), "edge")


def _dataflow_edge_models(raw_edges: Sequence[JsonValue | Edge] | JsonValue | None, field_name: str) -> list[Edge]:
    if raw_edges is None:
        return []
    if not isinstance(raw_edges, list):
        raise ValueError(f"{field_name} must be a list")
    out: list[Edge] = []
    for idx, edge in enumerate(raw_edges):
        item_name = f"{field_name}[{idx}]"
        if isinstance(edge, Edge):
            out.append(edge)
        elif isinstance(edge, BaseModel):
            payload = parse_json_object(edge.model_dump_json(by_alias=True), item_name)
            out.append(Edge.model_validate(payload))
        else:
            payload = require_json_value(edge, item_name)
            out.append(Edge.model_validate(payload))
    return out


def _flow_variable_models(
    raw_variables: JsonValue | Mapping[str, FlowVariableConfig] | None,
    field_name: str,
) -> dict[str, FlowVariableConfig]:
    if raw_variables is None:
        return {}
    if not isinstance(raw_variables, Mapping):
        raise ValueError(f"{field_name} must be an object")
    out: dict[str, FlowVariableConfig] = {}
    for key, raw_value in raw_variables.items():
        if not key:
            raise ValueError(f"{field_name} keys must be non-empty strings")
        if isinstance(raw_value, FlowVariableConfig):
            out[key] = raw_value
        elif isinstance(raw_value, Mapping):
            out[key] = FlowVariableConfig.model_validate(
                require_json_object(raw_value, f"{field_name}.{key}")
            )
        else:
            out[key] = FlowVariableConfig(
                value=require_json_value(raw_value, f"{field_name}.{key}"),
            )
    return out


def _graph_nodes_payload(nodes: Mapping[str, GraphNodeConfig]) -> dict[str, JsonObject]:
    return {
        node_id: parse_json_object(node.model_dump_json(by_alias=True, exclude_none=True), f"nodes.{node_id}")
        for node_id, node in nodes.items()
    }


async def _inline_tools_in_nodes(
    nodes: dict[str, JsonObject],
    container: FlowContainer
) -> dict[str, JsonObject]:
    """
    Инлайнит tools в nodes flow.

    Для каждой ноды:
    - Инлайнит tools (поле tools в llm_node)
    - Инлайнит code для нод типа tool с tool_id
    """
    for node_id, node_config in nodes.items():
        # Инлайним tools для llm_node
        tools = node_config.get("tools", [])
        if isinstance(tools, list) and tools:
            node_config["tools"] = await inline_tools_list(tools, container)

        # Инлайним code для code-нод с tool_id без кода
        if node_config.get("type") == "code" and node_config.get("tool_id") and not node_config.get("code"):
            tool_id = node_config["tool_id"]
            if not isinstance(tool_id, str):
                continue
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
        nodes[node_id] = node_config
    return nodes


async def inline_tools_list(
    tools: Sequence[JsonValue],
    container: FlowContainer
) -> list[JsonValue]:
    """Инлайнит список tools."""
    inlined: list[JsonValue] = []
    for tool in tools:
        inlined_tool = await _inline_single_tool(tool, container)
        if inlined_tool:
            inlined.append(inlined_tool)
    return inlined


async def _inline_single_tool(
    tool: JsonValue,
    container: FlowContainer
) -> JsonObject | None:
    """Инлайнит один tool."""
    if isinstance(tool, str):
        # tool_id - достаём из библиотеки
        tool_ref = await container.tool_repository.get(tool)
        if tool_ref:
            return parse_json_object(tool_ref.model_dump_json(), "tool")

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
        tool_obj = require_json_object(tool, "tool")
        tool_id = tool_obj.get("tool_id")

        # Если это llm_node - рекурсивно инлайним его tools
        if tool_obj.get("type") == "llm_node" or tool_obj.get("prompt"):
            nested_tools = tool_obj.get("tools")
            if isinstance(nested_tools, list):
                tool_obj["tools"] = await inline_tools_list(nested_tools, container)
            return tool_obj

        # Если нет code - дополняем из библиотеки
        if isinstance(tool_id, str) and tool_id and not tool_obj.get("code"):
            tool_ref = await container.tool_repository.get(tool_id)
            if tool_ref and tool_ref.code:
                merged = parse_json_object(tool_ref.model_dump_json(), "tool")
                merged.update(tool_obj)  # Переопределения из запроса приоритетнее
                return merged

        return tool_obj

    return None


async def _node_to_inline_tool(node: NodeConfig, container: FlowContainer) -> JsonObject:
    """Конвертирует NodeConfig в inline tool."""
    result: JsonObject = {
        "tool_id": node.node_id,
        "type": node.type.value,
        "name": node.name,
        "description": node.description,
        "prompt": node.prompt,
    }
    if node.llm:
        result["llm"] = parse_json_object(node.llm.model_dump_json(), "node.llm")
    if node.code:
        result["code"] = node.code
    if node.tools:
        tools_list: list[JsonValue] = []
        for tool in node.tools:
            if isinstance(tool, str):
                tools_list.append(tool)
            else:
                tools_list.append(parse_json_object(tool.model_dump_json(), "node.tools[]"))
        result["tools"] = await inline_tools_list(tools_list, container)
    return result


def _flow_config_to_inline_tool(flow_cfg: FlowConfig) -> JsonObject:
    """Конвертирует FlowConfig в inline tool."""
    return {
        "tool_id": flow_cfg.flow_id,
        "type": "flow",
        "name": flow_cfg.name,
        "description": flow_cfg.description,
        "entry": flow_cfg.entry,
        "nodes": flow_cfg.nodes or {},
        "edges": [_edge_to_json(edge) for edge in flow_cfg.edges],
    }

router = APIRouter(tags=["flows"])


class EdgeRequest(BaseModel):
    """Edge в запросе"""

    model_config: ClassVar[ConfigDict] = ConfigDict(populate_by_name=True)

    from_node: str
    to_node: str | None
    condition: str | None = None


class BranchRequest(BaseModel):
    """Ветка (branch) в запросе"""

    name: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    entry: str | None = None
    nodes: dict[str, GraphNodeConfig] | None = None
    nodes_mode: str | None = None
    edges: list[Edge] | None = None
    edges_mode: str | None = None
    variables: JsonObject = Field(default_factory=dict)
    variables_mode: str | None = None
    speech: FlowSpeechSettings | None = None


class BranchResponse(BaseModel):
    """Ветка (branch) в ответе"""

    name: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    entry: str | None = None
    nodes: dict[str, JsonObject] | None = None
    edges: list[Edge] | None = None
    variables: dict[str, FlowVariableConfig] = Field(default_factory=dict)
    nodes_mode: str | None = None
    edges_mode: str | None = None
    variables_mode: str | None = None
    speech: JsonObject | None = None


def _branch_config_to_response(branch_cfg: BranchConfig) -> BranchResponse:
    """Конвертирует BranchConfig в BranchResponse."""
    return BranchResponse(
        name=branch_cfg.name,
        description=branch_cfg.description,
        tags=branch_cfg.tags,
        entry=branch_cfg.entry,
        nodes=branch_cfg.nodes,
        edges=branch_cfg.edges if branch_cfg.edges else None,
        variables=branch_cfg.variables,
        nodes_mode=branch_cfg.nodes_mode.value,
        edges_mode=branch_cfg.edges_mode.value,
        variables_mode=branch_cfg.variables_mode.value,
        speech=_speech_to_json(branch_cfg.speech),
    )


def _branch_request_to_config(
    branch_id: str,
    branch_req: BranchRequest,
    existing: BranchConfig | None = None,
) -> BranchConfig:
    """Конвертирует BranchRequest в BranchConfig."""
    def _mode(
        raw: str | None,
        ex: MergeMode | None,
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
    speech_val: FlowSpeechSettings | None = None
    if branch_req.speech is not None:
        speech_val = branch_req.speech
    elif existing is not None:
        speech_val = existing.speech

    branch_nodes = _graph_nodes_payload(branch_req.nodes) if branch_req.nodes is not None else None

    return BranchConfig(
        name=branch_req.name,
        description=branch_req.description,
        tags=branch_req.tags,
        entry=branch_req.entry,
        nodes=branch_nodes,
        edges=branch_req.edges,
        variables=_flow_variable_models(branch_req.variables, f"branches.{branch_id}.variables"),
        nodes_mode=_mode(branch_req.nodes_mode, ex_n, MergeMode.REPLACE),
        edges_mode=_mode(branch_req.edges_mode, ex_e, MergeMode.REPLACE),
        variables_mode=_mode(branch_req.variables_mode, ex_v, MergeMode.MERGE),
        speech=speech_val,
    )


class FlowCreateRequest(BaseModel):
    """Запрос на создание агента"""

    flow_id: str
    name: str
    description: str | None = None
    entry: str
    nodes: dict[str, GraphNodeConfig]
    edges: list[Edge]
    variables: JsonObject = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    branches: dict[str, BranchRequest] = Field(default_factory=dict)
    evaluation: dict[str, TestCaseConfig] | None = None
    triggers: dict[str, TriggerConfig] = Field(default_factory=dict)
    resources: dict[str, ResourceReference] = Field(default_factory=dict)
    store_card_image_url: str | None = None
    speech: FlowSpeechSettings | None = None

    @field_validator("store_card_image_url", mode="before")
    @classmethod
    def _empty_store_card_image_url(cls, value: JsonValue) -> str | None:
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        if not isinstance(value, str):
            raise ValueError("store_card_image_url must be a string")
        return value


class FlowResponse(BaseModel):
    """Ответ с данными агента"""

    flow_id: str
    version: str = ""
    name: str
    description: str | None
    type: FlowType | None = FlowType.LOCAL

    # LOCAL flow
    entry: str | None = None
    nodes: dict[str, JsonObject] | None = None
    edges: list[Edge] | None = None
    variables: dict[str, FlowVariableConfig] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    branches: dict[str, BranchResponse] = Field(default_factory=dict)
    evaluation: dict[str, TestCaseConfig] | None = None
    hidden: bool = False
    has_bundle_update: bool = False

    # Внешний flow (A2A)
    url: str | None = None
    headers: dict[str, str] | None = None
    status: ExternalAgentStatus | None = None
    last_health_check: str | None = None
    agent_card: JsonObject | None = None

    # A2A capabilities
    capabilities: JsonObject = Field(default_factory=lambda: {
        "streaming": True,
        "pushNotifications": True,
    })

    # Триггеры агента
    triggers: dict[str, TriggerConfig] = Field(default_factory=dict)

    # Ресурсы агента
    resources: dict[str, ResourceReference] = Field(default_factory=dict)

    # UI-метаданные (sticky_notes и пр.)
    metadata: JsonObject = Field(default_factory=dict)

    # URL обложки агента (после загрузки файла или из bundle)
    store_card_image_url: str | None = None

    # manual | api | file (bundle в репозитории)
    source: str = "manual"

    speech: JsonObject | None = None


class FlowVoiceSessionQueryResponse(BaseModel):
    """Query-параметры для WS voice-сессии (effective flow + branch speech)."""

    query: dict[str, str]


class ReloadFlowFromBundleResponse(BaseModel):
    flow_id: str
    message: str


class FlowStoreBundleResponse(BaseModel):
    bundle_id: str
    flow_id: str
    name: str
    description: str | None = None
    tags: list[str] = []
    installed: bool


class FlowValidateRequest(BaseModel):
    """Запрос на валидацию агента"""

    nodes: dict[str, GraphNodeConfig]
    edges: list[Edge]
    entry: str
    variables: JsonObject = Field(default_factory=dict)
    flow_id: str | None = None


class ValidationErrorResponse(BaseModel):
    """Ошибка валидации"""

    code: str
    message: str
    severity: str
    node_id: str | None = None
    details: JsonObject | None = None


class FlowValidateResponse(BaseModel):
    """Ответ на валидацию агента"""

    valid: bool
    errors: list[ValidationErrorResponse] = []
    state_keys_used: list[str] = []
    var_keys_used: list[str] = []


class FlowDataflowInspectRequest(BaseModel):
    """Запрос статического анализа state до/после нод редактора."""

    flow_id: str | None = None
    branch_id: str = "default"
    entry: str | None = None
    nodes: dict[str, GraphNodeConfig] = Field(default_factory=dict)
    edges: list[Edge] = Field(default_factory=list)
    variables: dict[str, FlowVariableConfig] = Field(default_factory=dict)
    sample_state: JsonObject | None = None
    observed_runs: JsonObject = Field(default_factory=dict)

    @field_validator("variables", mode="before")
    @classmethod
    def _normalize_variables(
        cls,
        value: JsonValue | Mapping[str, FlowVariableConfig] | None,
    ) -> dict[str, FlowVariableConfig]:
        return _flow_variable_models(value, "variables")


async def _attach_nested_dataflow_for_editor(
    nodes: dict[str, JsonObject],
    container: FlowContainer,
    *,
    seen_flow_ids: set[str] | None = None,
) -> dict[str, JsonObject]:
    """Adds one-level static nested-flow summaries used only by the dataflow inspector."""
    seen = set(seen_flow_ids or set())
    out = copy.deepcopy(nodes)
    for node_id, node in out.items():
        if node.get("type") != "flow":
            continue
        nested_flow_id = node.get("flow_id")
        if not isinstance(nested_flow_id, str) or not nested_flow_id or nested_flow_id in seen:
            continue
        nested_cfg = await container.flow_repository.get(nested_flow_id)
        if nested_cfg is None:
            continue
        raw_nested_branch_id = node.get("branch_id")
        nested_branch_id: str = (
            raw_nested_branch_id
            if isinstance(raw_nested_branch_id, str) and raw_nested_branch_id.strip()
            else "default"
        )
        nested_effective = container.flow_factory.apply_branch(nested_cfg, nested_branch_id)
        nested_graph_nodes = _GRAPH_NODE_MAP_ADAPTER.validate_python(nested_effective.get("nodes") or {})
        nested_nodes = _graph_nodes_payload(nested_graph_nodes)
        nested_edges = _dataflow_edge_models(nested_effective.get("edges"), "nested.edges")
        try:
            nested_nodes = await _inline_tools_in_nodes(copy.deepcopy(nested_nodes), container)
        except Exception as exc:
            logger.warning(
                "flows.dataflow.nested_inline_tools_failed",
                flow_id=nested_flow_id,
                branch_id=nested_branch_id,
                node_id=node_id,
                exception_type=type(exc).__name__,
            )
        nested_nodes = await _attach_nested_dataflow_for_editor(
            nested_nodes,
            container,
            seen_flow_ids={*seen, nested_flow_id},
        )
        node["__dataflow_nested"] = parse_json_object(
            inspect_flow_dataflow(
                flow_id=nested_flow_id,
                branch_id=nested_branch_id,
                entry=nested_effective.get("entry"),
                nodes=_GRAPH_NODE_MAP_ADAPTER.validate_python(nested_nodes),
                edges=nested_edges,
                variables=_flow_variable_models(nested_effective.get("variables"), "nested.variables"),
                sample_state=None,
                observed_runs={},
            ).model_dump_json(),
            "__dataflow_nested",
        )
        out[node_id] = node
    return out


@router.post("/dataflow/inspect")
async def inspect_dataflow(
    request: FlowDataflowInspectRequest,
    container: ContainerDep,
) -> DataflowInspectResult:
    """Возвращает статический snapshot того, какие поля state входят и выходят из каждой ноды."""
    nodes: dict[str, GraphNodeConfig] = request.nodes
    edges: list[Edge] = request.edges
    entry = request.entry
    variables: dict[str, FlowVariableConfig] = request.variables

    if not nodes and request.flow_id:
        flow_cfg = await container.flow_repository.get(request.flow_id)
        if flow_cfg is None:
            raise HTTPException(status_code=404, detail=f"Flow not found: {request.flow_id}")
        effective = container.flow_factory.apply_branch(flow_cfg, request.branch_id or "default")
        nodes = _GRAPH_NODE_MAP_ADAPTER.validate_python(effective.get("nodes") or {})
        edges = _dataflow_edge_models(effective.get("edges"), "flow.edges")
        raw_entry = effective.get("entry")
        entry = raw_entry if isinstance(raw_entry, str) else None
        variables = _flow_variable_models(effective.get("variables"), "flow.variables")

    node_payloads = _graph_nodes_payload(nodes)
    try:
        node_payloads = await _inline_tools_in_nodes(copy.deepcopy(node_payloads), container)
    except Exception as exc:
        logger.warning(
            "flows.dataflow.inline_tools_failed",
            flow_id=request.flow_id,
            branch_id=request.branch_id,
            exception_type=type(exc).__name__,
        )
    node_payloads = await _attach_nested_dataflow_for_editor(node_payloads, container)
    nodes = _GRAPH_NODE_MAP_ADAPTER.validate_python(node_payloads)

    return inspect_flow_dataflow(
        flow_id=request.flow_id,
        branch_id=request.branch_id or "default",
        entry=entry,
        nodes=nodes,
        edges=edges,
        variables=variables,
        sample_state=request.sample_state,
        observed_runs=request.observed_runs,
    )


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
        flow_builder=container.flow_factory.create_validation_flow,
    )

    result = await validator.validate(
        nodes=_graph_nodes_payload(request.nodes),
        edges=[_edge_to_json(edge) for edge in request.edges],
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
    type: FlowType | None = None,
    limit: Annotated[int, Query(ge=1, le=2000, description="Максимум flows")] = 500,
    offset: Annotated[int, Query(ge=0, description="Смещение для пагинации")] = 0,
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

    result: list[FlowResponse] = []
    for f in flows:
        branches_response: dict[str, BranchResponse] = {
            branch_id: _branch_config_to_response(branch_cfg)
            for branch_id, branch_cfg in (f.branches or {}).items()
        }
        if f.type == FlowType.LOCAL:
            result.append(
                FlowResponse(
                    flow_id=f.flow_id,
                    version=f.version,
                    name=f.name,
                    description=f.description,
                    type=f.type,
                    tags=f.tags,
                    hidden=f.hidden,
                    source=f.source,
                    has_bundle_update=bundle_update_flags.get(f.flow_id, False),
                    store_card_image_url=f.store_card_image_url,
                    entry=f.entry,
                    nodes=f.nodes,
                    edges=f.edges,
                    variables=f.variables,
                    branches=branches_response,
                    evaluation=f.evaluation,
                )
            )
        elif f.type == FlowType.EXTERNAL:
            result.append(
                FlowResponse(
                    flow_id=f.flow_id,
                    version=f.version,
                    name=f.name,
                    description=f.description,
                    type=f.type,
                    tags=f.tags,
                    hidden=f.hidden,
                    source=f.source,
                    has_bundle_update=bundle_update_flags.get(f.flow_id, False),
                    store_card_image_url=f.store_card_image_url,
                    url=f.url,
                    headers=f.headers,
                    status=f.status,
                    last_health_check=f.last_health_check.isoformat() if f.last_health_check else None,
                    agent_card=f.agent_card,
                )
            )
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
        registry_data = require_json_object(yaml.safe_load(f) or {}, "registry.yaml")

    try:
        registry_flows = require_json_array(registry_data.get("flows", []), "registry.flows")
    except ValueError as exc:
        raise HTTPException(status_code=500, detail="Registry field 'flows' must be a list") from exc

    result: list[FlowStoreBundleResponse] = []
    for entry in registry_flows:
        if isinstance(entry, str):
            bundle_id = entry
            is_public = True
        elif isinstance(entry, dict):
            bundle_id = entry.get("id")
            raw_public = entry.get("public", False)
            if not isinstance(raw_public, bool):
                raise HTTPException(status_code=500, detail="Registry flow entry field 'public' must be boolean")
            is_public = raw_public
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
            raw_flow = parse_json_object(f.read(), f"bundles.{bundle_id}.flow")

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

        raw_tags = raw_flow.get("tags", [])
        if not isinstance(raw_tags, list):
            raise HTTPException(status_code=500, detail=f"Bundle '{bundle_id}' field 'tags' must be list[str]")
        tags: list[str] = []
        for tag in raw_tags:
            if not isinstance(tag, str):
                raise HTTPException(status_code=500, detail=f"Bundle '{bundle_id}' field 'tags' must be list[str]")
            tags.append(tag)

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
    nodes: dict[str, JsonObject],
    container: FlowContainer
) -> None:
    """Валидирует tool_id в code-нодах при отсутствии inline code."""
    for node_config in nodes.values():
        if node_config.get("type") == "code":
            tool_id = node_config.get("tool_id")
            has_code = "code" in node_config and node_config.get("code")

            if isinstance(tool_id, str) and tool_id and not has_code:
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
    variables = _flow_variable_models(request.variables, "variables")
    request_nodes = _graph_nodes_payload(request.nodes)

    # Валидируем tool_id в tool нодах
    await _validate_tool_nodes(request_nodes, container)

    # Инлайним tools - заменяем tool_id на полные конфиги с кодом ПЕРЕД валидацией
    nodes = await _inline_tools_in_nodes(request_nodes, container)

    # Валидируем ссылки (node_id, tool_id, flow_id) после инлайна
    validator = FlowValidator(
        flow_repository=container.flow_repository,
        tool_repository=container.tool_repository,
        node_repository=container.node_repository,
        flow_builder=container.flow_factory.create_validation_flow,
    )
    validation_result = await validator.validate(
        nodes=nodes,
        edges=[_edge_to_json(edge) for edge in request.edges],
        entry=request.entry,
        variables=request.variables,
    )

    if not validation_result.valid:
        errors = [e.message for e in validation_result.errors]
        raise HTTPException(
            status_code=400,
            detail="; ".join(errors)
        )

    branches_payload = {
        branch_id: _branch_request_to_config(branch_id, branch_req, None)
        for branch_id, branch_req in request.branches.items()
    }

    flow_config = FlowConfig(
        flow_id=request.flow_id,
        name=request.name,
        description=request.description or "",
        entry=request.entry,
        nodes=nodes,  # Инлайненные nodes
        edges=request.edges,
        variables=variables,
        tags=request.tags,
        branches=branches_payload,
        evaluation=request.evaluation,
        source="api",
        store_card_image_url=request.store_card_image_url,
        speech=request.speech,
    )

    _ = await container.flow_repository.set(flow_config)

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
        edges=flow_config.edges,
        variables=flow_config.variables,
        tags=flow_config.tags,
        branches=branches_response,
        evaluation=flow_config.evaluation,
        hidden=flow_config.hidden,
        url=_generate_flow_url(flow_config.flow_id, flow_config.type, flow_config.url),
        source=flow_config.source,
        store_card_image_url=flow_config.store_card_image_url,
        speech=_speech_to_json(flow_config.speech),
    )


@router.get("/{flow_id}/voice-session-query", response_model=FlowVoiceSessionQueryResponse)
async def get_flow_voice_session_query(
    flow_id: str,
    container: ContainerDep,
    branch_id: Annotated[str, Query(description="ID ветки графа для мержа speech")] = "default",
) -> FlowVoiceSessionQueryResponse:
    """Собирает query для Voice WS: STT/TTS/VAD/language из effective_flow_speech_settings.

    Ключи опциональны (только явно заданные в профиле). Дополнительно для ``tts_voice``
    выполняется тот же tier-резолв, что в ``resolve_effective_tts_voice_for_ws``, чтобы URL
    совпадал с ``get_tts_streamer`` при частичном профиле. Остальные поля без значения в
    профиле не заполняются — их на стороне ``apps/voice`` дозаполняет ``create_*_provider`` /
    ``get_tts_streamer`` из company и ``settings.voice``.
    """
    cfg = await container.flow_repository.get(flow_id)
    if cfg is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    eff = effective_flow_speech_settings(cfg, branch_id)
    stt, tts, vad = flow_speech_to_triple_override(eff)
    query = triple_to_voice_ws_query_dict(stt, tts, vad)
    ctx = get_context()
    company_id = ctx.active_company.company_id if ctx and ctx.active_company else None
    resolved_voice = await resolve_effective_tts_voice_for_ws(
        company_id=company_id,
        flow_tts=tts,
    )
    if resolved_voice:
        query["tts_voice"] = str(resolved_voice)
    else:
        _ = query.pop("tts_voice", None)
    logger.info(
        "flows.voice_session_query",
        flow_id=flow_id,
        branch_id=branch_id,
        flow_tts_voice=tts.voice,
        resolved_tts_voice=resolved_voice,
    )
    return FlowVoiceSessionQueryResponse(query=query)


@router.get("/{flow_id}", response_model=FlowResponse)
async def get_flow(
    flow_id: str, container: ContainerDep
) -> FlowResponse:
    """Получает flow по ID."""
    try:
        flow_cfg = await container.flow_repository.get(flow_id)
        if flow_cfg is None:
            raise HTTPException(status_code=404, detail="Flow not found")

        branches_response: dict[str, BranchResponse] = {}
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

        source_value = flow_cfg.source or "manual"
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
            edges=flow_cfg.edges,
            variables=flow_cfg.variables or {},
            tags=flow_cfg.tags or [],
            branches=branches_response,
            evaluation=flow_cfg.evaluation,
            hidden=flow_cfg.hidden,
            url=_generate_flow_url(flow_cfg.flow_id, flow_cfg.type, flow_cfg.url),
            triggers=flow_cfg.triggers,
            resources=flow_cfg.resources or {},
            metadata=flow_cfg.metadata or {},
            source=flow_cfg.source or "manual",
            has_bundle_update=bundle_update,
            store_card_image_url=flow_cfg.store_card_image_url,
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
    _ = await load_tools_to_db(container.tool_repository)

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


@router.post("/{flow_id}/preview-share", response_model=FlowPreviewShareResponse)
async def create_flow_preview_share(
    flow_id: str,
    body: FlowPreviewShareRequest,
    request: Request,
    container: ContainerDep,
) -> FlowPreviewShareResponse:
    """Одноразовая короткая ссылка на гостевую страницу с embed-чатом по flow/ветке."""
    ctx = get_context()
    if ctx is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    if ctx.active_company is None:
        raise HTTPException(status_code=400, detail="Company required")

    company_id = ctx.active_company.company_id

    flow_cfg = await container.flow_repository.get(flow_id)
    if flow_cfg is None:
        raise HTTPException(status_code=404, detail="Flow not found")

    branch_id_raw = (body.branch_id or "").strip()
    if not branch_id_raw:
        branch_id_raw = "default"

    flow_type = flow_cfg.type or FlowType.LOCAL
    if flow_type == FlowType.EXTERNAL:
        branch_id = "default"
    else:
        branch_id = branch_id_raw
        branches = flow_cfg.branches or {}
        if branches and branch_id not in branches:
            raise HTTPException(
                status_code=400,
                detail=f"Branch '{branch_id}' not found",
            )

    flows_base, platform_origin = _preview_share_base_urls(request)

    assistant_title = flow_cfg.name or flow_id
    embed_id = f"pshare_{uuid.uuid4().hex}"

    config = EmbedConfig(
        embed_id=embed_id,
        name=f"[preview] {assistant_title}",
        flow_id=flow_id,
        branch_id=branch_id,
        allowed_origins=[],
        status=EmbedStatus.ACTIVE,
        theme="dark",
        position="bottom-right",
        show_launcher=True,
        show_reasoning=False,
        show_tool_calls=False,
        assistant_title=assistant_title,
        interface_locale="auto",
        voice_enabled=False,
        voice_default_on=False,
        preview_share_link=True,
        guest_max_user_messages=body.guest_max_user_messages,
        created_by=ctx.user.user_id,
    )
    _ = await container.embed_config_repository.set(config)
    mapping = EmbedMapping(embed_id=embed_id, company_id=company_id)
    _ = await container.embed_mapping_repository.set(mapping)

    guest_id = f"flow_preview_{uuid.uuid4().hex}"
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=_FLOW_PREVIEW_SHARE_TTL_SECONDS)
    _ = await ensure_persisted_runtime_user(
        container,
        user_id=guest_id,
        company_id=company_id,
        name="Flow Preview Guest",
        roles=["guest"],
        attrs={
            "kind": "embed_session_guest",
            "embed_id": embed_id,
            "embed_flow_id": flow_id,
            "embed_branch_id": branch_id,
            "issued_by": "flows.preview_share",
            "token_expires_at": expires_at.isoformat(),
        },
    )
    token = get_token_service().create_embed_session_token(
        user_id=guest_id,
        company_id=company_id,
        roles=["guest"],
        expires_in=_FLOW_PREVIEW_SHARE_TTL_SECONDS,
        metadata={
            "embed_id": embed_id,
            "embed_flow_id": flow_id,
            "embed_branch_id": branch_id,
            "allowed_origin": "",
            "issued_by": "flows.preview_share",
        },
    )

    handoff_id = str(uuid.uuid4())
    handoff_payload: JsonObject = {
        "jwt": token,
        "embed_id": embed_id,
        "flow_id": flow_id,
        "branch_id": branch_id,
        "assistant_title": assistant_title,
        "theme": "dark",
        "interface_locale": "auto",
        "flows_base_url": flows_base,
        "platform_ui_origin": platform_origin,
        "company_id": company_id,
    }
    await store_flow_preview_handoff(
        redis=container.redis_client,
        handoff_id=handoff_id,
        payload=handoff_payload,
        ttl_seconds=_FLOW_PREVIEW_SHARE_TTL_SECONDS,
    )

    share_url = await container.short_link_service.mint_flow_preview_embed(handoff_id, expires_at)

    logger.info(
        "flows.preview_share_minted",
        flow_id=flow_id,
        branch_id=branch_id,
        embed_id=embed_id,
        issuer_user_id=ctx.user.user_id,
    )
    return FlowPreviewShareResponse(share_url=share_url)


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

    variables = _flow_variable_models(request.variables, "variables")

    top_nodes = _graph_nodes_payload(request.nodes)
    branches: dict[str, BranchConfig] = {}
    for branch_id, branch_req in request.branches.items():
        ex_cfg = (existing.branches or {}).get(branch_id)
        branches[branch_id] = _branch_request_to_config(branch_id, branch_req, ex_cfg)

    # Инлайним tools - заменяем tool_id на полные конфиги с кодом
    nodes = await _inline_tools_in_nodes(top_nodes, container)

    speech_merged = request.speech if request.speech is not None else existing.speech

    flow_config = FlowConfig(
        flow_id=flow_id,
        name=request.name,
        description=request.description or "",
        entry=request.entry,
        nodes=nodes,  # Инлайненные nodes
        edges=request.edges,
        variables=variables,
        tags=request.tags,
        branches=branches,
        evaluation=request.evaluation,
        source=existing.source,
        triggers=request.triggers,
        resources=request.resources,
        metadata=existing.metadata or {},
        store_card_image_url=request.store_card_image_url,
        speech=speech_merged,
    )

    _ = await container.flow_repository.set(flow_config)

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

    return FlowResponse(
        flow_id=flow_config.flow_id,
        version=flow_config.version or "",
        name=flow_config.name,
        description=flow_config.description,
        type=flow_config.type or FlowType.LOCAL,
        entry=flow_config.entry,
        nodes=flow_config.nodes,
        edges=flow_config.edges,
        variables=flow_config.variables,
        tags=flow_config.tags,
        branches=branches_response,
        evaluation=flow_config.evaluation,
        hidden=flow_config.hidden,
        url=_generate_flow_url(flow_config.flow_id, flow_config.type, flow_config.url),
        triggers=flow_config.triggers,
        resources=flow_config.resources or {},
        metadata=flow_config.metadata or {},
        source=flow_config.source,
        store_card_image_url=flow_config.store_card_image_url,
        speech=_speech_to_json(flow_config.speech),
    )


class BulkDeleteNodesRequest(BaseModel):
    """Запрос на массовое удаление нод с отчисткой связанных рёбер."""

    node_ids: list[str]


class BulkDeleteNodesResponse(BaseModel):
    """Результат массового удаления."""

    flow_id: str
    deleted_node_ids: list[str]
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
    deleted_ids: list[str] = []
    new_nodes: dict[str, JsonObject] = {}
    for node_id, node_value in (existing.nodes or {}).items():
        if node_id in target_ids:
            deleted_ids.append(node_id)
            continue
        new_nodes[node_id] = node_value

    new_edges: list[Edge] = []
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
        metadata=existing.metadata or {},
        store_card_image_url=existing.store_card_image_url,
        speech=existing.speech,
    )
    _ = await container.flow_repository.set(flow_config)

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

    sticky_notes: list[JsonObject] | None = None


class FlowMetadataResponse(BaseModel):
    flow_id: str
    metadata: JsonObject


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

    metadata: JsonObject = dict(existing.metadata or {})
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
        store_card_image_url=existing.store_card_image_url,
        speech=existing.speech,
    )
    _ = await container.flow_repository.set(flow_config)

    return FlowMetadataResponse(flow_id=flow_id, metadata=metadata)


@router.delete("/{flow_id}")
async def delete_flow(
    flow_id: str, container: ContainerDep
) -> JsonObject:
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

    branches_response: dict[str, BranchResponse] = {
        branch_id: _branch_config_to_response(branch_cfg)
        for branch_id, branch_cfg in (version_cfg.branches or {}).items()
    }

    return FlowResponse(
        flow_id=version_cfg.flow_id,
        version=version_cfg.version or "",
        name=version_cfg.name,
        description=version_cfg.description,
        type=version_cfg.type or FlowType.LOCAL,
        entry=version_cfg.entry,
        nodes=version_cfg.nodes or {},
        edges=version_cfg.edges,
        variables=version_cfg.variables or {},
        tags=version_cfg.tags or [],
        branches=branches_response,
        evaluation=version_cfg.evaluation,
        hidden=version_cfg.hidden,
        url=_generate_flow_url(version_cfg.flow_id, version_cfg.type, version_cfg.url),
        triggers=version_cfg.triggers,
        resources=version_cfg.resources or {},
        metadata=version_cfg.metadata or {},
        source=version_cfg.source or "manual",
        store_card_image_url=version_cfg.store_card_image_url,
        speech=_speech_to_json(version_cfg.speech),
    )


@router.post("/{flow_id}/versions/{version}/rollback")
async def rollback_version(
    flow_id: str,
    version: str,
    container: ContainerDep,
) -> JsonObject:
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
