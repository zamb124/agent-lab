"""
Модель NodeConfig - конфигурация ноды.

Zero-Guess Architecture:
- StrictBaseModel (extra='forbid')
- NodeType Enum вместо str
- Input/Output схемы для валидации data flow
"""

from datetime import datetime
from enum import Enum
from typing import ClassVar, Literal, cast

from pydantic import ConfigDict, Field, JsonValue, field_validator, model_validator

from apps.flows.src.constants.execution_limits import (
    get_graph_max_iterations,
    get_node_execution_wall_time_cap_seconds,
)
from core.clients.llm.config import LLMCallConfig, validate_fallback_model_configs
from core.models import StrictBaseModel
from core.urn import extract_id

from .enums import NodeType
from .exception_absorb_allow import ExceptionAbsorbAllowName
from .resource import ResourceReference
from .tool_reference import ToolReference


def _parse_config_int(value: object, field_name: str) -> int:
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


class NodeLLMOverride(LLMCallConfig):
    """Переопределение LLM настроек для конкретной ноды."""

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
    )

    # ОБЯЗАТЕЛЬНЫЕ ПОЛЯ
    node_id: str = Field(..., description="Уникальный идентификатор ноды")
    type: NodeType = Field(..., description="Тип ноды - NodeType Enum")

    name: str = Field(..., description="Название ноды")

    @field_validator("node_id", mode="before")
    @classmethod
    def validate_node_id(cls, v: object) -> str:
        """Принимает URN или plain ID, извлекает ID."""
        if not isinstance(v, str):
            raise ValueError(f"node_id: ожидается строка, получено {type(v).__name__}")
        return extract_id(v)

    description: str = Field(default="", description="Описание ноды")

    @field_validator("description", mode="before")
    @classmethod
    def validate_description(cls, v: str | None) -> str:
        """Конвертирует None в пустую строку."""
        return v if v is not None else ""

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
    llm_override: NodeLLMOverride | None = Field(
        default=None,
        description="Переопределение LLM настроек (если None - из global config)",
        alias="llm"
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
    def validate_incoming_policy(cls, v: object) -> Literal["any", "all"]:
        if v is None:
            return "any"
        if v not in ("any", "all"):
            raise ValueError(f"incoming_policy: ожидается 'any' или 'all', получено {v!r}")
        return v

    @field_validator("messages_filter", mode="before")
    @classmethod
    def validate_messages_filter(cls, v: object) -> Literal["all", "own"] | list[str]:
        if v is None:
            return "all"
        if isinstance(v, str):
            if v not in ("all", "own"):
                raise ValueError(
                    f"messages_filter: ожидается 'all' или 'own', получено {v!r}"
                )
            return v
        if isinstance(v, list):
            raw_items = cast(list[object], v)
            if not raw_items:
                raise ValueError("messages_filter: список node_id не может быть пустым")
            out: list[str] = []
            for i, item in enumerate(raw_items):
                if not isinstance(item, str) or not item.strip():
                    raise ValueError(
                        f"messages_filter: элемент #{i} должен быть непустой строкой (node_id)"
                    )
                out.append(extract_id(item))
            return out
        raise ValueError(
            f"messages_filter: ожидается 'all', 'own' или список строк, получено {type(v).__name__}"
        )

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
    code: str | None = Field(default=None, description="Inline Python код")

    # Ресурсы ноды
    resources: dict[str, ResourceReference] = Field(
        default_factory=dict,
        description="Ресурсы ноды (переопределяют flow-level)"
    )

    files: list[dict[str, JsonValue]] = Field(
        default_factory=list,
        description=(
            "Закреплённые файлы ноды (как элементы state.files: name, path; опционально "
            "mime_type, size, file_id). При старте новой сессии агрегируются в state.files."
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
    def validate_node_timeout_seconds(cls, v: object) -> int | None:
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
    def validate_max_visits_per_run(cls, v: object) -> int | None:
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
        if self.llm_override is not None:
            raise ValueError("resource node: llm / llm_override is not allowed")
        return self
