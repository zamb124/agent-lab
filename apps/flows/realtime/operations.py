"""Бизнес-функции каталога Flows: один `op_*` на verb для REST и WS RPC."""

from __future__ import annotations

import copy
import uuid
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pydantic import Field, TypeAdapter, field_validator

from apps.flows.config import get_settings
from apps.flows.di import Di
from apps.flows.src.contracts import RuntimeFlowProtocol
from apps.flows.src.flow_ui.problems import assert_flow_ui_publishable
from apps.flows.src.flow_ui.templates import default_chat_document
from apps.flows.src.models import (
    BranchConfig,
    BranchCreateRequest,
    BranchMutationResponse,
    BranchUpdateRequest,
    DataflowInspectResult,
    Edge,
    FlowConfig,
    FlowToolReference,
    FlowType,
    FlowVariableConfig,
    GraphNodeConfig,
    NodeConfig,
    ToolReference,
    TriggerConfig,
    branch_payload_to_config,
)
from apps.flows.src.models.enums import NodeType
from apps.flows.src.models.exception_absorb_allow import list_exception_absorb_allow_values
from apps.flows.src.models.execution_limits import get_graph_max_iterations
from apps.flows.src.models.flow_api import (
    FLOW_NODE_TYPE_CARDS,
    FLOW_RESOURCE_TYPE_CARDS,
    BulkDeleteNodesRequest,
    BulkDeleteNodesResponse,
    FlowCreateRequest,
    FlowDeletedResponse,
    FlowExecutionLimits,
    FlowMetadataRequest,
    FlowMetadataResponse,
    FlowNodeTypeCard,
    FlowPreviewShareRequest,
    FlowPreviewShareResponse,
    FlowResourceTypeCard,
    FlowResponse,
    FlowStoreBundleResponse,
    FlowValidateRequest,
    FlowValidateResponse,
    FlowVersionRollbackResponse,
    FlowVoiceSessionQueryRequest,
    FlowVoiceSessionQueryResponse,
    ReloadFlowFromBundleResponse,
    ValidationErrorResponse,
)
from apps.flows.src.models.flow_speech_settings import FlowSpeechSettings
from apps.flows.src.services.flow_dataflow_inspector import inspect_flow_dataflow
from apps.flows.src.services.flow_employee_provisioning import (
    remove_flow_employee,
    sync_flow_employee,
)
from apps.flows.src.services.flow_speech_resolve import (
    effective_flow_speech_settings,
    flow_speech_to_triple_override,
    triple_to_voice_ws_query_dict,
)
from apps.flows.src.services.flow_validator import FlowValidator, ValidationSeverity
from apps.flows.src.services.flows_loader import FlowsLoader, load_tools_to_db
from core.ai.runtime import resolve_voice_tts_ws_voice
from core.authz.errors import AuthzDenied
from core.authz.models import AuthzCheckItem, AuthzObject, AuthzSubject
from core.authz.types import AuthzRelation
from core.datasources.models import DatasourceConnectorSpec
from core.errors.boundary import PlatformConflictError, PlatformNotFoundError
from core.events import publish_event_to_user
from core.identity.embed_guest_turns import EMBED_SESSION_ID_METADATA_KEY
from core.identity.flow_preview_handoff import store_flow_preview_handoff
from core.identity.runtime_users import ensure_persisted_runtime_user
from core.logging import get_logger
from core.models.base import StrictBaseModel
from core.models.embed_models import EmbedConfig, EmbedStatus
from core.models.identity_models import User
from core.pagination import ListResponse, OffsetPage
from core.request_scope import CompanyScope, require_company
from core.short_links.service import require_platform_public_base_url
from core.types import (
    JsonArray,
    JsonObject,
    JsonValue,
    parse_json_object,
    parse_yaml_value,
    require_json_array,
    require_json_object,
    require_json_value,
)
from core.ui_document.document import FlowUIDocument
from core.utils.tokens import get_token_service
from core.websocket import (
    EmptyPayload,
    raise_conflict,
    raise_forbidden,
    raise_internal,
    raise_invalid,
    raise_not_found,
)

_FLOW_PREVIEW_SHARE_TTL_SECONDS = 86400

logger = get_logger(__name__)


class FlowsListPayload(StrictBaseModel):
    type: FlowType | None = None
    limit: int = Field(default=500, ge=1, le=2000)
    offset: int = Field(default=0, ge=0)


class FlowsFlowIdPayload(StrictBaseModel):
    flow_id: str = Field(min_length=1)


class FlowsFlowVersionPayload(StrictBaseModel):
    flow_id: str = Field(min_length=1)
    version: str = Field(min_length=1)


class FlowsBranchIdPayload(StrictBaseModel):
    flow_id: str = Field(min_length=1)
    branch_id: str = Field(min_length=1)


class FlowDataflowInspectRequest(StrictBaseModel):
    flow_id: str | None = None
    branch_id: str = Field(default="default", min_length=1)
    entry: str | None = None
    nodes: dict[str, GraphNodeConfig] = Field(default_factory=dict)
    edges: list[Edge] = Field(default_factory=list)
    variables: dict[str, FlowVariableConfig] = Field(default_factory=dict)
    triggers: dict[str, TriggerConfig] = Field(default_factory=dict)
    interface: FlowUIDocument | None = None
    sample_state: JsonObject | None = None
    observed_runs: JsonObject = Field(default_factory=dict)

    @field_validator("variables", mode="before")
    @classmethod
    def _normalize_variables(
        cls,
        value: JsonValue | Mapping[str, FlowVariableConfig] | None,
    ) -> dict[str, FlowVariableConfig]:
        return flow_variable_models(value, "variables")

    @field_validator("triggers", mode="before")
    @classmethod
    def _normalize_triggers(
        cls,
        value: JsonValue | Mapping[str, TriggerConfig] | None,
    ) -> dict[str, TriggerConfig]:
        if value is None:
            raise ValueError("triggers must be an object")
        if not isinstance(value, dict):
            raise ValueError("triggers must be an object")
        out: dict[str, TriggerConfig] = {}
        for trigger_id, trigger in value.items():
            if not trigger_id:
                raise ValueError("triggers keys must be non-empty strings")
            if isinstance(trigger, TriggerConfig):
                out[trigger_id] = trigger
            else:
                out[trigger_id] = TriggerConfig.model_validate(trigger)
        return out


_GRAPH_NODE_MAP_ADAPTER: TypeAdapter[dict[str, GraphNodeConfig]] = TypeAdapter(
    dict[str, GraphNodeConfig]
)









def company_scope() -> CompanyScope:
    return require_company()


def _flow_obj(flow_id: str, company_id: str) -> AuthzObject:
    return AuthzObject.flow(flow_id, company_id=company_id)


async def require_company_member(di: Di) -> CompanyScope:
    scope = company_scope()
    try:
        await di.authz_service.require_can_view(
            AuthzObject.company(scope.company_id),
            user_id=scope.user_id,
        )
    except AuthzDenied as exc:
        raise_forbidden(exc)
    return scope


async def require_view_flow(di: Di, flow_id: str) -> CompanyScope:
    scope = company_scope()
    try:
        await di.authz_service.require_can_view(
            _flow_obj(flow_id, scope.company_id),
            user_id=scope.user_id,
        )
    except AuthzDenied as exc:
        raise_forbidden(exc)
    return scope


async def require_edit_flow(di: Di, flow_id: str) -> CompanyScope:
    scope = company_scope()
    try:
        await di.authz_service.require_can_edit(
            _flow_obj(flow_id, scope.company_id),
            user_id=scope.user_id,
        )
    except AuthzDenied as exc:
        raise_forbidden(exc)
    return scope


async def require_view_tool(di: Di, tool_id: str) -> CompanyScope:
    scope = company_scope()
    try:
        await di.authz_service.require_can_view(
            AuthzObject.tool(tool_id, company_id=scope.company_id),
            user_id=scope.user_id,
        )
    except AuthzDenied as exc:
        raise_forbidden(exc)
    return scope


async def require_view_tool_or_flow(di: Di, object_id: str) -> CompanyScope:
    scope = company_scope()
    allowed = await di.authz_service.batch_check(
        [
            AuthzCheckItem(
                subject=AuthzSubject.user(scope.user_id),
                relation=AuthzRelation.CAN_VIEW,
                obj=AuthzObject.tool(object_id, company_id=scope.company_id),
                correlation_id="tool",
            ),
            AuthzCheckItem(
                subject=AuthzSubject.user(scope.user_id),
                relation=AuthzRelation.CAN_VIEW,
                obj=AuthzObject.flow(object_id, company_id=scope.company_id),
                correlation_id="flow",
            ),
        ]
    )
    if not any(allowed):
        raise_forbidden(AuthzDenied(f"denied user:{scope.user_id} can_view tool|flow:{object_id}"))
    return scope


async def require_share_flow(di: Di, flow_id: str) -> CompanyScope:
    scope = company_scope()
    try:
        await di.authz_service.require_relation(
            AuthzRelation.CAN_SHARE,
            _flow_obj(flow_id, scope.company_id),
            user_id=scope.user_id,
        )
    except AuthzDenied as exc:
        raise_forbidden(exc)
    return scope


async def authorize_reload_from_bundle(di: Di, flow_id: str) -> bool:
    """
    Перезапись существующего flow — ``can_edit``.

    Установка каталожного bundle без FGA tuples — член компании (как POST /flows).
    Если tuples уже есть, а ``can_edit`` нет — 403, без overwrite чужого объекта.
    """
    scope = company_scope()
    flow_obj = _flow_obj(flow_id, scope.company_id)
    if await di.authz_service.can_edit(flow_obj, user_id=scope.user_id):
        return False
    existing_tuples = await di.authz_service.list_tuples(flow_obj)
    if existing_tuples:
        try:
            await di.authz_service.require_can_edit(flow_obj, user_id=scope.user_id)
        except AuthzDenied as exc:
            raise_forbidden(exc)
    _ = await require_company_member(di)
    return True


async def _sync_flow_authz(di: Di, flow_config: FlowConfig) -> None:
    scope = company_scope()
    await di.flow_access_service.sync_flow_saved(
        flow_config,
        company_id=scope.company_id,
        owner_user_id=scope.user_id,
    )


async def persist_flow_with_authz(di: Di, flow_config: FlowConfig) -> None:
    previous = await FlowConfig.current_for_flow(flow_config.flow_id)
    _ = await FlowConfig.create_version(flow_config)
    try:
        await _sync_flow_authz(di, flow_config)
    except Exception:
        if previous is None:
            _ = await FlowConfig.delete_by_flow_id(flow_config.flow_id)
        else:
            _ = await FlowConfig.create_version(previous)
        raise


def assert_interface_publishable(interface: FlowUIDocument) -> None:
    try:
        assert_flow_ui_publishable(interface, get_settings().flow_ui)
    except ValueError as exc:
        raise_invalid(exc)


def assert_branch_interfaces_publishable(branches: Mapping[str, BranchConfig]) -> None:
    for branch_cfg in branches.values():
        if branch_cfg.interface is not None:
            assert_interface_publishable(branch_cfg.interface)


def speech_to_json(settings: FlowSpeechSettings | None) -> JsonObject | None:
    if settings is None:
        return None
    dumped = parse_json_object(settings.model_dump_json(exclude_none=True), "speech")
    if dumped:
        return dumped
    return None


def generate_flow_url(
    flow_id: str, flow_kind: FlowType | None = None, external_url: str | None = None
) -> str:
    if flow_kind == FlowType.EXTERNAL and external_url:
        return external_url
    settings = get_settings()
    return f"https://{settings.server.host}:{settings.server.port}/flows/{flow_id}"


def flow_variable_models(
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


def graph_nodes_payload(nodes: Mapping[str, GraphNodeConfig]) -> dict[str, JsonObject]:
    return {
        node_id: parse_json_object(
            node.model_dump_json(by_alias=True, exclude_none=True), f"nodes.{node_id}"
        )
        for node_id, node in nodes.items()
    }


def edge_to_json(edge: Edge) -> JsonObject:
    return parse_json_object(edge.model_dump_json(by_alias=True), "edge")


def _drop_files_fields(value: JsonValue) -> JsonValue:
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
    payload = parse_json_object(
        flow_cfg.model_dump_json(
            exclude={
                "version",
                "flow_row_id",
                "is_current",
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
                "permission",
                "timeout",
                "max_retries",
                "hidden",
            },
        ),
        "flow.semantic_payload",
    )
    return require_json_object(_drop_files_fields(payload), "flow.semantic_payload")


def _flows_root() -> Path:
    return Path(__file__).resolve().parents[1]


def build_bundle_index(flows_root: Path) -> dict[str, str]:
    registry_path = flows_root / "registry.yaml"
    bundles_dir = flows_root / "bundles"
    if not registry_path.exists():
        raise_internal(RuntimeError(f"Registry not found: {registry_path}"))

    loaded_raw = parse_yaml_value(registry_path.read_text(encoding="utf-8"), "registry.yaml")
    if loaded_raw is None:
        raise_internal(RuntimeError("registry.yaml is empty"))
    registry_data = require_json_object(loaded_raw, "registry.yaml")
    registry_flows = require_json_array(registry_data.get("flows"), "registry.flows")

    flow_to_bundle: dict[str, str] = {}
    for entry in registry_flows:
        if isinstance(entry, str):
            bundle_id = entry
        elif isinstance(entry, dict):
            raw_id = entry.get("id")
            if not isinstance(raw_id, str) or not raw_id:
                raise_internal(RuntimeError("Registry flow entry must include non-empty string 'id'"))
            bundle_id = raw_id
        else:
            raise_internal(RuntimeError("Registry flow entry must be string or object"))

        flow_path = bundles_dir / bundle_id / "flow.json"
        if not flow_path.exists():
            raise_internal(RuntimeError(f"Bundle flow.json not found for '{bundle_id}'"))

        with open(flow_path, "r", encoding="utf-8") as flow_file:
            raw_flow = parse_json_object(flow_file.read(), f"bundles.{bundle_id}.flow")

        flow_id = raw_flow.get("flow_id")
        if not isinstance(flow_id, str) or not flow_id:
            raise_internal(RuntimeError(f"Bundle '{bundle_id}' must define non-empty flow_id"))
        flow_to_bundle[flow_id] = bundle_id
    return flow_to_bundle


async def get_bundle_update_flags(
    flows: list[FlowConfig],
    di: Di,
    flows_root: Path,
) -> dict[str, bool]:
    flags: dict[str, bool] = {flow_cfg.flow_id: False for flow_cfg in flows}
    file_flows = [flow_cfg for flow_cfg in flows if flow_cfg.source == "file"]
    if not file_flows:
        return flags

    flow_to_bundle = build_bundle_index(flows_root)
    loader = FlowsLoader(
        bundles_dir=flows_root / "bundles",
        registry_path=flows_root / "registry.yaml",
        flow_access_service=di.flow_access_service,
        files_service=di.files_service,
    )
    loader.load_registry_yaml()
    for flow_cfg in file_flows:
        bundle_id = flow_to_bundle.get(flow_cfg.flow_id)
        if bundle_id is None:
            raise_internal(RuntimeError(f"bundle_mapping_not_found for flow_id={flow_cfg.flow_id}"))
        bundle_cfg = await loader.build_flow_bundle_config(bundle_id)
        if bundle_cfg is None:
            raise_internal(RuntimeError(f"bundle_config_none for bundle_id={bundle_id}"))
        flags[flow_cfg.flow_id] = _flow_semantic_payload(flow_cfg) != _flow_semantic_payload(
            bundle_cfg
        )
    return flags


async def inline_tools_list(
    tools: Sequence[JsonValue], di: Di
) -> list[JsonValue]:
    inlined: list[JsonValue] = []
    for tool in tools:
        inlined.append(await _inline_single_tool(tool, di))
    return inlined


async def _inline_single_tool(tool: JsonValue, di: Di) -> JsonObject:
    if isinstance(tool, str):
        tool_ref = await ToolReference.get(ToolReference.row_id_for_active_company(tool))
        if tool_ref is not None:
            return parse_json_object(tool_ref.model_dump_json(), "tool")
        node = await NodeConfig.get(NodeConfig.node_row_id_for_active_company(tool))
        if node is not None:
            return await _node_to_inline_tool(node, di)
        flow_cfg = await FlowConfig.current_for_flow(tool)
        if flow_cfg is not None:
            return _flow_config_to_inline_tool(flow_cfg)
        raise_invalid(ValueError(f"Tool '{tool}' not found in library"))

    if not isinstance(tool, dict):
        raise_invalid(ValueError("Tool entry must be a string or object"))

    tool_obj = require_json_object(tool, "tool")
    tool_id = tool_obj.get("tool_id")

    if tool_obj.get("type") == "flow":
        try:
            flow_ref = FlowToolReference.model_validate(tool_obj)
        except ValueError as exc:
            raise_invalid(exc)
        flow_cfg = await FlowConfig.current_for_flow(flow_ref.flow_id)
        if flow_cfg is None:
            raise_invalid(ValueError(f"Flow tool target '{flow_ref.flow_id}' not found"))
        if flow_ref.branch_id != "default" and flow_ref.branch_id not in flow_cfg.branches:
            raise_invalid(
                ValueError(
                    f"Flow tool target '{flow_ref.flow_id}' has no branch "
                    + repr(flow_ref.branch_id)
                )
            )
        return parse_json_object(
            flow_ref.model_dump_json(exclude_none=True),
            f"flow_tool.{flow_ref.tool_id}",
        )

    if tool_obj.get("type") == "llm_node" or tool_obj.get("prompt"):
        nested_tools = tool_obj.get("tools")
        if isinstance(nested_tools, list):
            tool_obj["tools"] = await inline_tools_list(nested_tools, di)
        return tool_obj

    if isinstance(tool_id, str) and tool_id and "code" not in tool_obj:
        tool_ref = await ToolReference.get(ToolReference.row_id_for_active_company(tool_id))
        if tool_ref is not None and tool_ref.code:
            merged = parse_json_object(tool_ref.model_dump_json(), "tool")
            merged.update(tool_obj)
            return merged
    return tool_obj


async def _node_to_inline_tool(node: NodeConfig, di: Di) -> JsonObject:
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
        result["tools"] = await inline_tools_list(tools_list, di)
    return result


def _flow_config_to_inline_tool(flow_cfg: FlowConfig) -> JsonObject:
    flow_ref = FlowToolReference(
        tool_id=flow_cfg.flow_id,
        flow_id=flow_cfg.flow_id,
        name=flow_cfg.name,
        description=flow_cfg.description,
    )
    return parse_json_object(
        flow_ref.model_dump_json(exclude_none=True),
        f"flow_tool.{flow_cfg.flow_id}",
    )


async def inline_tools_in_nodes(
    nodes: dict[str, JsonObject], di: Di
) -> dict[str, JsonObject]:
    for node_id, node_config in nodes.items():
        tools = node_config.get("tools", [])
        if isinstance(tools, list) and tools:
            node_config["tools"] = await inline_tools_list(tools, di)
        if (
            node_config.get("type") == "code"
            and node_config.get("tool_id")
            and "code" not in node_config
        ):
            tool_id = node_config["tool_id"]
            if not isinstance(tool_id, str):
                raise_invalid(ValueError(f"nodes.{node_id}.tool_id must be a string"))
            tool_ref = await ToolReference.get(ToolReference.row_id_for_active_company(tool_id))
            if tool_ref is not None and tool_ref.code:
                node_config["code"] = tool_ref.code
                if tool_ref.parameters_schema:
                    node_config["parameters_schema"] = tool_ref.parameters_schema
                if tool_ref.description and "description" not in node_config:
                    node_config["description"] = tool_ref.description
        nodes[node_id] = node_config
    return nodes


async def _build_validation_flow(
    di: Di,
    config: JsonObject,
) -> RuntimeFlowProtocol:
    return await di.flow_factory.create_validation_flow(
        config,
        tool_registry=di.tool_registry,
    )


async def validate_tool_nodes(nodes: dict[str, JsonObject]) -> None:
    for node_config in nodes.values():
        if node_config.get("type") != "code":
            continue
        tool_id = node_config.get("tool_id")
        has_code = "code" in node_config and node_config.get("code")
        if isinstance(tool_id, str) and tool_id and not has_code:
            tool = await ToolReference.get(ToolReference.row_id_for_active_company(tool_id))
            if tool is not None:
                continue
            node = await NodeConfig.get(NodeConfig.node_row_id_for_active_company(tool_id))
            if node is not None:
                continue
            flow_cfg = await FlowConfig.current_for_flow(tool_id)
            if flow_cfg is None:
                raise_invalid(ValueError(f"Tool '{tool_id}' not found in library"))


def _flow_item_response(
    flow_cfg: FlowConfig,
    *,
    has_bundle_update: bool,
) -> FlowResponse:
    return FlowResponse(
        flow_id=flow_cfg.flow_id,
        version=flow_cfg.version,
        name=flow_cfg.name,
        description=flow_cfg.description,
        type=flow_cfg.type,
        entry=flow_cfg.entry,
        nodes=flow_cfg.nodes,
        edges=flow_cfg.edges,
        variables=flow_cfg.variables,
        tags=flow_cfg.tags,
        branches=flow_cfg.branches,
        hidden=flow_cfg.hidden,
        url=generate_flow_url(flow_cfg.flow_id, flow_cfg.type, flow_cfg.url),
        triggers=flow_cfg.triggers,
        resources=flow_cfg.resources,
        metadata=flow_cfg.metadata,
        source=flow_cfg.source,
        has_bundle_update=has_bundle_update,
        store_card_image_url=flow_cfg.store_card_image_url,
        speech=speech_to_json(flow_cfg.speech),
        interface=flow_cfg.interface,
        employee=flow_cfg.employee,
        headers=flow_cfg.headers,
        status=flow_cfg.status,
        last_health_check=(
            flow_cfg.last_health_check.isoformat() if flow_cfg.last_health_check else None
        ),
        agent_card=flow_cfg.agent_card,
    )


async def op_flows_list(
    payload: FlowsListPayload,
    *,
    user: User,
    di: Di,
) -> OffsetPage[FlowResponse]:
    _ = user
    scope = company_scope()
    index = await FlowConfig.list_current_flow_index_by_created_at_desc()
    if payload.type is not None:
        index = [row for row in index if row.type == payload.type]
    catalog_ids = [row.flow_id for row in index]
    page_ids = await di.flow_access_service.page_viewable_flow_ids(
        catalog_ids,
        user_id=scope.user_id,
        company_id=scope.company_id,
        offset=payload.offset,
        limit=payload.limit,
    )
    total = len(catalog_ids)
    by_id = await FlowConfig.found_current_by_flow_ids(page_ids)
    flows = [by_id[flow_id] for flow_id in page_ids if flow_id in by_id]
    bundle_update_flags = await get_bundle_update_flags(flows, di, _flows_root())
    result: list[FlowResponse] = []
    for flow_cfg in flows:
        result.append(
            _flow_item_response(
                flow_cfg,
                has_bundle_update=bundle_update_flags[flow_cfg.flow_id],
            )
        )
    return OffsetPage[FlowResponse](
        items=result, total=total, limit=payload.limit, offset=payload.offset
    )


async def op_flows_item(
    payload: FlowsFlowIdPayload,
    *,
    user: User,
    di: Di,
) -> FlowResponse:
    _ = user
    _ = await require_view_flow(di, payload.flow_id)
    flow_cfg = await FlowConfig.current_for_flow(payload.flow_id)
    if flow_cfg is None:
        raise_not_found(PlatformNotFoundError("Flow not found"))
    bundle_flags = await get_bundle_update_flags([flow_cfg], di, _flows_root())
    has_bundle_update = bundle_flags[flow_cfg.flow_id]
    return _flow_item_response(
        flow_cfg,
        has_bundle_update=has_bundle_update,
    )


async def op_flows_create(
    payload: FlowCreateRequest,
    *,
    user: User,
    di: Di,
) -> FlowResponse:
    _ = user
    _ = await require_company_member(di)
    try:
        variables = flow_variable_models(payload.variables, "variables")
    except ValueError as exc:
        raise_invalid(exc)
    request_nodes = graph_nodes_payload(payload.nodes)
    await validate_tool_nodes(request_nodes)
    nodes = await inline_tools_in_nodes(request_nodes, di)
    validator = FlowValidator(
        resolve_node_refs=True,
        flow_builder=lambda config: _build_validation_flow(di, config),
    )
    validation_result = await validator.validate(
        nodes=nodes,
        edges=[edge_to_json(edge) for edge in payload.edges],
        entry=payload.entry,
        variables=payload.variables,
    )
    if not validation_result.valid:
        errors = [error.message for error in validation_result.errors]
        raise_invalid(ValueError("; ".join(errors)))

    branches_payload = {
        branch_id: branch_payload_to_config(branch_req)
        for branch_id, branch_req in payload.branches.items()
    }
    interface = payload.interface if payload.interface is not None else default_chat_document()
    assert_interface_publishable(interface)
    assert_branch_interfaces_publishable(branches_payload)
    description = payload.description if payload.description is not None else ""
    flow_config = FlowConfig(
        flow_id=payload.flow_id,
        name=payload.name,
        description=description,
        entry=payload.entry,
        nodes=nodes,
        edges=payload.edges,
        variables=variables,
        tags=payload.tags,
        branches=branches_payload,
        source="api",
        store_card_image_url=payload.store_card_image_url,
        speech=payload.speech,
        interface=interface,
        employee=payload.employee,
    )
    await persist_flow_with_authz(di, flow_config)
    await sync_flow_employee(di.authz_service, di.mail_service, flow_config)
    return _flow_item_response(
        flow_config,
        has_bundle_update=False,
    )


async def op_flows_update(
    payload: FlowCreateRequest,
    *,
    user: User,
    di: Di,
) -> FlowResponse:
    _ = user
    _ = await require_edit_flow(di, payload.flow_id)
    existing = await FlowConfig.current_for_flow(payload.flow_id)
    if existing is None:
        raise_not_found(PlatformNotFoundError("Flow not found"))
    try:
        variables = flow_variable_models(payload.variables, "variables")
    except ValueError as exc:
        raise_invalid(exc)
    branches = {
        branch_id: branch_payload_to_config(branch_req)
        for branch_id, branch_req in payload.branches.items()
    }
    nodes = await inline_tools_in_nodes(graph_nodes_payload(payload.nodes), di)
    speech_merged = payload.speech if payload.speech is not None else existing.speech
    interface_merged = payload.interface if payload.interface is not None else existing.interface
    assert_interface_publishable(interface_merged)
    assert_branch_interfaces_publishable(branches)
    description = payload.description if payload.description is not None else ""
    flow_config = FlowConfig(
        flow_id=payload.flow_id,
        name=payload.name,
        description=description,
        entry=payload.entry,
        nodes=nodes,
        edges=payload.edges,
        variables=variables,
        tags=payload.tags,
        branches=branches,
        source=existing.source,
        triggers=payload.triggers,
        resources=payload.resources,
        metadata=existing.metadata,
        store_card_image_url=payload.store_card_image_url,
        speech=speech_merged,
        interface=interface_merged,
        employee=payload.employee,
    )
    await persist_flow_with_authz(di, flow_config)
    await sync_flow_employee(di.authz_service, di.mail_service, flow_config)
    await publish_event_to_user(
        user_id=company_scope().user_id,
        type="flows/flow/updated",
        payload={"flow_id": payload.flow_id, "version": flow_config.version},
    )
    return _flow_item_response(
        flow_config,
        has_bundle_update=False,
    )


async def op_flows_remove(
    payload: FlowsFlowIdPayload,
    *,
    user: User,
    di: Di,
) -> FlowDeletedResponse:
    _ = user
    scope = await require_edit_flow(di, payload.flow_id)
    existing = await FlowConfig.current_for_flow(payload.flow_id)
    deleted = await FlowConfig.delete_by_flow_id(payload.flow_id)
    if not deleted:
        raise_not_found(PlatformNotFoundError("Flow not found"))
    branch_ids = list(existing.branches.keys()) if existing is not None else []
    await di.flow_access_service.sync_flow_deleted(
        payload.flow_id, company_id=scope.company_id, branch_ids=branch_ids
    )
    await remove_flow_employee(di.authz_service, di.mail_service, payload.flow_id)
    await publish_event_to_user(
        user_id=scope.user_id,
        type="flows/flow/deleted",
        payload={"flow_id": payload.flow_id},
    )
    return FlowDeletedResponse(status="deleted", flow_id=payload.flow_id)


def _store_bundle_tags(raw_tags: JsonValue | None, bundle_id: str) -> list[str]:
    if raw_tags is None:
        return []
    if not isinstance(raw_tags, list):
        raise_internal(RuntimeError(f"Bundle '{bundle_id}' field 'tags' must be list[str]"))
    tags: list[str] = []
    for tag in raw_tags:
        if not isinstance(tag, str):
            raise_internal(RuntimeError(f"Bundle '{bundle_id}' field 'tags' must be list[str]"))
        tags.append(tag)
    return tags


async def op_flows_store_bundles(
    payload: EmptyPayload,
    *,
    user: User,
    di: Di,
) -> ListResponse[FlowStoreBundleResponse]:
    _ = payload
    _ = user
    _ = await require_company_member(di)
    flows_root = _flows_root()
    registry_path = flows_root / "registry.yaml"
    bundles_dir = flows_root / "bundles"
    if not registry_path.exists():
        raise_internal(RuntimeError(f"Registry not found: {registry_path}"))
    loaded_raw = parse_yaml_value(registry_path.read_text(encoding="utf-8"), "registry.yaml")
    if loaded_raw is None:
        raise_internal(RuntimeError("registry.yaml is empty"))
    registry_data = require_json_object(loaded_raw, "registry.yaml")
    registry_flows = require_json_array(registry_data.get("flows"), "registry.flows")
    result: list[FlowStoreBundleResponse] = []
    for entry in registry_flows:
        if isinstance(entry, str):
            bundle_id = entry
            is_public = True
        elif isinstance(entry, dict):
            raw_id = entry.get("id")
            if not isinstance(raw_id, str) or not raw_id:
                raise_internal(RuntimeError("Registry flow entry must include non-empty string 'id'"))
            bundle_id = raw_id
            raw_public = entry.get("public")
            if raw_public is None:
                is_public = False
            elif isinstance(raw_public, bool):
                is_public = raw_public
            else:
                raise_internal(RuntimeError("Registry flow entry field 'public' must be boolean"))
        else:
            raise_internal(RuntimeError("Registry flow entry must be string or object"))
        if not is_public:
            continue
        flow_path = bundles_dir / bundle_id / "flow.json"
        if not flow_path.exists():
            raise_internal(RuntimeError(f"Bundle flow.json not found for '{bundle_id}'"))
        with open(flow_path, "r", encoding="utf-8") as flow_file:
            raw_flow = parse_json_object(flow_file.read(), f"bundles.{bundle_id}.flow")
        hidden_value = raw_flow.get("hidden")
        if hidden_value is None:
            hidden_value = False
        if not isinstance(hidden_value, bool):
            raise_internal(RuntimeError(f"Field 'hidden' must be boolean in bundle '{bundle_id}'"))
        if hidden_value:
            continue
        flow_id = raw_flow.get("flow_id")
        if not isinstance(flow_id, str) or not flow_id:
            raise_internal(RuntimeError(f"Bundle '{bundle_id}' must define non-empty flow_id"))
        name = raw_flow.get("name")
        if not isinstance(name, str) or not name:
            raise_internal(RuntimeError(f"Bundle '{bundle_id}' must define non-empty name"))
        description = raw_flow.get("description")
        if description is not None and not isinstance(description, str):
            raise_internal(RuntimeError(f"Bundle '{bundle_id}' field 'description' must be string"))
        installed = await FlowConfig.current_for_flow(flow_id) is not None
        result.append(
            FlowStoreBundleResponse(
                bundle_id=bundle_id,
                flow_id=flow_id,
                name=name,
                description=description if isinstance(description, str) else None,
                tags=_store_bundle_tags(raw_flow.get("tags"), bundle_id),
                installed=installed,
            )
        )
    return ListResponse[FlowStoreBundleResponse](items=result)


async def op_flows_validate(
    payload: FlowValidateRequest,
    *,
    user: User,
    di: Di,
) -> FlowValidateResponse:
    _ = user
    if payload.flow_id is not None:
        _ = await require_view_flow(di, payload.flow_id)
    else:
        _ = await require_company_member(di)
    validator = FlowValidator(
        resolve_node_refs=True,
        flow_builder=lambda config: _build_validation_flow(di, config),
    )
    result = await validator.validate(
        nodes=graph_nodes_payload(payload.nodes),
        edges=[edge_to_json(edge) for edge in payload.edges],
        entry=payload.entry,
        variables=payload.variables,
        flow_id=payload.flow_id,
    )
    return FlowValidateResponse(
        valid=result.valid,
        errors=[
            ValidationErrorResponse(
                code=error.code,
                message=error.message,
                severity=error.severity.value,
                node_id=error.node_id,
                details=error.details,
            )
            for error in result.errors
        ],
        state_keys_used=list(result.state_keys_used),
        var_keys_used=list(result.var_keys_used),
    )


async def op_flows_reload_from_bundle(
    payload: FlowsFlowIdPayload,
    *,
    user: User,
    di: Di,
) -> ReloadFlowFromBundleResponse:
    _ = user
    catalog_install = await authorize_reload_from_bundle(di, payload.flow_id)
    _ = await load_tools_to_db(
        flow_access_service=di.flow_access_service,
    )
    flows_root = _flows_root()
    loader = FlowsLoader(
        bundles_dir=flows_root / "bundles",
        registry_path=flows_root / "registry.yaml",
        flow_access_service=di.flow_access_service,
        files_service=di.files_service,
        authz_service=di.authz_service,
        mail_service=di.mail_service,
    )
    try:
        loaded_id = await loader.reload_flow_bundle(payload.flow_id)
    except ValueError as exc:
        msg = str(exc).lower()
        if "не найден" in msg or "not found" in msg:
            if catalog_install:
                raise_forbidden(exc)
            raise_not_found(exc)
        raise_invalid(exc)
    reloaded_cfg = await FlowConfig.current_for_flow(loaded_id)
    if reloaded_cfg is None:
        raise_internal(RuntimeError(f"Flow '{loaded_id}' missing after reload-from-bundle"))
    await publish_event_to_user(
        user_id=company_scope().user_id,
        type="flows/flow/updated",
        payload={"flow_id": loaded_id, "version": reloaded_cfg.version},
    )
    return ReloadFlowFromBundleResponse(
        flow_id=loaded_id,
        message=f"Flow '{loaded_id}' перезагружен из bundle",
    )


async def op_flows_versions_list(
    payload: FlowsFlowIdPayload,
    *,
    user: User,
    di: Di,
) -> ListResponse[str]:
    _ = user
    _ = await require_view_flow(di, payload.flow_id)
    versions = await FlowConfig.list_version_strings_by_version_desc(payload.flow_id)
    return ListResponse[str](items=versions)


async def op_flows_version_item(
    payload: FlowsFlowVersionPayload,
    *,
    user: User,
    di: Di,
) -> FlowResponse:
    _ = user
    _ = await require_view_flow(di, payload.flow_id)
    version_cfg = await FlowConfig.by_flow_id_and_version(payload.flow_id, payload.version)
    if version_cfg is None:
        raise_not_found(PlatformNotFoundError("Version not found"))
    return _flow_item_response(
        version_cfg,
        has_bundle_update=False,
    )


async def op_flows_version_rollback(
    payload: FlowsFlowVersionPayload,
    *,
    user: User,
    di: Di,
) -> FlowVersionRollbackResponse:
    _ = user
    _ = await require_edit_flow(di, payload.flow_id)
    success = await FlowConfig.rollback_to_version(payload.flow_id, payload.version)
    if not success:
        raise_not_found(PlatformNotFoundError("Version not found"))
    return FlowVersionRollbackResponse(
        status="success",
        message=f"Flow '{payload.flow_id}' rolled back to version {payload.version}",
        flow_id=payload.flow_id,
        version=payload.version,
    )


def _require_path_id(value: str, field_name: str) -> str:
    if value == "":
        raise_invalid(ValueError(f"{field_name} is required"))
    return value


async def _validate_merged_branch(
    di: Di,
    flow_config: FlowConfig,
    branch_id: str,
) -> None:
    assert_branch_interfaces_publishable(flow_config.branches)
    effective = di.flow_factory.apply_branch(flow_config, branch_id)
    entry = effective["entry"]
    if entry is None:
        raise_invalid(ValueError(f"Flow '{flow_config.flow_id}' has no entry"))
    validator = FlowValidator(
        resolve_node_refs=True,
        flow_builder=lambda config: _build_validation_flow(di, config),
    )
    validation_result = await validator.validate(
        nodes=effective["nodes"],
        edges=[
            require_json_object(
                edge.model_dump(mode="json", by_alias=True),
                "effective.edges[]",
            )
            for edge in effective["edges"]
        ],
        entry=entry,
        variables=effective["variables"],
        flow_id=flow_config.flow_id,
    )
    if not validation_result.valid:
        errors = [
            error.message
            for error in validation_result.errors
            if error.severity == ValidationSeverity.ERROR
        ]
        raise_invalid(ValueError(f"branch validation failed: {'; '.join(errors)}"))


async def op_flows_branch_create(
    payload: BranchCreateRequest,
    *,
    user: User,
    di: Di,
) -> BranchMutationResponse:
    _ = user
    flow_id = _require_path_id(payload.flow_id, "flow_id")
    _ = await require_edit_flow(di, flow_id)
    flow_config = await FlowConfig.current_for_flow(flow_id)
    if flow_config is None:
        raise_not_found(PlatformNotFoundError(f"Flow '{flow_id}' not found"))
    if payload.branch_id in flow_config.branches:
        raise_conflict(PlatformConflictError(f"branch {payload.branch_id!r} already exists"))
    candidate = flow_config.model_copy(deep=True)
    candidate.branches[payload.branch_id] = branch_payload_to_config(payload)
    await _validate_merged_branch(di, candidate, payload.branch_id)
    await persist_flow_with_authz(di, candidate)
    await publish_event_to_user(
        user_id=company_scope().user_id,
        type="flows/branch/created",
        payload={"flow_id": flow_id, "branch_id": payload.branch_id},
    )
    return BranchMutationResponse(
        status="success",
        message=f"Ветка '{payload.branch_id}' создана",
        branch_id=payload.branch_id,
    )


async def op_flows_branch_update(
    payload: BranchUpdateRequest,
    *,
    user: User,
    di: Di,
) -> BranchMutationResponse:
    _ = user
    flow_id = _require_path_id(payload.flow_id, "flow_id")
    branch_id = _require_path_id(payload.branch_id, "branch_id")
    _ = await require_edit_flow(di, flow_id)
    flow_config = await FlowConfig.current_for_flow(flow_id)
    if flow_config is None:
        raise_not_found(PlatformNotFoundError(f"Flow '{flow_id}' not found"))
    if branch_id not in flow_config.branches:
        raise_not_found(PlatformNotFoundError(f"Branch '{branch_id}' not found. Use POST to create."))
    candidate = flow_config.model_copy(deep=True)
    candidate.branches[branch_id] = branch_payload_to_config(payload)
    await _validate_merged_branch(di, candidate, branch_id)
    await persist_flow_with_authz(di, candidate)
    await publish_event_to_user(
        user_id=company_scope().user_id,
        type="flows/branch/updated",
        payload={"flow_id": flow_id, "branch_id": branch_id},
    )
    return BranchMutationResponse(
        status="success",
        message=f"Ветка '{branch_id}' обновлена",
        branch_id=branch_id,
    )


async def op_flows_branch_remove(
    payload: FlowsBranchIdPayload,
    *,
    user: User,
    di: Di,
) -> BranchMutationResponse:
    _ = user
    scope = await require_edit_flow(di, payload.flow_id)
    flow_config = await FlowConfig.current_for_flow(payload.flow_id)
    if flow_config is None:
        raise_not_found(PlatformNotFoundError(f"Flow '{payload.flow_id}' not found"))
    if payload.branch_id not in flow_config.branches:
        raise_not_found(PlatformNotFoundError(f"branch {payload.branch_id!r} not found"))
    candidate = flow_config.model_copy(deep=True)
    del candidate.branches[payload.branch_id]
    _ = await FlowConfig.create_version(candidate)
    try:
        await di.flow_access_service.sync_branch_deleted(
            payload.flow_id, payload.branch_id, company_id=scope.company_id
        )
        await _sync_flow_authz(di, candidate)
    except Exception:
        _ = await FlowConfig.create_version(flow_config)
        raise
    await publish_event_to_user(
        user_id=scope.user_id,
        type="flows/branch/deleted",
        payload={"flow_id": payload.flow_id, "branch_id": payload.branch_id},
    )
    return BranchMutationResponse(
        status="success",
        message=f"Ветка '{payload.branch_id}' удалена",
        branch_id=payload.branch_id,
    )


def _preview_share_base_urls() -> tuple[str, str]:
    base = require_platform_public_base_url().rstrip("/")
    return f"{base}/flows", base


async def op_flows_voice_session_query(
    payload: FlowVoiceSessionQueryRequest,
    *,
    user: User,
    di: Di,
) -> FlowVoiceSessionQueryResponse:
    _ = user
    scope = await require_view_flow(di, payload.flow_id)
    cfg = await FlowConfig.current_for_flow(payload.flow_id)
    if cfg is None:
        raise_not_found(PlatformNotFoundError(f"Flow '{payload.flow_id}' not found"))
    branch_id = _require_path_id(payload.branch_id, "branch_id")
    eff = effective_flow_speech_settings(cfg, branch_id)
    stt, tts, vad = flow_speech_to_triple_override(eff)
    query = triple_to_voice_ws_query_dict(stt, tts, vad)
    resolved_voice = await resolve_voice_tts_ws_voice(
        company_id=scope.company_id,
        flow_tts=tts,
    )
    if resolved_voice is not None:
        query["tts_voice"] = str(resolved_voice)
    elif "tts_voice" in query:
        del query["tts_voice"]
    logger.info(
        "flows.voice_session_query",
        flow_id=payload.flow_id,
        branch_id=branch_id,
        flow_tts_voice=tts.voice,
        resolved_tts_voice=resolved_voice,
    )
    return FlowVoiceSessionQueryResponse(query=query)


async def op_flows_preview_share(
    payload: FlowPreviewShareRequest,
    *,
    user: User,
    di: Di,
) -> FlowPreviewShareResponse:
    _ = user
    flow_id = _require_path_id(payload.flow_id, "flow_id")
    scope = await require_share_flow(di, flow_id)
    flow_cfg = await FlowConfig.current_for_flow(flow_id)
    if flow_cfg is None:
        raise_not_found(PlatformNotFoundError(f"Flow '{flow_id}' not found"))
    branch_id = _require_path_id(payload.branch_id, "branch_id")
    if flow_cfg.type == FlowType.EXTERNAL:
        branch_id = "default"
    elif flow_cfg.branches and branch_id not in flow_cfg.branches:
        raise_invalid(ValueError(f"Branch '{branch_id}' not found"))

    flows_base, platform_origin = _preview_share_base_urls()
    assistant_title = flow_cfg.name
    embed_id = f"pshare_{uuid.uuid4().hex}"
    config = EmbedConfig(
        embed_id=embed_id,
        company_id=scope.company_id,
        name=f"[preview] {assistant_title}",
        flow_id=flow_id,
        branch_id=branch_id,
        allowed_origins=[],
        status=EmbedStatus.ACTIVE,
        presentation="page",
        theme="dark",
        position="bottom-right",
        show_launcher=False,
        assistant_title=assistant_title,
        interface_locale="auto",
        voice_enabled=False,
        voice_default_on=False,
        preview_share_link=True,
        guest_max_user_messages=payload.guest_max_user_messages,
        created_by=scope.user_id,
    )
    _ = await EmbedConfig.set(config)

    guest_id = f"flow_preview_{uuid.uuid4().hex}"
    embed_session_id = f"embsess_{uuid.uuid4().hex}"
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=_FLOW_PREVIEW_SHARE_TTL_SECONDS)
    _ = await ensure_persisted_runtime_user(
        di.authz_service,
        user_id=guest_id,
        company_id=scope.company_id,
        name="Flow Preview Guest",
        roles=["guest"],
        attributes={
            "kind": "embed_session_guest",
            "embed_id": embed_id,
            "embed_flow_id": flow_id,
            "embed_branch_id": branch_id,
            "issued_by": "flows.preview_share",
            "token_expires_at": expires_at.isoformat(),
            EMBED_SESSION_ID_METADATA_KEY: embed_session_id,
        },
    )
    token = get_token_service().create_embed_session_token(
        user_id=guest_id,
        company_id=scope.company_id,
        roles=["guest"],
        expires_in=_FLOW_PREVIEW_SHARE_TTL_SECONDS,
        metadata={
            "embed_id": embed_id,
            "embed_flow_id": flow_id,
            "embed_branch_id": branch_id,
            "allowed_origin": "",
            "issued_by": "flows.preview_share",
            EMBED_SESSION_ID_METADATA_KEY: embed_session_id,
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
        "company_id": scope.company_id,
    }
    await store_flow_preview_handoff(
        redis=di.redis_client,
        handoff_id=handoff_id,
        payload=handoff_payload,
        ttl_seconds=_FLOW_PREVIEW_SHARE_TTL_SECONDS,
    )
    share_url = await di.short_link_service.mint_flow_preview_embed(handoff_id, expires_at)
    logger.info(
        "flows.preview_share_minted",
        flow_id=flow_id,
        branch_id=branch_id,
        embed_id=embed_id,
        issuer_user_id=scope.user_id,
    )
    return FlowPreviewShareResponse(share_url=share_url)


async def op_flows_nodes_bulk_delete(
    payload: BulkDeleteNodesRequest,
    *,
    user: User,
    di: Di,
) -> BulkDeleteNodesResponse:
    _ = user
    flow_id = _require_path_id(payload.flow_id, "flow_id")
    scope = await require_edit_flow(di, flow_id)
    existing = await FlowConfig.current_for_flow(flow_id)
    if existing is None:
        raise_not_found(PlatformNotFoundError(f"Flow '{flow_id}' not found"))
    nodes = existing.nodes
    if nodes is None:
        raise_invalid(ValueError("flow.nodes is required"))
    target_ids = set(payload.node_ids)
    deleted_ids = [node_id for node_id in nodes if node_id in target_ids]
    new_nodes = {
        node_id: node_value for node_id, node_value in nodes.items() if node_id not in target_ids
    }
    new_edges: list[Edge] = []
    deleted_edge_count = 0
    for edge in existing.edges:
        if edge.from_node in target_ids or edge.to_node in target_ids:
            deleted_edge_count += 1
            continue
        new_edges.append(edge)
    new_entry = existing.entry if existing.entry not in target_ids else None
    updated = existing.model_copy(
        update={"nodes": new_nodes, "edges": new_edges, "entry": new_entry}
    )
    _ = await persist_flow_with_authz(di, updated)
    await publish_event_to_user(
        user_id=scope.user_id,
        type="flows/flow/updated",
        payload={"flow_id": flow_id, "version": updated.version},
    )
    return BulkDeleteNodesResponse(
        flow_id=flow_id,
        deleted_node_ids=deleted_ids,
        deleted_edge_count=deleted_edge_count,
    )


async def op_flows_metadata_update(
    payload: FlowMetadataRequest,
    *,
    user: User,
    di: Di,
) -> FlowMetadataResponse:
    _ = user
    flow_id = _require_path_id(payload.flow_id, "flow_id")
    _ = await require_edit_flow(di, flow_id)
    existing = await FlowConfig.current_for_flow(flow_id)
    if existing is None:
        raise_not_found(PlatformNotFoundError(f"Flow '{flow_id}' not found"))
    metadata: JsonObject = dict(existing.metadata)
    if payload.sticky_notes is not None:
        metadata["sticky_notes"] = payload.sticky_notes
    updated = existing.model_copy(update={"metadata": metadata})
    _ = await persist_flow_with_authz(di, updated)
    return FlowMetadataResponse(flow_id=flow_id, metadata=metadata)


async def _attach_nested_dataflow_for_editor(
    nodes: dict[str, JsonObject],
    di: Di,
    *,
    seen_flow_ids: set[str],
) -> dict[str, JsonObject]:
    out = copy.deepcopy(nodes)
    for node_id, node in out.items():
        if node.get("type") != "flow":
            continue
        nested_flow_id = node.get("flow_id")
        if not isinstance(nested_flow_id, str) or nested_flow_id == "":
            raise_invalid(ValueError(f"nodes.{node_id}.flow_id is required"))
        if nested_flow_id in seen_flow_ids:
            continue
        nested_cfg = await FlowConfig.current_for_flow(nested_flow_id)
        if nested_cfg is None:
            raise_not_found(PlatformNotFoundError(f"Flow '{nested_flow_id}' not found"))
        raw_nested_branch_id = node.get("branch_id")
        if raw_nested_branch_id is None:
            nested_branch_id = "default"
        elif not isinstance(raw_nested_branch_id, str) or raw_nested_branch_id.strip() == "":
            raise_invalid(ValueError(f"nodes.{node_id}.branch_id must be a non-empty string"))
        else:
            nested_branch_id = raw_nested_branch_id
        nested_effective = di.flow_factory.apply_branch(nested_cfg, nested_branch_id)
        nested_graph_nodes = _GRAPH_NODE_MAP_ADAPTER.validate_python(nested_effective["nodes"])
        nested_nodes = graph_nodes_payload(nested_graph_nodes)
        nested_nodes = await inline_tools_in_nodes(copy.deepcopy(nested_nodes), di)
        nested_nodes = await _attach_nested_dataflow_for_editor(
            nested_nodes,
            di,
            seen_flow_ids={*seen_flow_ids, nested_flow_id},
        )
        node["__dataflow_nested"] = parse_json_object(
            inspect_flow_dataflow(
                flow_id=nested_flow_id,
                branch_id=nested_branch_id,
                entry=nested_effective["entry"],
                nodes=_GRAPH_NODE_MAP_ADAPTER.validate_python(nested_nodes),
                edges=nested_effective["edges"],
                variables=flow_variable_models(nested_effective["variables"], "nested.variables"),
                sample_state=None,
                observed_runs={},
            ).model_dump_json(),
            "__dataflow_nested",
        )
        out[node_id] = node
    return out


async def op_flows_dataflow_inspect(
    payload: FlowDataflowInspectRequest,
    *,
    user: User,
    di: Di,
) -> DataflowInspectResult:
    _ = user
    nodes = payload.nodes
    edges = payload.edges
    entry = payload.entry
    variables = payload.variables
    triggers = payload.triggers
    interface = payload.interface
    if not nodes:
        if payload.flow_id is None:
            raise_invalid(ValueError("nodes or flow_id is required"))
        _ = await require_view_flow(di, payload.flow_id)
        flow_cfg = await FlowConfig.current_for_flow(payload.flow_id)
        if flow_cfg is None:
            raise_not_found(PlatformNotFoundError(f"Flow '{payload.flow_id}' not found"))
        effective = di.flow_factory.apply_branch(flow_cfg, payload.branch_id)
        nodes = _GRAPH_NODE_MAP_ADAPTER.validate_python(effective["nodes"])
        edges = effective["edges"]
        entry = effective["entry"]
        variables = flow_variable_models(effective["variables"], "flow.variables")
        triggers = flow_cfg.triggers
        if interface is None:
            interface = flow_cfg.interface_for_branch(payload.branch_id)

    node_payloads = graph_nodes_payload(nodes)
    node_payloads = await inline_tools_in_nodes(copy.deepcopy(node_payloads), di)
    node_payloads = await _attach_nested_dataflow_for_editor(
        node_payloads, di, seen_flow_ids=set()
    )
    nodes = _GRAPH_NODE_MAP_ADAPTER.validate_python(node_payloads)
    return inspect_flow_dataflow(
        flow_id=payload.flow_id,
        branch_id=payload.branch_id,
        entry=entry,
        nodes=nodes,
        edges=edges,
        variables=variables,
        sample_state=payload.sample_state,
        observed_runs=payload.observed_runs,
        triggers=triggers,
        interface=interface,
    )


def _datasource_palette_card(spec: DatasourceConnectorSpec) -> FlowNodeTypeCard:
    return FlowNodeTypeCard(
        category="sources",
        type=NodeType.DATASOURCE.value,
        name=spec.name,
        icon=spec.icon,
        description=spec.description,
        color="#14b8a6",
        inputs=1,
        outputs=1,
        connector_id=spec.connector_id,
    )


async def op_flows_node_types(
    payload: EmptyPayload,
    *,
    user: User,
    di: Di,
) -> ListResponse[FlowNodeTypeCard]:
    _ = payload
    _ = user
    _ = await require_company_member(di)
    cards = list(FLOW_NODE_TYPE_CARDS)
    for spec in await di.datasource_service.list_connectors():
        cards.append(_datasource_palette_card(spec))
    return ListResponse(items=cards)


async def op_flows_resource_types(
    payload: EmptyPayload,
    *,
    user: User,
    di: Di,
) -> ListResponse[FlowResourceTypeCard]:
    _ = payload
    _ = user
    _ = await require_company_member(di)
    return ListResponse(items=list(FLOW_RESOURCE_TYPE_CARDS))


async def op_flows_exception_absorb_allow_names(
    payload: EmptyPayload,
    *,
    user: User,
    di: Di,
) -> ListResponse[str]:
    _ = payload
    _ = user
    _ = await require_company_member(di)
    return ListResponse(items=list_exception_absorb_allow_values())


async def op_flows_execution_limits(
    payload: EmptyPayload,
    *,
    user: User,
    di: Di,
) -> FlowExecutionLimits:
    _ = payload
    _ = user
    _ = await require_company_member(di)
    return FlowExecutionLimits(graph_max_iterations=get_graph_max_iterations())
