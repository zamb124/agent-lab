"""
Модель FlowConfig - конфигурация flow.

Flow = граф:
- nodes: ноды (llm_node, function, flow)
- edges: связи между нодами с условиями
- entry: точка входа

Zero-Guess Architecture:
- Использует StrictBaseModel (extra='forbid')
- Использует MergeMode Enum вместо класса
- Явные типы для всех полей
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from enum import Enum
from typing import Annotated, ClassVar, Literal, Self, cast, override

from oxyde import Field as DbField
from oxyde import Index, Query, execute_raw
from pydantic import ConfigDict, Field, field_validator, model_validator

from apps.flows.src.models.execution_limits import get_flow_execution_wall_time_cap_seconds
from core.context.context import get_context
from core.flow_ui.document import FlowUIDocument
from core.flow_ui.templates import default_chat_document
from core.logging import get_logger
from core.models import StrictBaseModel
from core.models.platform_model import CompanyScopedModel
from core.types import JsonObject, JsonValue, parse_json_object, require_json_object
from core.urn import extract_resource_id
from core.variables.models import VariableEntry, normalize_variables_map

from .enums import MergeMode
from .flow_speech_settings import FlowSpeechSettings
from .resource import ResourceReference
from .trigger_config import TriggerConfig

logger = get_logger(__name__)

_PAGE = 1000

# Тип для permission: строка или список строк
Permission = str | list[str] | None


def _parse_flow_config_int(value: object, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name}: expected integer, got bool")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            raise ValueError(f"{field_name}: expected integer, got an empty string")
        try:
            return int(stripped, 10)
        except ValueError as exc:
            raise ValueError(
                f"{field_name}: expected integer, got {value!r}"
            ) from exc
    raise ValueError(f"{field_name}: expected integer, got {type(value).__name__}")


class FlowType(str, Enum):
    """Тип flow"""
    LOCAL = "local"
    EXTERNAL = "external"


class ExternalAgentStatus(str, Enum):
    """Статус внешнего агента"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    UNHEALTHY = "unhealthy"


class FlowVariableConfig(VariableEntry):
    """
    Конфигурация переменной flow с метаданными.

    Контракт значения {value, secret} симметричен company-уровню
    (`core.variables.models.PlatformVariable`). При выполнении flow
    переменная по тому же ключу перекрывает company-переменную.
    """


def normalize_flow_variables_map(raw: Mapping[str, object]) -> dict[str, FlowVariableConfig]:
    """Нормализует scalar/wrapped JSON в dict[str, FlowVariableConfig]."""
    normalized = normalize_variables_map(raw)
    result: dict[str, FlowVariableConfig] = {}
    for key, entry in normalized.items():
        if isinstance(entry, FlowVariableConfig):
            result[key] = entry
        else:
            result[key] = FlowVariableConfig.model_validate(entry.model_dump())
    return result


def normalize_flow_variables_payload(data: object) -> object:
    """Нормализует scalar JSON variables в строгий FlowVariableConfig payload."""
    if not isinstance(data, dict):
        return data
    raw = cast(Mapping[str, object], data)
    variables = raw.get("variables")
    if not isinstance(variables, dict):
        return dict(raw)

    out = dict(raw)
    out["variables"] = normalize_flow_variables_map(cast(Mapping[str, object], variables))
    return out


EdgeConditionOperator = Literal["==", "!=", ">", "<", ">=", "<=", "in"]
EdgeCodeLanguage = Literal["python", "javascript", "typescript", "go", "csharp"]


class SimpleEdgeCondition(StrictBaseModel):
    """Типизированное условие перехода по значению из ExecutionState."""

    type: Literal["simple"] = "simple"
    variable: str = Field(..., min_length=1, description="Путь в ExecutionState")
    operator: EdgeConditionOperator = Field(..., description="Оператор сравнения")
    value: JsonValue = Field(..., description="JSON-значение для сравнения")


class CodeEdgeCondition(StrictBaseModel):
    """Типизированное условие перехода через durable code activity."""

    type: Literal["code"] = "code"
    language: EdgeCodeLanguage = Field(..., description="Язык code-condition")
    code: str = Field(..., min_length=1, description="Исходный код condition activity")
    entrypoint: str | None = Field(default=None, min_length=1, description="Entry point функции")


EdgeCondition = Annotated[SimpleEdgeCondition | CodeEdgeCondition, Field(discriminator="type")]


class Edge(StrictBaseModel):
    """
    Связь между нодами.

    condition - типизированный объект для проверки (опционально).
    Если condition не указан - безусловный переход.

    Допустимые форматы condition:
      - `{"type": "simple", "variable": str, "operator": str, "value": Any}`;
      - `{"type": "code", "language": "python|javascript|typescript|go|csharp", "code": str}`.

    from_port — именованный out-порт исходной ноды (UI + валидация).
    Для reflection: `approved` | `blocked`. Runtime ветвит только по condition.
    """

    from_node: str = Field(..., description="ID исходной ноды")
    to_node: str | None = Field(..., description="ID целевой ноды (null = конец)")
    condition: EdgeCondition | None = Field(
        default=None,
        description="Условие перехода: simple ({type, variable, operator, value}) или code ({type, language, code}).",
    )
    from_port: str | None = Field(
        default=None,
        min_length=1,
        description="Именованный out-порт исходной ноды (reflection: approved|blocked)",
    )
    contributes_to_join: bool = Field(
        default=True,
        description=(
            "При incoming_policy=all у целевой ноды: ребро участвует в AND; false = переход без ожидания остальных входов"
        ),
    )

    model_config: ClassVar[ConfigDict] = ConfigDict(populate_by_name=True)


class BranchConfig(StrictBaseModel):
    """
    Конфигурация ветки графа (варианта flow) внутри одного flow_id.

    Ветка имеет ту же структуру, что и базовый граф: entry, nodes, edges, variables.
    Для каждого поля можно указать режим применения через *_mode.
    Если branches не указаны в FlowConfig, автоматически создаётся default-ветка.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(use_enum_values=False)

    name: str = Field(..., description="Название ветки")
    description: str = Field(default="", description="Описание ветки")
    tags: list[str] = Field(default_factory=list, description="Теги ветки")
    permission: list[str] = Field(
        default_factory=list,
        description=(
            "Группы с доступом к ветке. Пустой список = наследование viewer от flow"
        ),
    )

    @field_validator("permission", mode="before")
    @classmethod
    def validate_permission(cls, v: str | list[str] | None) -> list[str]:
        """Конвертирует None в [], string в [string]."""
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        return v

    # Точка входа (всегда replace если указана)
    entry: str | None = Field(default=None, description="Точка входа")

    # Ноды
    nodes: dict[str, JsonObject] | None = Field(default=None, description="Ноды ветки")
    nodes_mode: MergeMode = Field(
        default=MergeMode.REPLACE, description="Режим применения nodes: 'merge' или 'replace'"
    )

    # Связи между нодами
    edges: list[Edge] | None = Field(default=None, description="Связи между нодами")
    edges_mode: MergeMode = Field(
        default=MergeMode.REPLACE, description="Режим применения edges: 'merge' или 'replace'"
    )

    # Переменные
    variables: dict[str, FlowVariableConfig] = Field(
        default_factory=dict, description="Переменные ветки с метаданными"
    )
    variables_mode: MergeMode = Field(
        default=MergeMode.MERGE, description="Режим применения variables: 'merge' или 'replace'"
    )

    # Ресурсы skill
    resources: dict[str, ResourceReference] = Field(
        default_factory=dict,
        description="Ресурсы ветки (мержатся с flow-level)",
    )
    resources_mode: MergeMode = Field(
        default=MergeMode.MERGE,
        description="Режим применения resources: 'merge' или 'replace'"
    )

    speech: FlowSpeechSettings | None = Field(
        default=None,
        description="Переопределение профиля речи для ветки (мержится поверх flow.speech)",
    )

    interface: FlowUIDocument | None = Field(
        default=None,
        description="Интерфейс ветки; None — интерфейс flow",
    )

    @model_validator(mode="before")
    @classmethod
    def _normalize_variables(cls, data: object) -> object:
        """Нормализует variables: простые значения -> FlowVariableConfig."""
        return normalize_flow_variables_payload(data)


class FlowEmployeeConfig(StrictBaseModel):
    """Конфигурация flow как сотрудника платформы (runtime-identity).

    Включённый режим делает flow полноценным ``User`` компании: он действует от
    собственного имени во всех сервисах (RBAC, ACL, sync, worktracker, биллинг),
    и платформа диспатчит ему работу так же, как человеку. У каждого сотрудника
    обязателен куратор-человек (``curator_user_ids``) — нет AI-сотрудника без
    ответственного.
    """

    enabled: bool = Field(
        default=False,
        description="Активировать runtime-identity: flow становится сотрудником компании",
    )
    roles: list[str] = Field(
        default_factory=list,
        description="Роли сотрудника в компании (RBAC). Задаются явно, без дефолта-угадывания",
    )
    curator_user_ids: list[str] = Field(
        default_factory=list,
        description="user_id кураторов-людей. Обязателен минимум один при enabled=True",
    )
    display_name: str | None = Field(
        default=None,
        description="Отображаемое имя сотрудника. None = FlowConfig.name",
    )
    avatar_url: str | None = Field(
        default=None,
        description="URL аватара сотрудника для team UI и user-chip",
    )

    @model_validator(mode="after")
    def _validate_enabled_invariants(self) -> "FlowEmployeeConfig":
        if not self.enabled:
            return self
        clean_roles = [role.strip() for role in self.roles if role.strip()]
        if not clean_roles:
            raise ValueError("FlowEmployeeConfig: enabled requires a non-empty roles")
        clean_curators = [uid.strip() for uid in self.curator_user_ids if uid.strip()]
        if not clean_curators:
            raise ValueError(
                "FlowEmployeeConfig: enabled requires at least one curator_user_ids"
            )
        return self


class FlowToolPickerItem(StrictBaseModel):
    """
    Lightweight projection для tool picker: только поля списка без валидации
    полного FlowConfig / Flow UI document.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore")

    flow_id: str
    name: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)


class FlowListIndexItem(StrictBaseModel):
    """Проекция списка flows: id и type без полного FlowConfig / Flow UI."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore")

    flow_id: str
    type: FlowType


class FlowConfig(CompanyScopedModel):
    """Конфигурация flow. Текущая версия и история — строки таблицы ``flows``."""

    __database_alias__: ClassVar[str | None] = "flows"

    class Meta:
        is_table: bool = True
        table_name: str = "flows"
        indexes: list[Index] = [
            Index(["company_id", "flow_id"], unique=True, where="is_current = true"),
        ]

    flow_id: str = DbField(description="Уникальный идентификатор flow")
    name: str = DbField(description="Название flow")
    company_id: str = DbField(default="", db_index=True)
    flow_row_id: str = DbField(default="", db_pk=True, db_type="TEXT")
    is_current: bool = DbField(default=False, db_index=True)
    type: FlowType = Field(default=FlowType.LOCAL, description="Тип flow (local/external)")

    @field_validator("flow_id", mode="before")
    @classmethod
    def validate_flow_id(cls, v: str) -> str:
        """Принимает URN или plain ID, извлекает ID."""
        return extract_resource_id(v)

    description: str = DbField(default="", db_type="TEXT", description="Описание flow")

    @field_validator("description", mode="before")
    @classmethod
    def validate_description(cls, v: str | None) -> str:
        """Конвертирует None в пустую строку."""
        return v if v is not None else ""

    # LOCAL FLOW ПОЛЯ - обязательны для LOCAL, опциональны для EXTERNAL
    entry: str | None = Field(default=None, description="ID стартовой ноды - ОБЯЗАТЕЛЬНО для LOCAL")
    nodes: dict[str, JsonObject] | None = Field(
        default=None,
        description="Ноды графа - ОБЯЗАТЕЛЬНО для LOCAL"
    )
    edges: list[Edge] = DbField(
        default_factory=list,
        db_type="JSONB",
        description="Связи между нодами",
    )

    # EXTERNAL FLOW ПОЛЯ - обязательны для EXTERNAL, опциональны для LOCAL
    url: str | None = Field(default=None, description="Base URL внешнего flow (A2A) - ОБЯЗАТЕЛЬНО для EXTERNAL")
    headers: dict[str, str] = Field(default_factory=dict, description="HTTP-заголовки к внешнему агенту (A2A)")
    status: ExternalAgentStatus = Field(
        default=ExternalAgentStatus.INACTIVE, description="Статус внешнего flow (A2A)"
    )
    last_health_check: datetime | None = Field(
        default=None, description="Время последней проверки здоровья"
    )
    agent_card: JsonObject | None = Field(default=None, description="Кэш agent-card.json")
    permission: list[str] = Field(
        default_factory=list,
        description="Группы с доступом. Пустой список = company-visible (member компании)",
    )

    @field_validator("permission", mode="before")
    @classmethod
    def validate_permission(cls, v: str | list[str] | None) -> list[str]:
        """Конвертирует None в [], string в [string]."""
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        return v

    @field_validator("timeout", mode="before")
    @classmethod
    def validate_flow_timeout_seconds(cls, v: object) -> int | None:
        if v is None:
            return None
        iv = _parse_flow_config_int(v, "timeout")
        if iv < 1:
            raise ValueError(f"timeout: expected >= 1, got {iv}")
        cap = get_flow_execution_wall_time_cap_seconds()
        if iv > cap:
            raise ValueError(f"timeout: maximum {cap}s (flow_execution_wall_time_cap_seconds), got {iv}")
        return iv

    # Опциональные/технические поля
    version: str = Field(default="", description="Версия flow (timestamp)")
    tags: list[str] = Field(default_factory=list, description="Теги для группировки")

    variables: dict[str, FlowVariableConfig] = Field(
        default_factory=dict,
        description="Переменные flow с метаданными. @var:key резолвятся из БД",
    )

    metadata: JsonObject = Field(
        default_factory=dict,
        description=(
            "UI-метаданные flow editor (sticky_notes, layout-подсказки и пр.). "
            "Не влияет на исполнение; обновляется через PATCH /flows/{flow_id}/metadata. "
            "viewBox preference и заметки на канвасе."
        ),
    )

    @model_validator(mode="before")
    @classmethod
    def _normalize_variables(cls, data: object) -> object:
        """Нормализует variables: простые значения -> FlowVariableConfig."""
        return normalize_flow_variables_payload(data)

    branches: dict[str, BranchConfig] = Field(
        default_factory=dict,
        description="Ветки flow (варианты графа). Если пусто — автоматически default-ветка",
    )
    channels: dict[str, JsonObject] = Field(
        default_factory=lambda: {"a2a": {}}, description="Каналы"
    )
    store: JsonObject = Field(default_factory=dict, description="Начальные данные")
    timeout: int | None = Field(
        default=None,
        description="Wall-clock лимит одного run flow (сек), верх снимается с flow_execution_wall_time_cap_seconds; None = default_flow_timeout_seconds",
    )
    max_retries: int = Field(default=0, description="Максимум повторов")
    source: str = Field(default="manual", description="Источник создания")
    created_at: datetime | None = Field(default=None)
    updated_at: datetime | None = Field(default=None)
    hidden: bool = Field(default=False, description="Скрытый flow (не отображается в UI)")

    depends_on_flow_ids: list[str] = Field(
        default_factory=list,
        description=(
            "Bundle-only (flow.json): flow_id агентов-зависимостей. "
            "При reload-from-bundle и company init ставятся до этого flow."
        ),
    )

    store_card_image_url: str | None = Field(
        default=None,
        description=(
            "URL обложки агента (витрина, публичные embed/лендинг). "
            "В UI задаётся загрузкой файла; при установке из bundle поле материализуется из store_card_image."
        ),
    )

    # Ресурсы flow
    resources: dict[str, ResourceReference] = Field(
        default_factory=dict,
        description="Ресурсы flow, доступные всем нодам"
    )

    speech: FlowSpeechSettings | None = DbField(
        default=None,
        db_type="JSONB",
        description="Профиль речи (STT/TTS/VAD) без секретов; tier ниже explicit SpeechOverride, выше company",
    )

    interface: FlowUIDocument = DbField(
        default_factory=default_chat_document,
        db_type="JSONB",
        description="Design-time интерфейс flow; чат — документ по умолчанию",
    )

    # Триггеры flow — точки входа (telegram, cron, webhook, email)
    triggers: dict[str, TriggerConfig] = Field(
        default_factory=dict,
        description="Триггеры flow {trigger_id: TriggerConfig}"
    )

    employee: FlowEmployeeConfig = DbField(
        default_factory=FlowEmployeeConfig,
        db_type="JSONB",
        description="Конфигурация flow как сотрудника компании (runtime-identity)",
    )

    # Контроль доступа для UI
    public_fields: list[str] | None = Field(
        default=None,
        description="Поля доступные для редактирования в UI. None = все поля доступны"
    )

    @classmethod
    def row_id(cls, flow_id: str, version: str) -> str:
        ctx = get_context()
        if ctx is None or ctx.active_company is None or ctx.active_company.company_id == "":
            raise ValueError("flow_id requires an active company")
        company_id = ctx.active_company.company_id
        if (
            flow_id == ""
            or version == ""
            or ":" in company_id
            or ":" in flow_id
            or ":" in version
        ):
            raise ValueError("flow_id and version are required and must not contain ':'")
        return f"{len(company_id)}:{company_id}:{flow_id}:{version}"

    @model_validator(mode="after")
    def bind_company(self) -> Self:
        ctx = get_context()
        if ctx is None or ctx.active_company is None:
            return self
        company_id = ctx.active_company.company_id
        if company_id == "":
            raise ValueError("company_id is required")
        if self.company_id == "":
            self.company_id = company_id
        elif self.company_id != company_id:
            raise ValueError("company_id does not match the active company")
        if self.version == "":
            return self
        expected = type(self).row_id(self.flow_id, self.version)
        if self.flow_row_id == "":
            self.flow_row_id = expected
        elif self.flow_row_id != expected:
            raise ValueError("flow_row_id does not match company_id, flow_id and version")
        return self

    @override
    async def pre_save(self, *, is_create: bool, update_fields: set[str] | None = None) -> None:
        expected = type(self).row_id(self.flow_id, self.version)
        if self.company_id == "" or self.flow_row_id != expected:
            raise ValueError("flow_row_id does not match the active company")
        _ = is_create, update_fields

    def interface_for_branch(self, branch_id: str) -> FlowUIDocument:
        """Интерфейс ветки, если ветка задала свой; иначе интерфейс flow."""
        branch = self.branches.get(branch_id)
        if branch is not None and branch.interface is not None:
            return branch.interface
        return self.interface

    @model_validator(mode="after")
    def validate_flow_type_fields(self) -> "FlowConfig":
        """Валидация полей в зависимости от типа flow."""
        if self.type == FlowType.LOCAL:
            if not self.entry:
                raise ValueError("LOCAL flow must have 'entry' field")
            if not self.nodes:
                raise ValueError("LOCAL flow must have 'nodes' field")
        elif self.type == FlowType.EXTERNAL:
            if not self.url:
                raise ValueError("EXTERNAL flow must have 'url' field")
        return self

    @classmethod
    async def get_latest(cls, flow_id: str) -> Self | None:
        if flow_id == "":
            raise ValueError("flow_id is required")
        return await cls.objects.filter(flow_id=flow_id, is_current=True).get_or_none()

    @classmethod
    async def get_latest_by_flow_id_unscoped(
        cls, flow_id: str
    ) -> tuple[Self, str] | None:
        if flow_id.strip() == "":
            raise ValueError("flow_id is required")
        rows = await execute_raw(
            """
            SELECT row_to_json(flows) AS flow
            FROM flows
            WHERE flow_id = $1 AND is_current = true
            LIMIT 2
            """,
            [flow_id],
            using="flows",
        )
        if len(rows) > 1:
            raise RuntimeError(f"flow_id {flow_id} is current in more than one company")
        if len(rows) == 0:
            return None
        envelope = require_json_object(rows[0], "flow")
        raw_flow = envelope["flow"]
        if isinstance(raw_flow, str):
            payload = parse_json_object(raw_flow, "flow")
        else:
            payload = require_json_object(raw_flow, "flow")
        config = cls.model_validate(payload)
        return (config, config.company_id)

    @classmethod
    async def get_current_for_company(cls, company_id: str, flow_id: str) -> Self | None:
        if company_id.strip() == "" or flow_id.strip() == "":
            raise ValueError("company_id and flow_id are required")
        rows = await execute_raw(
            """
            SELECT row_to_json(flows) AS flow
            FROM flows
            WHERE company_id = $1 AND flow_id = $2 AND is_current = true
            LIMIT 2
            """,
            [company_id, flow_id],
            using="flows",
        )
        if len(rows) > 1:
            raise RuntimeError(
                f"flow_id {flow_id} is current more than once in company {company_id}"
            )
        if len(rows) == 0:
            return None
        envelope = require_json_object(rows[0], "flow")
        raw_flow = envelope["flow"]
        if isinstance(raw_flow, str):
            payload = parse_json_object(raw_flow, "flow")
        else:
            payload = require_json_object(raw_flow, "flow")
        return cls.model_validate(payload)

    @classmethod
    async def list_company_identifiers(
        cls,
        *,
        limit: int = 10_000,
        offset: int = 0,
    ) -> list[str]:
        if limit < 1:
            raise ValueError("limit must be >= 1")
        if offset < 0:
            raise ValueError("offset must be >= 0")
        rows = await execute_raw(
            """
            SELECT DISTINCT company_id
            FROM flows
            WHERE is_current = true
            ORDER BY company_id
            LIMIT $1 OFFSET $2
            """,
            [limit, offset],
            using="flows",
        )
        identifiers: list[str] = []
        for row in rows:
            payload = require_json_object(row, "company_id")
            company_id = payload["company_id"]
            if not isinstance(company_id, str) or company_id == "":
                raise TypeError("flows.company_id must be a non-empty string")
            identifiers.append(company_id)
        return identifiers

    @classmethod
    async def get_version(cls, flow_id: str, version: str) -> Self | None:
        if flow_id == "" or version == "":
            raise ValueError("flow_id and version are required")
        return await cls.objects.filter(flow_id=flow_id, version=version).get_or_none()

    @classmethod
    async def list_versions(cls, flow_id: str) -> list[str]:
        if flow_id == "":
            raise ValueError("flow_id is required")
        rows = await cls.objects.filter(flow_id=flow_id).order_by("-version").all()
        return [row.version for row in rows]

    @classmethod
    async def create_version(cls, entity: Self) -> bool:
        version = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
        now = datetime.now(timezone.utc)
        entity.version = version
        entity.is_current = True
        context = get_context()
        if context is None or context.active_company is None or context.active_company.company_id == "":
            raise ValueError("flow save requires an active company")
        entity.company_id = context.active_company.company_id
        entity.flow_row_id = cls.row_id(entity.flow_id, version)
        if entity.created_at is None:
            entity.created_at = now
        entity.updated_at = now
        previous = await cls.get_latest(entity.flow_id)
        if previous is not None:
            previous.is_current = False
            _ = await previous.save(update_fields={"is_current"})
        _ = await cls.objects.create(instance=entity)
        logger.info("flows.repo.saved", flow_id=entity.flow_id, version=version)
        return True

    @classmethod
    def _current_flows(cls) -> Query[Self]:
        return cls.objects.filter(is_current=True).order_by("-created_at", "flow_id")

    @classmethod
    async def latest_by_flow_ids(cls, flow_ids: list[str]) -> dict[str, Self]:
        if len(flow_ids) == 0:
            return {}
        for flow_id in flow_ids:
            if flow_id == "":
                raise ValueError("flow_id is required")
        rows = await cls.objects.filter(flow_id__in=flow_ids, is_current=True).all()
        return {row.flow_id: row for row in rows}

    @classmethod
    async def list_current(cls, *, limit: int, offset: int = 0) -> list[Self]:
        if limit < 1:
            raise ValueError("limit must be >= 1")
        if offset < 0:
            raise ValueError("offset must be >= 0")
        return await cls._current_flows().limit(limit).offset(offset).all()

    @classmethod
    async def list_index(cls) -> list[FlowListIndexItem]:
        items: list[FlowListIndexItem] = []
        offset = 0
        while True:
            rows = await cls._current_flows().limit(_PAGE).offset(offset).all()
            items.extend(
                FlowListIndexItem(flow_id=row.flow_id, type=row.type) for row in rows
            )
            if len(rows) < _PAGE:
                return items
            offset += _PAGE

    @classmethod
    async def list_for_tool_picker(cls, *, limit: int, offset: int = 0) -> list[FlowToolPickerItem]:
        if limit < 1:
            raise ValueError("limit must be >= 1")
        if offset < 0:
            raise ValueError("offset must be >= 0")
        rows = await cls._current_flows().limit(limit).offset(offset).all()
        return [
            FlowToolPickerItem(
                flow_id=row.flow_id,
                name=row.name,
                description=row.description,
                tags=row.tags,
            )
            for row in rows
        ]

    @classmethod
    async def list_picker_index(cls) -> list[FlowToolPickerItem]:
        items: list[FlowToolPickerItem] = []
        offset = 0
        while True:
            page = await cls.list_for_tool_picker(limit=_PAGE, offset=offset)
            items.extend(page)
            if len(page) < _PAGE:
                return items
            offset += _PAGE

    @classmethod
    async def delete_by_flow_id(cls, flow_id: str) -> bool:
        if flow_id == "":
            raise ValueError("flow_id is required")
        deleted = await cls.objects.filter(flow_id=flow_id).delete()
        if deleted == 0:
            logger.info("flows.repo.delete_missing", flow_id=flow_id)
            return False
        logger.info("flows.repo.deleted", flow_id=flow_id, version_count=deleted)
        return True

    @classmethod
    async def rollback_to_version(cls, flow_id: str, version: str) -> bool:
        snapshot = await cls.get_version(flow_id, version)
        if snapshot is None:
            return False
        current = await cls.get_latest(flow_id)
        if current is not None and current.flow_row_id != snapshot.flow_row_id:
            current.is_current = False
            _ = await current.save(update_fields={"is_current"})
        snapshot.is_current = True
        _ = await snapshot.save(update_fields={"is_current"})
        logger.info("flows.repo.rolled_back", flow_id=flow_id, version=version)
        return True
