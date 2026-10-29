"""HTTP/WS контракты каталога flow: один payload на REST и command-router."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from apps.flows.src.models.branch_contracts import BranchPayload
from apps.flows.src.models.flow_config import (
    BranchConfig,
    Edge,
    ExternalAgentStatus,
    FlowEmployeeConfig,
    FlowType,
    FlowVariableConfig,
)
from apps.flows.src.models.flow_speech_settings import FlowSpeechSettings
from apps.flows.src.models.node_config import GraphNodeConfig
from apps.flows.src.models.resource import ResourceReference
from apps.flows.src.models.trigger_config import TriggerConfig
from core.flow_ui.document import FlowUIDocument
from core.flow_ui.templates import default_chat_document
from core.models.base import StrictBaseModel
from core.types import JsonObject, JsonValue


class FlowCreateRequest(BaseModel):
    flow_id: str
    name: str
    description: str | None = None
    entry: str
    nodes: dict[str, GraphNodeConfig]
    edges: list[Edge]
    variables: JsonObject = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    branches: dict[str, BranchPayload] = Field(default_factory=dict)
    triggers: dict[str, TriggerConfig] = Field(default_factory=dict)
    resources: dict[str, ResourceReference] = Field(default_factory=dict)
    store_card_image_url: str | None = None
    speech: FlowSpeechSettings | None = None
    interface: FlowUIDocument | None = None
    employee: FlowEmployeeConfig = Field(default_factory=FlowEmployeeConfig)

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


class FlowResponse(StrictBaseModel):
    flow_id: str
    version: str = ""
    name: str
    description: str | None
    type: FlowType | None = FlowType.LOCAL
    entry: str | None = None
    nodes: dict[str, JsonObject] | None = None
    edges: list[Edge] | None = None
    variables: dict[str, FlowVariableConfig] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    branches: dict[str, BranchConfig] = Field(default_factory=dict)
    hidden: bool = False
    has_bundle_update: bool = False
    url: str | None = None
    headers: dict[str, str] | None = None
    status: ExternalAgentStatus | None = None
    last_health_check: str | None = None
    agent_card: JsonObject | None = None
    capabilities: JsonObject = Field(
        default_factory=lambda: {
            "streaming": True,
            "pushNotifications": True,
        }
    )
    triggers: dict[str, TriggerConfig] = Field(default_factory=dict)
    resources: dict[str, ResourceReference] = Field(default_factory=dict)
    metadata: JsonObject = Field(default_factory=dict)
    store_card_image_url: str | None = None
    source: str = "manual"
    speech: JsonObject | None = None
    interface: FlowUIDocument = Field(default_factory=default_chat_document)
    employee: FlowEmployeeConfig = Field(default_factory=FlowEmployeeConfig)


class FlowDeletedResponse(StrictBaseModel):
    status: Literal["deleted"]
    flow_id: str


class ReloadFlowFromBundleResponse(StrictBaseModel):
    flow_id: str
    message: str


class FlowStoreBundleResponse(StrictBaseModel):
    bundle_id: str
    flow_id: str
    name: str
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    installed: bool


class FlowValidateRequest(BaseModel):
    nodes: dict[str, GraphNodeConfig]
    edges: list[Edge]
    entry: str
    variables: JsonObject = Field(default_factory=dict)
    flow_id: str | None = None


class ValidationErrorResponse(StrictBaseModel):
    code: str
    message: str
    severity: str
    node_id: str | None = None
    details: JsonObject | None = None


class FlowValidateResponse(StrictBaseModel):
    valid: bool
    errors: list[ValidationErrorResponse] = Field(default_factory=list)
    state_keys_used: list[str] = Field(default_factory=list)
    var_keys_used: list[str] = Field(default_factory=list)


class FlowVersionRollbackResponse(StrictBaseModel):
    status: Literal["success"]
    message: str
    flow_id: str
    version: str


class FlowPreviewShareRequest(StrictBaseModel):
    flow_id: str = ""
    branch_id: str = Field(default="default", min_length=1)
    guest_max_user_messages: int | None = Field(default=None, ge=1, le=500)


class FlowPreviewShareResponse(StrictBaseModel):
    share_url: str


class FlowVoiceSessionQueryRequest(StrictBaseModel):
    flow_id: str = Field(min_length=1)
    branch_id: str = Field(default="default", min_length=1)


class FlowVoiceSessionQueryResponse(StrictBaseModel):
    query: dict[str, str]


class BulkDeleteNodesRequest(StrictBaseModel):
    flow_id: str = ""
    node_ids: list[str] = Field(min_length=1)


class BulkDeleteNodesResponse(StrictBaseModel):
    flow_id: str
    deleted_node_ids: list[str]
    deleted_edge_count: int


class FlowMetadataRequest(StrictBaseModel):
    flow_id: str = ""
    sticky_notes: list[JsonObject] | None = None


class FlowMetadataResponse(StrictBaseModel):
    flow_id: str
    metadata: JsonObject


class FlowNodeTypeCard(StrictBaseModel):
    category: str
    type: str
    name: str
    icon: str
    description: str
    color: str
    inputs: int
    outputs: int
    connector_id: str | None = None


class FlowResourceTypeCard(StrictBaseModel):
    type: str
    name: str
    icon: str
    description: str
    color: str


class FlowExecutionLimits(StrictBaseModel):
    graph_max_iterations: int


FLOW_NODE_TYPE_CARDS: tuple[FlowNodeTypeCard, ...] = (
    FlowNodeTypeCard(
        category="core",
        type="llm_node",
        name="LLM Node",
        icon="llm_node",
        description="LLM и tools (ReAct)",
        color="#f59e0b",
        inputs=1,
        outputs=1,
    ),
    FlowNodeTypeCard(
        category="core",
        type="code",
        name="Code Node",
        icon="code",
        description="Python/JavaScript/TypeScript/Go через isolated runners",
        color="#8b5cf6",
        inputs=1,
        outputs=1,
    ),
    FlowNodeTypeCard(
        category="core",
        type="code_agent",
        name="Code agent",
        icon="code_agent",
        description="Агент из дерева исходников (Documents) + контейнер на ферме",
        color="#7c3aed",
        inputs=1,
        outputs=1,
    ),
    FlowNodeTypeCard(
        category="core",
        type="reflection",
        name="Reflection Gate",
        icon="sparkle",
        description="Typed critic gate без side effects",
        color="#14b8a6",
        inputs=1,
        outputs=1,
    ),
    FlowNodeTypeCard(
        category="tools",
        type="external_api",
        name="External API",
        icon="globe",
        description="HTTP API вызов",
        color="#06b6d4",
        inputs=1,
        outputs=1,
    ),
    FlowNodeTypeCard(
        category="tools",
        type="mcp",
        name="MCP Tool",
        icon="plug",
        description="MCP сервер tool",
        color="#8b5cf6",
        inputs=1,
        outputs=1,
    ),
    FlowNodeTypeCard(
        category="integrations",
        type="remote_flow",
        name="Remote A2A",
        icon="cloud",
        description="Внешний A2A ≥1.0 endpoint (URL + Skill ID)",
        color="#3b82f6",
        inputs=1,
        outputs=1,
    ),
    FlowNodeTypeCard(
        category="integrations",
        type="flow",
        name="Flow Node",
        icon="workflow",
        description="Вложенный flow (subflow)",
        color="#ec4899",
        inputs=1,
        outputs=1,
    ),
    FlowNodeTypeCard(
        category="integrations",
        type="resource",
        name="Resource Node",
        icon="box",
        description="Ресурс на графе (pass-through)",
        color="#a78bfa",
        inputs=1,
        outputs=1,
    ),
    FlowNodeTypeCard(
        category="channels",
        type="channel",
        name="Channel",
        icon="send",
        description="Отправка в каналы (Telegram, Email)",
        color="#99A6F9",
        inputs=1,
        outputs=1,
    ),
    FlowNodeTypeCard(
        category="channels",
        type="hitl_node",
        name="Оператор",
        icon="users",
        description="Пауза до специалиста очереди",
        color="#0ea5e9",
        inputs=1,
        outputs=1,
    ),
)


FLOW_RESOURCE_TYPE_CARDS: tuple[FlowResourceTypeCard, ...] = (
    FlowResourceTypeCard(
        type="llm",
        name="LLM",
        icon="bot",
        description="LLM модель",
        color="#ec4899",
    ),
    FlowResourceTypeCard(
        type="rag",
        name="База знаний",
        icon="database",
        description="База знаний (Namespace) для context layer и тулов rag_*",
        color="#14b8a6",
    ),
    FlowResourceTypeCard(
        type="data_table",
        name="Таблица",
        icon="table",
        description="SQLite-таблица в Documents (file_id), тулы tables_*",
        color="#f59e0b",
    ),
)
