"""
Модель NodeConfig - конфигурация ноды.

Zero-Guess Architecture:
- StrictBaseModel (extra='forbid')
- NodeType Enum вместо str
- Input/Output схемы для валидации data flow
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from core.clients.llm.model_routing import split_provider_prefixed_model
from core.models import StrictBaseModel
from core.urn import extract_id
from apps.flows.src.constants.execution_limits import (
    get_graph_max_iterations,
    get_node_execution_wall_time_cap_seconds,
)
from .enums import NodeType
from .exception_absorb_allow import ExceptionAbsorbAllowName
from .tool_reference import ToolReference
from .resource import ResourceReference


class ReactLoopMode(str, Enum):
    """Режим выхода из ReAct цикла"""
    
    AUTO = "auto"  # Текст без tool_calls = финальный ответ (по умолчанию)
    EXPLICIT = "explicit"  # Выход только через exit_tool


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
    reminder_message: Optional[str] = Field(
        default=None,
        description="Кастомный reminder. По умолчанию: 'Ты не вызвал tool X для завершения...'"
    )


class NodeLLMOverride(StrictBaseModel):
    """Переопределение LLM настроек для конкретной ноды."""

    model: Optional[str] = Field(default=None, description="Модель (если None - из global LLMConfig)")
    temperature: Optional[float] = Field(default=None, description="Температура генерации")
    max_tokens: Optional[int] = Field(default=None, description="Максимум токенов в ответе")
    provider: Optional[str] = Field(default=None, description="Провайдер: openai, openrouter, bothub, provider_litserve, yandex")
    api_key: Optional[str] = Field(default=None, description="API ключ (напрямую или @var:my_key)")
    folder_id: Optional[str] = Field(
        default=None,
        description="Yandex Cloud folder id (каталог); для провайдера yandex с собственным api_key обязателен, если не задан llm.yandex.folder_id",
    )
    base_url: Optional[str] = Field(default=None, description="Base URL провайдера (напрямую или @var:my_url)")
    top_p: Optional[float] = Field(default=None, description="Nucleus sampling top_p")
    top_k: Optional[int] = Field(default=None, description="Top-K семплирование")
    frequency_penalty: Optional[float] = Field(default=None, description="Штраф за частоту токенов")
    presence_penalty: Optional[float] = Field(default=None, description="Штраф за присутствие токенов")
    seed: Optional[int] = Field(default=None, description="Seed для детерминизма")
    reasoning_effort: Optional[
        Literal["none", "minimal", "low", "medium", "high", "xhigh"]
    ] = Field(default=None, description="Усилие reasoning (OpenAI-совместимые модели)")
    extra_request_body: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Доп. поля тела POST /chat/completions; мерж последним, перекрывает поля рантайма",
    )
    extra_request_headers: Optional[Dict[str, str]] = Field(
        default=None,
        description=(
            "Доп. HTTP заголовки; мерж последним, перекрывает в т.ч. Authorization и default_headers провайдера"
        ),
    )
    llm_resource_key: Optional[str] = Field(
        default=None,
        description="Ключ LLM-ресурса в flow/skill/node resources; база конфига, поля override не-None перекрывают",
    )

    @field_validator("extra_request_body", mode="before")
    @classmethod
    def _extra_must_be_object(cls, v: Any) -> Any:
        if v is None:
            return None
        if isinstance(v, dict):
            return v
        raise ValueError("extra_request_body должен быть объектом JSON, не массивом и не скаляром")

    @field_validator("extra_request_headers", mode="before")
    @classmethod
    def _extra_headers_must_be_object(cls, v: Any) -> Any:
        if v is None:
            return None
        if not isinstance(v, dict):
            raise ValueError("extra_request_headers должен быть объектом JSON, не массивом и не скаляром")
        for key, val in v.items():
            if not isinstance(key, str) or not key.strip():
                raise ValueError("extra_request_headers: ключи — непустые строки")
            if not isinstance(val, str):
                raise ValueError("extra_request_headers: значения должны быть строками")
        return v

    @model_validator(mode="before")
    @classmethod
    def _split_provider_prefixed_model(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        prov_raw = data.get("provider")
        prov_set = prov_raw is not None and isinstance(prov_raw, str) and prov_raw.strip() != ""
        if prov_set:
            return data
        model_raw = data.get("model")
        split_prov, split_model = split_provider_prefixed_model(None, model_raw if isinstance(model_raw, str) else None)
        if split_prov is None:
            return data
        out = dict(data)
        out["provider"] = split_prov
        out["model"] = split_model
        return out


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

    model_config = ConfigDict(json_schema_extra={"storage_prefix": "node"}, populate_by_name=True)

    # ОБЯЗАТЕЛЬНЫЕ ПОЛЯ
    node_id: str = Field(..., description="Уникальный идентификатор ноды")
    type: NodeType = Field(..., description="Тип ноды - NodeType Enum")
    
    name: str = Field(..., description="Название ноды")
    
    @field_validator("node_id", mode="before")
    @classmethod
    def validate_node_id(cls, v: str) -> str:
        """Принимает URN или plain ID, извлекает ID."""
        return extract_id(v)
    
    description: str = Field(default="", description="Описание ноды")
    
    @field_validator("description", mode="before")
    @classmethod
    def validate_description(cls, v: Optional[str]) -> str:
        """Конвертирует None в пустую строку."""
        return v if v is not None else ""
    
    # Data Flow контракт (опциональн, но рекомендуется)
    input_schema: Optional[Dict[str, Any]] = Field(default=None, description="JSON Schema входных данных")
    output_schema: Optional[Dict[str, Any]] = Field(default=None, description="JSON Schema выходных данных")
    tags: List[str] = Field(default_factory=list, description="Группы/категории")
    
    # Для llm_node
    prompt: Optional[str] = Field(default=None, description="Системный промпт")
    tools: List[ToolReference] = Field(
        default_factory=list, description="Список инструментов"
    )
    llm_override: Optional[NodeLLMOverride] = Field(
        default=None, 
        description="Переопределение LLM настроек (если None - из global config)", 
        alias="llm"
    )
    llm_capability: Optional[
        Literal[
            "llm_chat",
            "llm_summarize",
            "llm_format_markdown",
            "llm_codegen",
            "llm_vision",
            "image_gen",
        ]
    ] = Field(
        default=None,
        description=(
            "Декларативная capability ноды для company AI overlay. "
            "Если None — считается llm_chat. Если у компании в metadata.ai_providers "
            "задан override этой capability, runtime подменяет provider/model/api_key "
            "перед вызовом LLM. См. core/company_ai/resolver.py."
        ),
    )
    react: Optional[ReactConfig] = Field(
        default=None, description="Конфигурация ReAct цикла (loop_mode, exit_tool)"
    )
    messages_filter: Union[Literal["all", "own"], List[str]] = Field(
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
    def validate_incoming_policy(cls, v: Any) -> str:
        if v is None:
            return "any"
        if v not in ("any", "all"):
            raise ValueError(f"incoming_policy: ожидается 'any' или 'all', получено {v!r}")
        return v

    @field_validator("messages_filter", mode="before")
    @classmethod
    def validate_messages_filter(cls, v: Any) -> Union[str, List[str]]:
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
            out: List[str] = []
            for i, item in enumerate(v):
                if not isinstance(item, str) or not item.strip():
                    raise ValueError(
                        f"messages_filter: элемент #{i} должен быть непустой строкой (node_id)"
                    )
                out.append(extract_id(item))
            return out
        raise ValueError(
            f"messages_filter: ожидается 'all', 'own' или список строк, получено {type(v).__name__}"
        )
    
    # Structured Output (взаимоисключающе с tools)
    structured_output: bool = Field(
        default=False,
        description="Режим structured output вместо tools (response_format json_schema)"
    )
    output_schema: Optional[Dict[str, Any]] = Field(
        default=None,
        description="JSON Schema для structured output (передается в response_format)"
    )
    output_mapping: Optional[Dict[str, str]] = Field(
        default=None,
        description="Маппинг полей JSON -> state fields. Если None - поля записываются напрямую"
    )
    
    # Для code-ноды (inline)
    code: Optional[str] = Field(default=None, description="Inline Python код")
    
    # Ресурсы ноды
    resources: Dict[str, ResourceReference] = Field(
        default_factory=dict,
        description="Ресурсы ноды (переопределяют flow-level)"
    )

    files: List[Dict[str, Any]] = Field(
        default_factory=list,
        description=(
            "Закреплённые файлы ноды (как элементы state.files: name, path; опционально "
            "mime_type, size, file_id). При старте новой сессии агрегируются в state.files."
        ),
    )

    operator_queue_slug: Optional[str] = Field(
        default=None,
        description="Slug очереди оператора (взаимоисключающе с operator_queue_id)",
    )
    operator_queue_id: Optional[str] = Field(
        default=None,
        description="UUID очереди оператора (взаимоисключающе с operator_queue_slug)",
    )
    operator_handoff_mode: Optional[Literal["single_reply", "takeover"]] = Field(
        default=None,
        description="Режим оператора: single_reply — один ответ; takeover — перехват диалога",
    )
    operator_task_title: Optional[str] = Field(
        default=None,
        description="Заголовок задачи; можно переопределить input_mapping.task_title",
    )
    operator_user_message: Optional[str] = Field(
        default=None,
        description="Текст для пользователя; можно переопределить input_mapping.user_facing_message",
    )
    
    # Общее
    local_variables: Dict[str, Any] = Field(
        default_factory=dict, description="Локальные переменные"
    )
    store: Dict[str, Any] = Field(default_factory=dict, description="Начальные данные store")
    source: str = Field(default="manual", description="Источник создания")
    created_at: Optional[datetime] = Field(default=None, description="Дата создания")
    updated_at: Optional[datetime] = Field(default=None, description="Дата обновления")
    
    # Контроль доступа для UI
    public_fields: Optional[List[str]] = Field(
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
    exception_allow_types: List[ExceptionAbsorbAllowName] = Field(
        default_factory=list,
        description=(
            "Whitelist имён классов исключений (ExceptionAbsorbAllowName). Пустой список при "
            "exception_as_response=True означает любое исключение; иначе только перечисленные типы"
        ),
    )
    node_timeout_seconds: Optional[int] = Field(
        default=None,
        description=(
            "Wall-clock лимит ноды (сек), верх — node_execution_wall_time_cap_seconds; "
            "None = только лимит flow"
        ),
    )
    max_visits_per_run: Optional[int] = Field(
        default=None,
        description=(
            "Максимум заходов в эту ноду за один Flow.run; None — для code действует дефолт платформы, "
            "для прочих типов отдельного лимита нет (только итерации графа)"
        ),
    )

    @field_validator("node_timeout_seconds", mode="before")
    @classmethod
    def validate_node_timeout_seconds(cls, v: Any) -> Optional[int]:
        if v is None:
            return None
        iv = int(v)
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
    def validate_max_visits_per_run(cls, v: Any) -> Optional[int]:
        if v is None:
            return None
        iv = int(v)
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
