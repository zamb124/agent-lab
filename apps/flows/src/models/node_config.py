"""
Модель NodeConfig - конфигурация ноды.

Zero-Guess Architecture:
- StrictBaseModel (extra='forbid')
- NodeType Enum вместо str
- Input/Output схемы для валидации data flow
"""

from collections.abc import Mapping
from datetime import datetime
from enum import Enum
from typing import ClassVar, Literal, cast

from pydantic import AliasChoices, ConfigDict, Field, RootModel, field_validator, model_validator

from apps.flows.src.constants.execution_limits import (
    get_graph_max_iterations,
    get_node_execution_wall_time_cap_seconds,
)
from core.clients.llm.config import LLMCallConfig, validate_fallback_model_configs
from core.llm_context import LLMContextPatch
from core.models import StrictBaseModel
from core.types import JsonObject, JsonValue
from core.urn import extract_resource_id

from .enums import ChannelType, NodeType
from .exception_absorb_allow import ExceptionAbsorbAllowName
from .external_api import HTTPMethod, ResponseSchema, ResponseType
from .resource import ResourceReference
from .tool_reference import CallParameter, ToolReference


def _parse_config_int(value: JsonValue, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name}: ожидается целое число, получено bool")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            raise ValueError(f"{field_name}: ожидается целое число, получена пустая строка")
        try:
            return int(stripped, 10)
        except ValueError as exc:
            raise ValueError(
                f"{field_name}: ожидается целое число, получено {value!r}"
            ) from exc
    raise ValueError(f"{field_name}: ожидается целое число, получено {type(value).__name__}")


class ReactLoopMode(str, Enum):
    """Режим выхода из ReAct цикла"""

    AUTO = "auto"  # Текст без tool_calls = финальный ответ (по умолчанию)
    EXPLICIT = "explicit"  # Выход только через exit_tool


type LLMCapability = Literal[
    "llm_chat",
    "llm_summarize",
    "llm_format_markdown",
    "llm_codegen",
    "llm_vision",
    "image_gen",
]


class ReactConfig(StrictBaseModel):
    """Конфигурация ReAct цикла для llm_node"""

    loop_mode: ReactLoopMode = Field(
        default=ReactLoopMode.AUTO,
        description="Режим выхода: auto (текст = финал) или explicit (только через exit_tool)"
    )
    exit_tool: str = Field(
        default="finish",
        description="Tool который завершает цикл в режиме explicit"
    )
    max_iterations: int = Field(
        default=10,
        description="Максимум итераций перед принудительным выходом"
    )
    strict: bool = Field(
        default=True,
        description="Строгий режим: True = reminder при тексте без exit_tool, False = текст автозавершает"
    )
    reminder_message: str | None = Field(
        default=None,
        description="Кастомный reminder. По умолчанию: 'Ты не вызвал tool X для завершения...'"
    )


class NodeLLMConfig(LLMCallConfig):
    """LLM настройки конкретной ноды."""

    model: str | None = Field(default=None, description="Модель (если None - из global LLMConfig)")
    fallback_models: list[LLMCallConfig] | None = Field(
        default=None,
        description=(
            "Ordered список полноценных LLM-конфигов fallback-попыток. Каждый элемент имеет "
            "тот же контракт, что основная модель: provider/model/api_key/base_url/temperature/"
            "headers/body и параметры sampling."
        ),
    )
    llm_resource_key: str | None = Field(
        default=None,
        description="Ключ LLM-ресурса в flow/skill/node resources; база конфига, поля override не-None перекрывают",
    )

    @field_validator("fallback_models")
    @classmethod
    def _fallback_models_require_model(
        cls,
        v: list[LLMCallConfig] | None,
    ) -> list[LLMCallConfig] | None:
        return validate_fallback_model_configs(v)


NodeLLMOverride = NodeLLMConfig


class NodeInputMapping(RootModel[dict[str, JsonValue]]):
    """Маппинг входов runtime-ноды: target -> @state/@var expression или JSON-константа."""

    model_config: ClassVar[ConfigDict] = ConfigDict(validate_assignment=True)

    root: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("root")
    @classmethod
    def validate_target_keys(cls, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
        for key in value:
            if not key.strip():
                raise ValueError("input_mapping: target key must be a non-empty string")
            if key != key.strip():
                raise ValueError("input_mapping: target key must not have surrounding whitespace")
        return value


class NodeConfig(StrictBaseModel):
    """
    СТРОГАЯ конфигурация ноды.

    Zero-Guess Architecture:
    - type: NodeType Enum (не str!)
    - description: обязательное поле
    - input_schema, output_schema для валидации data flow

    Поддерживаемые типы:
    - NodeType.LLM_NODE: LLM агент с ReAct циклом
    - NodeType.CODE: выполнение кода (Python, JavaScript, Go)
    - NodeType.FLOW: вложенный flow
    - NodeType.REMOTE_FLOW: внешний flow по A2A
    - NodeType.EXTERNAL_API: вызов HTTP API
    - NodeType.MCP: MCP tool
    - NodeType.HITL_NODE: пауза до оператора очереди
    - NodeType.RESOURCE: нода-ресурс на графе (привязка resources; рантайм pass-through)
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(
        json_schema_extra={"storage_prefix": "node"},
        populate_by_name=True,
        use_enum_values=False,
    )

    # ОБЯЗАТЕЛЬНЫЕ ПОЛЯ
    node_id: str = Field(
        ...,
        validation_alias=AliasChoices("node_id", "tool_id"),
        description="Уникальный идентификатор ноды",
    )
    type: NodeType = Field(..., description="Тип ноды - NodeType Enum")

    name: str = Field(default="", description="Название ноды")

    @field_validator("node_id", mode="before")
    @classmethod
    def validate_node_id(cls, v: JsonValue) -> str:
        """Принимает URN или plain ID, извлекает ID."""
        if not isinstance(v, str):
            raise ValueError(f"node_id: ожидается строка, получено {type(v).__name__}")
        return extract_resource_id(v)

    description: str = Field(default="", description="Описание ноды")

    @field_validator("description", mode="before")
    @classmethod
    def validate_description(cls, v: str | None) -> str:
        """Конвертирует None в пустую строку."""
        return v if v is not None else ""

    @model_validator(mode="after")
    def default_node_name(self) -> "NodeConfig":
        if not self.name.strip():
            object.__setattr__(self, "name", self.node_id)
        return self

    # Data Flow контракт (опционален, но рекомендуется)
    input_schema: dict[str, JsonValue] | None = Field(
        default=None,
        description="JSON Schema входных данных",
    )
    output_schema: dict[str, JsonValue] | None = Field(
        default=None,
        description=(
            "JSON Schema выходных данных ноды. Для llm_node в режиме structured_output "
            "этот же контракт передается в response_format."
        ),
    )
    tags: list[str] = Field(default_factory=list, description="Группы/категории")

    # Для llm_node
    prompt: str | None = Field(default=None, description="Системный промпт")
    tools: list[ToolReference] = Field(
        default_factory=list, description="Список инструментов"
    )
    llm: NodeLLMConfig | None = Field(
        default=None,
        description="LLM настройки ноды (если None - из global config)",
    )
    llm_context: LLMContextPatch | None = Field(
        default=None,
        description=(
            "Патч платформенного контекстного слоя для llm_node. "
            "Для автора обычно достаточно {'profile': 'compact'|'standard'|'agent'}."
        ),
    )
    llm_context_resource_key: str | None = Field(
        default=None,
        description=(
            "Advanced: ключ LLM context resource в flow/skill/node resources. "
            "Если None и context resource ровно один, runtime выберет его автоматически."
        ),
    )
    llm_capability: LLMCapability | None = Field(
        default=None,
        description=(
            "Декларативная capability ноды для company AI overlay. "
            "Если None — считается llm_chat. Если у компании в metadata.ai_providers "
            "задан override этой capability, runtime подменяет provider/model/api_key "
            "перед вызовом LLM. См. core/company_ai/resolver.py."
        ),
    )
    react: ReactConfig | None = Field(
        default=None, description="Конфигурация ReAct цикла (loop_mode, exit_tool)"
    )
    messages_filter: Literal["all", "own"] | list[str] = Field(
        default="all",
        description=(
            "Срез истории для запросов к LLM (полный лог всегда в state.messages): "
            "all — весь лог; own — только сообщения с metadata.node_id равным id этой ноды; "
            "список — только сообщения с metadata.node_id из списка (user и agent по тегу)"
        ),
    )
    incoming_policy: Literal["any", "all"] = Field(
        default="any",
        description=(
            "Fan-in: any — нода ставится в очередь при первом сработавшем входе; "
            "all — ждать все входы с contributes_to_join=true на рёбрах"
        ),
    )

    @field_validator("incoming_policy", mode="before")
    @classmethod
    def validate_incoming_policy(cls, v: JsonValue) -> Literal["any", "all"]:
        if v is None:
            return "any"
        if v not in ("any", "all"):
            raise ValueError(f"incoming_policy: ожидается 'any' или 'all', получено {v!r}")
        return v

    @field_validator("messages_filter", mode="before")
    @classmethod
    def validate_messages_filter(cls, v: JsonValue) -> Literal["all", "own"] | list[str]:
        if v is None:
            return "all"
        if isinstance(v, str):
            if v not in ("all", "own"):
                raise ValueError(
                    f"messages_filter: ожидается 'all' или 'own', получено {v!r}"
                )
            return v
        if isinstance(v, list):
            if not v:
                raise ValueError("messages_filter: список node_id не может быть пустым")
            out: list[str] = []
            for i, item in enumerate(v):
                if not isinstance(item, str) or not item.strip():
                    raise ValueError(
                        f"messages_filter: элемент #{i} должен быть непустой строкой (node_id)"
                    )
                out.append(extract_resource_id(item))
            return out
        raise ValueError(
            f"messages_filter: ожидается 'all', 'own' или список строк, получено {type(v).__name__}"
        )

    input_mapping: NodeInputMapping = Field(
        default_factory=NodeInputMapping,
        description="Маппинг входов ноды: target -> @state:path, @var:path или JSON-константа",
    )
    save_to_messages: bool = Field(default=False, description="Добавлять результат ноды в state.messages")
    message_field: str | None = Field(default=None, description="Поле результата для записи в messages")

    # Structured Output (взаимоисключающе с tools; использует output_schema как контракт ответа)
    structured_output: bool = Field(
        default=False,
        description="Режим structured output вместо tools (response_format json_schema)"
    )
    output_mapping: dict[str, str] | None = Field(
        default=None,
        description="Маппинг полей JSON -> state fields. Если None - поля записываются напрямую"
    )

    # Для code-ноды (inline)
    code: str | None = Field(default=None, description="Inline code for isolated language runners")
    language: str = Field(default="python", description="Язык исполнения code-ноды")
    entrypoint: str | None = Field(default=None, description="Имя entrypoint-функции")
    tool_id: str | None = Field(default=None, description="Ссылка на tool/library id для code-ноды")
    function: str | None = Field(default=None, description="Bundle-функция до инлайна в code")
    args_schema: dict[str, CallParameter] = Field(
        default_factory=dict,
        description="JSON Schema аргументов code-ноды в legacy плоском формате",
    )
    parameters_schema: JsonObject | None = Field(
        default=None,
        description="Полная JSON Schema параметров code-ноды/tool",
    )
    output_key: str | None = Field(default=None, description="Legacy ключ результата ноды")
    llm_node_class: str | None = Field(default=None, description="Кастомный класс llm_node")

    # Для вложенных и удалённых flow
    flow_id: str | None = Field(default=None, description="ID вложенного или внешнего flow")
    branch_id: str = Field(default="default", description="ID ветки вложенного или внешнего flow")
    config: JsonObject | None = Field(default=None, description="Вложенный legacy config блока flow-ноды")

    # Для remote_flow / external_api / mcp
    url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("url", "agent_url"),
        description="URL remote_flow или external_api",
    )
    method: HTTPMethod | None = Field(default=None, description="HTTP метод external_api")
    headers: dict[str, str] = Field(default_factory=dict, description="HTTP headers")
    request_content_type: str | None = Field(default=None, description="Content-Type запроса external_api")
    response_type: ResponseType | None = Field(default=None, description="Тип ответа external_api")
    response_schema: ResponseSchema | None = Field(default=None, description="Схема ответа external_api")
    timeout: float | None = Field(default=None, description="Таймаут external_api в секундах")
    body_template: str | None = Field(default=None, description="JSON body template external_api")
    state_mapping: dict[str, str] = Field(default_factory=dict, description="Маппинг ответа в state")
    server_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("server_id", "mcp_server"),
        description="MCP server id",
    )
    tool_name: str | None = Field(
        default=None,
        validation_alias=AliasChoices("tool_name", "mcp_tool"),
        description="MCP tool name",
    )

    # Для channel-ноды
    channel: ChannelType | None = Field(default=None, description="Тип канала")
    action: str | None = Field(default=None, description="Действие channel-ноды")
    channel_config: JsonObject | None = Field(default=None, description="Параметры channel handler")

    # Декларативные LLM resources ноды
    resources: dict[str, ResourceReference] = Field(
        default_factory=dict,
        description="LLM resources for llm_resource_key/resource islands. Sandbox code uses capabilities instead."
    )

    files: list[dict[str, JsonValue]] = Field(
        default_factory=list,
        description=(
            "Закреплённые файлы ноды (как элементы state.files: original_name, url, "
            "content_type, file_size, file_id). При старте новой сессии агрегируются в state.files."
        ),
    )

    operator_queue_slug: str | None = Field(
        default=None,
        description="Slug очереди оператора (взаимоисключающе с operator_queue_id)",
    )
    operator_queue_id: str | None = Field(
        default=None,
        description="UUID очереди оператора (взаимоисключающе с operator_queue_slug)",
    )
    operator_handoff_mode: Literal["single_reply", "takeover"] | None = Field(
        default=None,
        description="Режим оператора: single_reply — один ответ; takeover — перехват диалога",
    )
    operator_task_title: str | None = Field(
        default=None,
        description="Заголовок задачи; можно переопределить input_mapping.task_title",
    )
    operator_user_message: str | None = Field(
        default=None,
        description="Текст для пользователя; можно переопределить input_mapping.user_facing_message",
    )

    # Общее
    local_variables: dict[str, JsonValue] = Field(
        default_factory=dict, description="Локальные переменные"
    )
    store: dict[str, JsonValue] = Field(default_factory=dict, description="Начальные данные store")
    source: str = Field(default="manual", description="Источник создания")
    created_at: datetime | None = Field(default=None, description="Дата создания")
    updated_at: datetime | None = Field(default=None, description="Дата обновления")

    # Контроль доступа для UI
    public_fields: list[str] | None = Field(
        default=None,
        description="Поля доступные для редактирования в UI. None = все поля доступны"
    )

    exception_as_response: bool = Field(
        default=False,
        description=(
            "Исключения при выполнении ноды или её tools (llm_node) записывать в state.execution_exceptions "
            "и не рвать граф; для llm_node ошибка tool попадает ещё в messages как результат вызова"
        ),
    )
    exception_allow_types: list[ExceptionAbsorbAllowName] = Field(
        default_factory=list,
        description=(
            "Whitelist имён классов исключений (ExceptionAbsorbAllowName). Пустой список при "
            "exception_as_response=True означает любое исключение; иначе только перечисленные типы"
        ),
    )
    node_timeout_seconds: int | None = Field(
        default=None,
        description=(
            "Wall-clock лимит ноды (сек), верх — node_execution_wall_time_cap_seconds; "
            "None = только лимит flow"
        ),
    )
    max_visits_per_run: int | None = Field(
        default=None,
        description=(
            "Максимум заходов в эту ноду за один Flow.run; None — для code действует дефолт платформы, "
            "для прочих типов отдельного лимита нет (только итерации графа)"
        ),
    )

    @field_validator("node_timeout_seconds", mode="before")
    @classmethod
    def validate_node_timeout_seconds(cls, v: JsonValue) -> int | None:
        if v is None:
            return None
        iv = _parse_config_int(v, "node_timeout_seconds")
        if iv < 1:
            raise ValueError(f"node_timeout_seconds: ожидается >= 1, получено {iv}")
        cap = get_node_execution_wall_time_cap_seconds()
        if iv > cap:
            raise ValueError(
                f"node_timeout_seconds: максимум {cap}с (node_execution_wall_time_cap_seconds), получено {iv}"
            )
        return iv

    @field_validator("max_visits_per_run", mode="before")
    @classmethod
    def validate_max_visits_per_run(cls, v: JsonValue) -> int | None:
        if v is None:
            return None
        iv = _parse_config_int(v, "max_visits_per_run")
        if iv < 1:
            raise ValueError(f"max_visits_per_run: ожидается >= 1, получено {iv}")
        cap = get_graph_max_iterations()
        if iv > cap:
            raise ValueError(
                f"max_visits_per_run: максимум {cap} (graph_max_iterations), получено {iv}"
            )
        return iv

    @model_validator(mode="before")
    @classmethod
    def _normalize_legacy_llm_override(cls, data: JsonValue) -> JsonValue:
        if not isinstance(data, dict):
            return data
        raw = cast(Mapping[str, JsonValue], data)
        if "llm_override" not in raw:
            return dict(raw)
        out: JsonObject = dict(raw)
        legacy_llm = out.pop("llm_override", None)
        if legacy_llm not in (None, {}):
            out["llm"] = legacy_llm
        return out

    @model_validator(mode="after")
    def validate_resource_node_excludes_agent_surface(self) -> "NodeConfig":
        if self.type != NodeType.RESOURCE:
            return self
        if self.prompt is not None and str(self.prompt).strip():
            raise ValueError("resource node: prompt must be empty")
        if self.tools:
            raise ValueError("resource node: tools must be empty")
        if self.react is not None:
            raise ValueError("resource node: react is not allowed")
        if self.structured_output:
            raise ValueError("resource node: structured_output must be False")
        if self.llm is not None:
            raise ValueError("resource node: llm is not allowed")
        if self.llm_context is not None or self.llm_context_resource_key is not None:
            raise ValueError("resource node: llm_context is not allowed")
        return self


class GraphNodeConfig(StrictBaseModel):
    """
    Конфигурация экземпляра ноды внутри flow-графа.

    `NodeConfig` описывает библиотечную ноду/шаблон. В graph nodes ключ
    словаря является ID экземпляра на графе, а поле `node_id`, если задано,
    используется как ссылка на библиотечный шаблон при сборке bundle.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(
        populate_by_name=True,
        use_enum_values=False,
    )

    type: NodeType = Field(..., description="Тип runtime-ноды")
    node_id: str | None = Field(default=None, description="ID библиотечной ноды-шаблона")
    name: str = Field(default="", description="Название ноды на графе")
    description: str = Field(default="", description="Описание ноды")

    prompt: str | None = Field(default=None, description="Системный промпт llm_node")
    tools: list[ToolReference | JsonObject | str] = Field(default_factory=list, description="Tools llm_node")
    llm: NodeLLMConfig | None = Field(default=None, description="LLM настройки ноды")
    llm_context: LLMContextPatch | None = Field(default=None, description="Патч контекстного слоя")
    llm_context_resource_key: str | None = Field(default=None, description="Ключ LLM context resource")
    llm_capability: LLMCapability | None = Field(default=None, description="Декларативная LLM capability")
    react: ReactConfig | None = Field(default=None, description="Конфигурация ReAct")
    messages_filter: Literal["all", "own"] | list[str] = Field(default="all")
    incoming_policy: Literal["any", "all"] = Field(default="any")
    structured_output: bool = Field(default=False)
    input_mapping: NodeInputMapping = Field(default_factory=NodeInputMapping)
    output_mapping: dict[str, str] | None = Field(default=None)
    output_schema: dict[str, JsonValue] | None = Field(default=None)

    code: str | None = Field(default=None)
    language: str = Field(default="python")
    entrypoint: str | None = Field(default=None)
    tool_id: str | None = Field(default=None)
    function: str | None = Field(default=None)
    args_schema: dict[str, CallParameter] = Field(default_factory=dict)
    parameters_schema: JsonObject | None = Field(default=None)
    output_key: str | None = Field(default=None)
    llm_node_class: str | None = Field(default=None)

    flow_id: str | None = Field(default=None)
    branch_id: str = Field(default="default")
    config: JsonObject | None = Field(default=None)

    url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("url", "agent_url"),
    )
    method: HTTPMethod | None = Field(default=None)
    headers: dict[str, str] = Field(default_factory=dict)
    request_content_type: str | None = Field(default=None)
    response_type: ResponseType | None = Field(default=None)
    response_schema: ResponseSchema | None = Field(default=None)
    timeout: float | None = Field(default=None)
    body_template: str | None = Field(default=None)
    state_mapping: dict[str, str] = Field(default_factory=dict)
    server_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("server_id", "mcp_server"),
    )
    tool_name: str | None = Field(
        default=None,
        validation_alias=AliasChoices("tool_name", "mcp_tool"),
    )

    channel: ChannelType | None = Field(default=None)
    action: str | None = Field(default=None)
    channel_config: JsonObject | None = Field(default=None)

    local_variables: dict[str, JsonValue] = Field(default_factory=dict)
    store: dict[str, JsonValue] = Field(default_factory=dict)
    resources: dict[str, ResourceReference] = Field(default_factory=dict)
    files: list[dict[str, JsonValue]] = Field(default_factory=list)

    operator_queue_slug: str | None = Field(default=None)
    operator_queue_id: str | None = Field(default=None)
    operator_handoff_mode: Literal["single_reply", "takeover"] | None = Field(default=None)
    operator_task_title: str | None = Field(default=None)
    operator_user_message: str | None = Field(default=None)

    save_to_messages: bool = Field(default=False)
    message_field: str | None = Field(default=None)
    exception_as_response: bool = Field(default=False)
    exception_allow_types: list[ExceptionAbsorbAllowName] = Field(default_factory=list)
    node_timeout_seconds: int | None = Field(default=None)
    max_visits_per_run: int | None = Field(default=None)

    dataflow_nested: JsonObject | None = Field(default=None, alias="__dataflow_nested")
