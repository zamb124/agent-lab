"""
Pydantic модели для API endpoints.
"""

from datetime import date, datetime
from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from apps.crm.types import JsonObject, JsonValue

SemanticTextIndexStatus = Literal["absent", "pending_embedding", "ready"]

from core.models.identity_models import BoardStage, NamespaceCRMSettings  # noqa: E402


class EntityCreate(BaseModel):
    """Создание entity"""

    entity_type: str
    entity_subtype: str | None = None
    namespace: str = Field(default="default", description="Namespace для изоляции")
    name: str
    description: str | None = None
    attributes: JsonObject | None = None
    tags: list[str] | None = None
    attachment_ids: list[str] | None = None
    user_id: str | None = None

    voice_entity_id: str | None = Field(
        default=None,
        description="Сущность-голос (обычно contact); null в JSON — без голоса при переданном поле",
    )
    context_entity_id: str | None = Field(
        default=None,
        description="Якорь контекста; null — без привязки",
    )

    note_date: date | None = None
    due_date: date | None = None
    priority: str | None = None
    assignees: list[str] = Field(default_factory=list)


class EntityUpdate(BaseModel):
    """Обновление entity"""

    name: str | None = None
    description: str | None = None
    status: str | None = None
    attributes: JsonObject | None = None
    tags: list[str] | None = None
    attachment_ids: list[str] | None = None

    voice_entity_id: str | None = None
    context_entity_id: str | None = None

    entity_type: str | None = None
    entity_subtype: str | None = None

    note_date: date | None = None
    due_date: date | None = None
    priority: str | None = None
    assignees: list[str] | None = Field(default=None)


class EntityResponse(BaseModel):
    """Response с entity"""

    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)

    entity_id: str
    company_id: str
    namespace: str
    entity_type: str
    entity_subtype: str | None
    name: str
    description: str | None
    status: str
    attributes: JsonObject
    tags: list[str]
    attachment_ids: list[str]

    note_date: date | None
    due_date: date | None
    priority: str | None
    assignees: list[str]

    user_id: str | None
    source_entity_id: str | None
    source_company_id: str | None
    external_relationships: list[JsonObject] = []
    relevance: float = Field(
        description="Значение CRMEntity.relevance в БД; на ранжирование результатов поиска не влияет.",
    )
    access_level: str | None = None
    score: float | None = Field(
        default=None,
        description="Релевантность из пайплайна поиска (semantic / text / hybrid), если запрос — поиск. Не смешивается с relevance сущности и не зависит от весов рёбер графа.",
    )
    match_type: str | None = Field(
        default=None,
        description="Источник совпадения в гибридном поиске, когда применимо.",
    )
    semantic_text_index_status: SemanticTextIndexStatus | None = Field(
        default=None,
        description=(
            "Семантический индекс основного текста сущности (pgvector, document_id = entity_id). "
            "None — не pgvector или поле не включено в ответ."
        ),
    )

    created_at: datetime
    updated_at: datetime


class EntitySearchFilterNode(BaseModel):
    """DSL-узел фильтра поиска сущностей."""

    model_config: ClassVar[ConfigDict] = ConfigDict(populate_by_name=True, extra="forbid")

    and_nodes: list["EntitySearchFilterNode"] | None = Field(default=None, alias="$and")
    or_nodes: list["EntitySearchFilterNode"] | None = Field(default=None, alias="$or")
    field: str | None = None
    op: str | None = None
    value: JsonValue | None = None

    @model_validator(mode="after")
    def validate_shape(self) -> "EntitySearchFilterNode":
        has_and = self.and_nodes is not None
        has_or = self.or_nodes is not None
        has_leaf = self.field is not None or self.op is not None or self.value is not None

        if has_and and has_or:
            raise ValueError("Filter node cannot include both $and and $or")
        if (has_and or has_or) and has_leaf:
            raise ValueError("Logical filter node cannot include field/op/value")

        if self.and_nodes is not None:
            if len(self.and_nodes) < 2:
                raise ValueError("$and requires at least 2 child nodes")
            return self
        if self.or_nodes is not None:
            if len(self.or_nodes) < 2:
                raise ValueError("$or requires at least 2 child nodes")
            return self

        if self.field is None or self.op is None:
            raise ValueError("Leaf filter node requires field and op")
        if self.value is None:
            raise ValueError("Leaf filter node requires value")
        return self


_ = EntitySearchFilterNode.model_rebuild()


class EntitySearchQueryRequest(BaseModel):
    """POST-контракт поиска/листинга сущностей через DSL-фильтры."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    query: str | None = None
    search_mode: Literal["text", "semantic", "hybrid"] = Field(
        default="hybrid",
        description="Режим поиска: только текст (FTS), только semantic (вектор), hybrid (RRF). Рёбра графа ранжирование не меняют.",
    )
    entity_type: str | None = None
    entity_subtype: str | None = None
    namespace: str | None = None
    filters: EntitySearchFilterNode | None = None
    cursor: str | None = None
    limit: int = Field(default=100, ge=1, le=1000)


class BulkCreateRequest(BaseModel):
    """Batch создание сущностей (до 200)."""

    items: list["EntityCreate"]


class BulkUpdateItem(BaseModel):
    entity_id: str
    updates: JsonObject


class BulkUpdateRequest(BaseModel):
    items: list[BulkUpdateItem]


class BulkDeleteRequest(BaseModel):
    entity_ids: list[str]


class BulkErrorItem(BaseModel):
    index: int
    entity_id: str | None = None
    error: str


class BulkCreateResponse(BaseModel):
    created: list[EntityResponse]
    errors: list[BulkErrorItem]


class BulkUpdateResponse(BaseModel):
    updated: list[EntityResponse]
    errors: list[BulkErrorItem]


class BulkDeleteResponse(BaseModel):
    deleted: list[str]
    errors: list[BulkErrorItem]


class BulkCardsRequest(BaseModel):
    """Batch загрузка карточек по списку entity_id."""

    entity_ids: list[str]


class EntityTimelineBoundsResponse(BaseModel):
    """Границы timeline по created_at."""

    min_created_at: datetime | None
    max_created_at: datetime | None
    total_entities: int


MergeSide = Literal["survivor", "source"]


class EntityMergeRequest(BaseModel):
    """Слияние source в survivor: survivor сохраняет entity_id и entity_type, source удаляется."""

    survivor_entity_id: str
    source_entity_id: str
    scalar_choices: dict[str, MergeSide] = Field(
        default_factory=dict,
        description="Для каждого конфликтного скаляра: survivor | source",
    )
    attribute_choices: dict[str, MergeSide] = Field(
        default_factory=dict,
        description="Для каждого конфликтного ключа attributes",
    )


class EntityMergeResponse(BaseModel):
    """Результат слияния: актуальная survivor-сущность и id удалённой."""

    entity: EntityResponse
    merged_from_entity_id: str


class EntityTypeCreate(BaseModel):
    """Создание типа сущности"""

    type_id: str
    namespace: str = Field(default="default", min_length=1)
    parent_type_id: str | None = None
    name: str
    description: str | None = None
    prompt: str | None = None
    required_fields: JsonObject | None = None
    optional_fields: JsonObject | None = None
    icon: str | None = None
    color: str | None = None
    is_event: bool = False
    check_duplicates: bool = True
    is_context_anchor: bool = False
    is_voice_target: bool = False
    auto_resolve_suggests: bool = False


class EntityTypeUpdate(BaseModel):
    """Обновление типа сущности"""

    name: str | None = None
    description: str | None = None
    parent_type_id: str | None = None
    prompt: str | None = None
    required_fields: JsonObject | None = None
    optional_fields: JsonObject | None = None
    icon: str | None = None
    color: str | None = None
    is_context_anchor: bool | None = None
    is_voice_target: bool | None = None
    auto_resolve_suggests: bool | None = None


class EntityTypeResponse(BaseModel):
    """Response с типом сущности"""

    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)

    type_id: str
    company_id: str
    namespace: str
    parent_type_id: str | None
    name: str
    description: str | None
    prompt: str | None
    required_fields: JsonObject
    optional_fields: JsonObject
    public_fields: list[str]
    icon: str | None
    color: str | None
    is_system: bool
    is_event: bool
    check_duplicates: bool
    weight_coefficient: float
    is_context_anchor: bool
    is_voice_target: bool
    auto_resolve_suggests: bool
    extractable: bool
    created_at: datetime
    list_entity_type: str
    list_entity_subtype: str | None = None


class RelationshipTypeCreate(BaseModel):
    """Создание типа связи"""

    type_id: str
    name: str
    description: str | None = None
    prompt: str | None = None
    is_directed: bool = True
    inverse_type_id: str | None = None
    icon: str | None = None
    color: str | None = None
    weight_default: float = 1.0


class RelationshipTypeResponse(BaseModel):
    """Response с типом связи"""

    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)

    type_id: str
    company_id: str
    name: str
    description: str | None
    prompt: str | None
    is_directed: bool
    inverse_type_id: str | None
    icon: str | None
    color: str | None
    is_system: bool
    weight_default: float
    created_at: datetime


class RelationshipCreate(BaseModel):
    """Создание связи"""

    source_entity_id: str
    target_entity_id: str
    relationship_type: str
    namespace: str = Field(default="default", description="Namespace для изоляции")
    weight: float = Field(
        default=1.0,
        description="Сила или стоимость связи; участвует в метриках пути по графу, не в ранжировании поиска сущностей.",
    )
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Достоверность связи (например из AI); не участвует в ранжировании поиска сущностей и не входит в стоимость кратчайшего пути.",
    )
    attributes: JsonObject | None = None


class RelationshipResponse(BaseModel):
    """Response со связью"""

    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)

    relationship_id: str
    company_id: str
    namespace: str
    source_entity_id: str
    target_entity_id: str
    relationship_type: str
    weight: float = Field(
        description="Сила или стоимость связи; в кратчайшем пути по графу накапливается как расстояние.",
    )
    confidence: float = Field(
        description="Достоверность связи; на длину пути и на поиск сущностей не влияет.",
    )
    attributes: JsonObject
    created_at: datetime
    updated_at: datetime


class SearchMentionsRequest(BaseModel):
    """Запрос на поиск упоминаний в тексте"""

    text: str = Field(description="Текст для поиска упоминаний")
    namespace: str | None = Field(None, description="Namespace для ограничения поиска")


class AIAnalyzeRequest(BaseModel):
    """Запрос на AI анализ текста"""

    text: str = Field(description="Текст для анализа")
    extract_entity_types: list[str] | None = Field(
        default=None, description="Типы для извлечения (None = все)"
    )
    extract_relationship_types: list[str] | None = Field(
        default=None, description="Типы связей для извлечения (None = все кроме linked)"
    )
    mentioned_entity_ids: list[str] | None = Field(
        default=None, description="ID entities, упомянутых через @"
    )
    namespace: str | None = Field(
        default=None, description="Namespace для ограничения типов и дедупликации"
    )


class NamespaceCreateRequest(BaseModel):
    """Создание namespace из шаблона."""

    name: str = Field(..., description="Имя namespace")
    description: str | None = Field(default=None, description="Описание namespace")
    template_id: str = Field(
        ...,
        description="ID шаблона: sales | development | hr | ...",
    )


class NamespaceIntegrationBadge(BaseModel):
    """Статус подключения интеграции в пространстве (для UI)."""

    provider_id: str
    connected: bool


class NamespaceResponse(BaseModel):
    """Данные namespace."""

    name: str
    company_id: str
    description: str | None = None
    is_default: bool = False
    crm_settings: NamespaceCRMSettings | None = None
    integration_badges: list[NamespaceIntegrationBadge] = Field(default_factory=list)


class NamespaceUpdateRequest(BaseModel):
    """Обновление существующего namespace."""

    description: str | None = None
    allowed_type_ids: list[str] | None = None
    crm_settings: NamespaceCRMSettings | None = None


class TaskBoardStagesApiResponse(BaseModel):
    """Стадии доски задач для namespace и текущего фильтра подтипа."""

    board_key: str
    stages: list[BoardStage]


class TaskBoardEditorBoardResponse(BaseModel):
    """Одна доска в редакторе стадий пространства."""

    board_key: str
    label: str
    stages: list[BoardStage]
    uses_custom_preset: bool


class TaskBoardEditorStateResponse(BaseModel):
    """Сводка досок задач для экрана настройки namespace."""

    boards: list[TaskBoardEditorBoardResponse]


class NamespaceEditabilityResponse(BaseModel):
    """Ограничения редактирования namespace."""

    namespace: str
    has_entities: bool
    entity_count: int
    used_type_ids: list[str]
    current_allowed_type_ids: list[str]
    can_update_allowed_types: bool
    can_add_types: bool
    locked_type_ids: list[str]
    removable_type_ids: list[str]
    all_namespaces_type_ids: list[str]
    lock_reason: str | None = None


class NamespaceTemplateResponse(BaseModel):
    """Шаблон namespace."""

    template_id: str
    name: str
    description: str | None = None
    icon: str | None = None
    is_system: bool = False
    entity_type_ids: list[str]


class NamespaceTemplateCreateRequest(BaseModel):
    template_id: str
    name: str
    description: str | None = None
    icon: str | None = None


class NamespaceTemplateUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    icon: str | None = None
    crm_settings: NamespaceCRMSettings | None = None


class NamespaceTemplateTypeUpsertRequest(BaseModel):
    type_id: str
    parent_type_id: str | None = None
    name: str
    description: str | None = None
    prompt: str | None = None
    required_fields: JsonObject = Field(default_factory=dict)
    optional_fields: JsonObject = Field(default_factory=dict)
    icon: str | None = None
    color: str | None = None
    is_event: bool = False
    check_duplicates: bool = True
    weight_coefficient: float = 1.0
    namespace_ids: list[str] = Field(default_factory=list)
    is_context_anchor: bool = False
    is_voice_target: bool = False


class NamespaceTemplateTypeResponse(BaseModel):
    type_id: str
    parent_type_id: str | None = None
    name: str
    description: str | None = None
    prompt: str | None = None
    required_fields: JsonObject
    optional_fields: JsonObject
    icon: str | None = None
    color: str | None = None
    is_event: bool
    check_duplicates: bool
    weight_coefficient: float
    namespace_ids: list[str]
    is_context_anchor: bool
    is_voice_target: bool


class NamespaceTemplateDetailsResponse(BaseModel):
    template_id: str
    name: str
    description: str | None = None
    icon: str | None = None
    is_system: bool
    types: list[NamespaceTemplateTypeResponse]
    entity_type_ids: list[str]
    crm_settings: NamespaceCRMSettings | None = None


class NamespaceTemplateSchemaFieldType(BaseModel):
    type_id: str
    label: str
    supports_enum_values: bool = False
    supports_enum_set: bool = False


class NamespaceTemplateSchemaEnumSet(BaseModel):
    enum_set_id: str
    label: str
    values: list[str]


class NamespaceTemplateSchemaOperator(BaseModel):
    operator_id: str
    label: str


class NamespaceTemplateSchemaOptionsResponse(BaseModel):
    field_types: list[NamespaceTemplateSchemaFieldType]
    enum_sets: list[NamespaceTemplateSchemaEnumSet]
    operators: list[NamespaceTemplateSchemaOperator]
    defaults: JsonObject = Field(default_factory=dict)
    validation_limits: dict[str, int] = Field(default_factory=dict)


class AIExtractedEntity(BaseModel):
    """Entity извлеченная AI (без БД полей)"""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="allow")

    draft_entity_id: str | None = Field(
        default=None,
        description="Стабильный id строки черновика; выставляет только CRM после analyze",
    )
    entity_type: str
    name: str
    entity_subtype: str | None = None
    description: str | None = None
    attributes: JsonObject | None = None
    note_date: str | None = None
    confidence: float | None = None
    # Поля для tasks
    due_date: str | None = None
    priority: str | None = None
    assignees: list[str] | None = None

    # Поля дедупликации (заполняются после проверки)
    dedup_action: Literal["create", "merge"] | None = None
    dedup_existing_id: str | None = None
    dedup_existing_name: str | None = None
    dedup_confidence: float | None = None


class AIAnalyzeRelationshipExtracted(BaseModel):
    """
    Связь в сыром JSON от skill analyze (flows).
    Только текстовые концы; после ответа CRM превращает в AIAnalysisRelationshipDraft.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore")

    source_type: str
    source_name: str
    target_type: str
    target_name: str
    relationship_type: str
    weight: float
    confidence: float = Field(ge=0.0, le=1.0)
    attributes: JsonObject | None = None


class AIAnalysisRelationshipDraft(BaseModel):
    """
    Связь в ответе POST /analyze и в ai_analysis_draft.
    Концы связи только через draft_entity_id строк сущностей черновика.
    """

    draft_relationship_id: str
    source_draft_entity_id: str
    target_draft_entity_id: str
    relationship_type: str
    weight: float = 1.0
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    attributes: JsonObject | None = None


class AIAnalyzeResponse(BaseModel):
    """Результат AI анализа"""

    note: AIExtractedEntity | None = Field(
        default=None, description="Извлеченная заметка с подтипом"
    )
    entities: list[AIExtractedEntity] = Field(
        default_factory=list, description="Извлеченные entities"
    )
    relationships: list[AIAnalysisRelationshipDraft] = Field(
        default_factory=list, description="Связи черновика (только draft-id концов)"
    )
    attachment_summaries: list[JsonObject] = Field(
        default_factory=list,
        description="Резюме по каждому вложению [{filename, summary}]",
    )
    known_entity_id_map: dict[str, str] = Field(
        default_factory=dict,
        description="draft_entity_id → real entity_id для known entities (member, company)",
    )


class AIAnalysisDraftStored(BaseModel):
    """Снимок черновика analyze в attributes заметки (каноническая схема)."""

    draft_version: int
    updated_at: str
    note: AIExtractedEntity | None = None
    entities: list[AIExtractedEntity] = Field(default_factory=list)
    relationships: list[AIAnalysisRelationshipDraft] = Field(default_factory=list)
    known_entity_id_map: dict[str, str] = Field(
        default_factory=dict,
        description="draft_entity_id → real entity_id для known entities (member, company); не отображаются в UI",
    )


class DraftEntityPatch(BaseModel):
    draft_entity_id: str
    entity_type: str | None = None
    name: str | None = None
    description: str | None = None
    attributes: JsonObject | None = None
    entity_subtype: str | None = None
    note_date: str | None = None
    due_date: str | None = None
    priority: str | None = None
    assignees: list[str] | None = None


class DraftRelationshipPatch(BaseModel):
    draft_relationship_id: str
    weight: float | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    attributes: JsonObject | None = None


class AIAnalysisDraftPatchRequest(BaseModel):
    expected_version: int
    remove_entity_draft_ids: list[str] = Field(default_factory=list)
    remove_relationship_draft_ids: list[str] = Field(default_factory=list)
    patch_entities: list[DraftEntityPatch] = Field(default_factory=list)
    patch_relationships: list[DraftRelationshipPatch] = Field(default_factory=list)
    add_entities: list[AIExtractedEntity] = Field(default_factory=list)
    add_relationships: list[AIAnalysisRelationshipDraft] = Field(default_factory=list)


class AIAnalysisDraftApplyResult(BaseModel):
    created_entity_ids: list[str] = Field(default_factory=list)
    updated_entity_ids: list[str] = Field(default_factory=list)
    created_relationship_ids: list[str] = Field(default_factory=list)


class AIAnalysisDraftRepairFlowResult(BaseModel):
    """Structured output ветки CRM flow draft_repair."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    patch_entities: list[DraftEntityPatch] = Field(default_factory=list)
    repair_notes: str | None = None


class NoteAnalysisDraftRepairQueuedResponse(BaseModel):
    """Ответ POST постановки починки черновика в очередь TaskIQ."""

    note_id: str
    task_id: str
    queued: bool = True


class NoteProcessingConfig(BaseModel):
    """Конфигурация конвейера обработки заметки (analyze + apply)."""

    extract_entity_types: list[str] | None = Field(
        default=None,
        description="Типы сущностей для извлечения (None = все типы namespace)",
    )
    extract_relationship_types: list[str] | None = Field(
        default=None,
        description="Типы связей для извлечения (None = все с prompt)",
    )
    mentioned_entity_ids: list[str] | None = Field(
        default=None,
        description="ID entities, упомянутых через @",
    )
    check_duplicates: bool = Field(
        default=True,
        description="Проверять дубликаты при анализе",
    )
    include_attachments: bool = Field(
        default=True,
        description="Включать текст из attachment_ids заметки",
    )
    attachment_chars_limit_per_file: int = Field(
        default=40_000,
        ge=5_000,
        description=(
            "Порог символов для текста одного вложения. "
            "Если текст файла превышает значение — он суммаризируется LLM перед анализом."
        ),
    )


class NoteProcessingResult(BaseModel):
    """Результат полного конвейера обработки заметки (analyze + apply)."""

    note_id: str
    created_entity_ids: list[str] = Field(default_factory=list)
    updated_entity_ids: list[str] = Field(default_factory=list)
    created_relationship_ids: list[str] = Field(default_factory=list)


class DeduplicateResult(BaseModel):
    """Результат проверки на дубликат"""

    is_duplicate: bool
    confidence: float
    reason: str
    action: Literal["merge", "create"]
    existing_entity_id: str | None = None
    existing_entity_name: str | None = None
    merged_attributes: JsonObject | None = None
    merged_description: str | None = None


class LaraNamespaceSummaryResponse(BaseModel):
    """Сводка для Lara: импорты и черновики AI-анализа заметок в namespace."""

    namespace: str
    knowledge_imports_awaiting_review: int = Field(
        ...,
        ge=0,
        description="Импорты completed/failed/cancelled без review_completed_at",
    )
    knowledge_imports_in_progress: int = Field(
        ...,
        ge=0,
        description="Импорты в статусах pending или running",
    )
    notes_with_analysis_draft_not_applied: int = Field(
        ...,
        ge=0,
        description="Заметки с ai_analysis_draft и без ai_analysis_applied_at",
    )


class KnowledgeImportStartRequest(BaseModel):
    namespace: str = Field(..., description="Пространство назначения")
    mode: Literal["notes_only", "graph"] = Field(
        ...,
        description="Только заметки или нарезка + analyze/apply по каждому чанку",
    )
    source_file_id: str | None = Field(
        default=None, description="Один file_id в shared files (legacy)"
    )
    source_file_ids: list[str] | None = Field(
        default=None,
        description="Несколько file_id; можно вместе с source_text",
    )
    source_text: str | None = Field(
        default=None,
        description="Текст из мастера (лимит см. CRM knowledge import)",
    )
    extract_entity_types: list[str] | None = Field(
        default=None,
        description="Для mode=graph: типы сущностей (None = все типы пространства)",
    )
    split_by_headings: bool = Field(default=False, description="Нарезка по заголовкам markdown")
    chunk_max_chars: int = Field(default=50_000, ge=2000, le=500_000)


class KnowledgeImportResponse(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)

    import_id: str
    company_id: str
    namespace: str
    user_id: str
    mode: str
    status: str
    extract_entity_types: list[str] | None = None
    source_file_id: str | None = None
    source_file_ids: list[str] | None = None
    source_text_sha256: str | None = None
    split_by_headings: bool = False
    chunk_max_chars: int = 50_000
    taskiq_task_id: str | None = None
    notes_created_count: int = 0
    entities_created_count: int = 0
    relationships_created_count: int = 0
    created_entity_ids: list[str] = Field(default_factory=list)
    created_relationship_ids: list[str] = Field(default_factory=list)
    attachment_document_ids: list[str] = Field(default_factory=list)
    cancel_requested: bool = False
    error_message: str | None = None
    chunk_errors: list[JsonObject] | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    review_completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class KnowledgeImportCreatedEntityItem(BaseModel):
    entity_id: str
    name: str
    entity_type: str
    entity_subtype: str | None = None
    status: str


class KnowledgeImportCreatedEntitiesResponse(BaseModel):
    import_id: str
    namespace: str
    status: str
    review_completed_at: datetime | None = None
    relationships_created_count: int = 0
    entities: list[KnowledgeImportCreatedEntityItem] = Field(default_factory=list)
    missing_entity_ids: list[str] = Field(default_factory=list)


class StructuredKnowledgeImportRequest(BaseModel):
    """Запрос структурированного импорта (массовое создание без LLM)."""

    namespace: str
    entities: list[JsonObject] = Field(default_factory=list)
    relationships: list[JsonObject] = Field(default_factory=list)


# ── Unified task models ────────────────────────────────────────────────────────


class NoteMarkdownFormatQueuedResponse(BaseModel):
    """Ответ POST …/notes/{note_id}/format-markdown — задача поставлена в TaskIQ."""

    status: Literal["queued"] = "queued"
    note_id: str
    task_id: str


class TaskResponse(BaseModel):
    """Ответ с данными задачи из crm_tasks."""

    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)

    task_id: str
    task_type: str
    status: str
    stage: str
    progress_pct: int = 0
    error_message: str | None = None
    data: JsonObject = Field(default_factory=dict)
    taskiq_task_id: str | None = None
    cancel_requested: bool = False
    company_id: str
    namespace: str
    user_id: str
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class StartKnowledgeImportRequest(BaseModel):
    """Запуск импорта знаний через /tasks/knowledge-import."""

    namespace: str = Field(..., description="Пространство назначения")
    mode: Literal["notes_only", "graph"] = Field(...)
    source_file_id: str | None = Field(default=None)
    source_file_ids: list[str] | None = Field(default=None)
    source_text: str | None = Field(default=None)
    extract_entity_types: list[str] | None = Field(default=None)
    split_by_headings: bool = Field(default=False)
    chunk_max_chars: int = Field(default=50_000, ge=2000, le=500_000)


class StartNoteAnalyzeRequest(BaseModel):
    """Запуск анализа заметки через /tasks/note-analyze."""

    note_id: str
    mode: Literal["analyze", "apply", "process"] = Field(default="analyze")
    include_attachments: bool = Field(default=True)
    attachment_chars_limit_per_file: int = Field(default=40_000, ge=5_000)
    check_duplicates: bool = Field(default=True)
    extract_entity_types: list[str] | None = Field(default=None)
    extract_relationship_types: list[str] | None = Field(default=None)
    mentioned_entity_ids: list[str] | None = Field(default=None)


class TaskCreatedEntitiesResponse(BaseModel):
    """Список сущностей созданных задачей knowledge_import."""

    task_id: str
    namespace: str
    status: str
    review_completed_at: str | None = None
    relationships_created_count: int = 0
    entities: list[KnowledgeImportCreatedEntityItem] = Field(default_factory=list)
    missing_entity_ids: list[str] = Field(default_factory=list)


class StartDailySummaryRequest(BaseModel):
    """Запуск пересчёта дневной сводки через /tasks/daily-summary."""

    namespace: str = Field(..., description="Пространство назначения")
    date_str: str = Field(..., description="Дата в формате YYYY-MM-DD")
    reason: str = Field(default="manual")


class DailySummaryRequest(BaseModel):
    """Получение cached/SWR дневной сводки через /entities/daily-summary."""

    date: str = Field(..., min_length=1, description="Дата в формате YYYY-MM-DD")
    namespace: str | None = Field(default=None, description="Пространство назначения")
    force_rebuild: bool = Field(default=False)


class StartPeriodSummaryRequest(BaseModel):
    """Запуск пересчёта сводки за период через /tasks/period-summary."""

    namespace: str = Field(..., description="Пространство назначения")
    date_from: str = Field(..., description="Начало периода YYYY-MM-DD")
    date_to: str = Field(..., description="Конец периода YYYY-MM-DD")
    reason: str = Field(default="manual")


class PeriodSummaryRequest(BaseModel):
    """Получение cached/SWR сводки за период через /entities/period-summary."""

    date_from: str = Field(..., min_length=1, description="Начало периода YYYY-MM-DD")
    date_to: str = Field(..., min_length=1, description="Конец периода YYYY-MM-DD")
    namespace: str | None = Field(default=None, description="Пространство назначения")
    force_rebuild: bool = Field(default=False)
