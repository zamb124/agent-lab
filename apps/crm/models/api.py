"""
Pydantic модели для API endpoints.
"""

from pydantic import BaseModel, Field, ConfigDict, model_validator
from typing import Dict, Any, List, Optional, Literal
from datetime import date, datetime

from core.models.identity_models import NamespaceCRMSettings, BoardStage


class EntityCreate(BaseModel):
    """Создание entity"""
    entity_type: str
    entity_subtype: Optional[str] = None
    namespace: str = Field(default="default", description="Namespace для изоляции")
    name: str
    description: Optional[str] = None
    attributes: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None
    attachment_ids: Optional[List[str]] = None
    user_id: Optional[str] = None

    voice_entity_id: Optional[str] = Field(
        default=None,
        description="Сущность-голос (обычно contact); null в JSON — без голоса при переданном поле",
    )
    context_entity_id: Optional[str] = Field(
        default=None,
        description="Якорь контекста; null — без привязки",
    )

    note_date: Optional[date] = None
    due_date: Optional[date] = None
    priority: Optional[str] = None
    assignees: List[str] = Field(default_factory=list)


class EntityUpdate(BaseModel):
    """Обновление entity"""
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    attributes: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None
    attachment_ids: Optional[List[str]] = None

    voice_entity_id: Optional[str] = None
    context_entity_id: Optional[str] = None

    entity_type: Optional[str] = None
    entity_subtype: Optional[str] = None

    note_date: Optional[date] = None
    due_date: Optional[date] = None
    priority: Optional[str] = None
    assignees: Optional[List[str]] = Field(default=None)


class EntityResponse(BaseModel):
    """Response с entity"""
    model_config = ConfigDict(from_attributes=True)
    
    entity_id: str
    company_id: str
    namespace: str
    entity_type: str
    entity_subtype: Optional[str]
    name: str
    description: Optional[str]
    status: str
    attributes: Dict[str, Any]
    tags: List[str]
    attachment_ids: List[str]
    
    note_date: Optional[date]
    due_date: Optional[date]
    priority: Optional[str]
    assignees: List[str]
    
    user_id: Optional[str]
    source_entity_id: Optional[str]
    source_company_id: Optional[str]
    external_relationships: List[Dict[str, Any]] = []
    relevance: float = Field(
        description="Значение CRMEntity.relevance в БД; на ранжирование результатов поиска не влияет.",
    )
    access_level: Optional[str] = None
    score: Optional[float] = Field(
        default=None,
        description="Релевантность из пайплайна поиска (semantic / text / hybrid), если запрос — поиск. Не смешивается с relevance сущности и не зависит от весов рёбер графа.",
    )
    match_type: Optional[str] = Field(
        default=None,
        description="Источник совпадения в гибридном поиске, когда применимо.",
    )

    created_at: datetime
    updated_at: datetime



class EntitySearchFilterNode(BaseModel):
    """DSL-узел фильтра поиска сущностей."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    and_nodes: Optional[List["EntitySearchFilterNode"]] = Field(default=None, alias="$and")
    or_nodes: Optional[List["EntitySearchFilterNode"]] = Field(default=None, alias="$or")
    field: Optional[str] = None
    op: Optional[str] = None
    value: Optional[Any] = None

    @model_validator(mode="after")
    def validate_shape(self) -> "EntitySearchFilterNode":
        has_and = self.and_nodes is not None
        has_or = self.or_nodes is not None
        has_leaf = self.field is not None or self.op is not None or self.value is not None

        if has_and and has_or:
            raise ValueError("Filter node cannot include both $and and $or")
        if (has_and or has_or) and has_leaf:
            raise ValueError("Logical filter node cannot include field/op/value")

        if has_and:
            if len(self.and_nodes) < 2:
                raise ValueError("$and requires at least 2 child nodes")
            return self
        if has_or:
            if len(self.or_nodes) < 2:
                raise ValueError("$or requires at least 2 child nodes")
            return self

        if self.field is None or self.op is None:
            raise ValueError("Leaf filter node requires field and op")
        if self.value is None:
            raise ValueError("Leaf filter node requires value")
        return self


EntitySearchFilterNode.model_rebuild()


class EntitySearchQueryRequest(BaseModel):
    """POST-контракт поиска/листинга сущностей через DSL-фильтры."""

    model_config = ConfigDict(extra="forbid")

    query: Optional[str] = None
    search_mode: Literal["text", "semantic", "hybrid"] = Field(
        default="hybrid",
        description="Режим поиска: только текст (FTS), только semantic (вектор), hybrid (RRF). Рёбра графа ранжирование не меняют.",
    )
    entity_type: Optional[str] = None
    entity_subtype: Optional[str] = None
    namespace: Optional[str] = None
    filters: Optional[EntitySearchFilterNode] = None
    cursor: Optional[str] = None
    limit: int = Field(default=100, ge=1, le=1000)


class BulkCreateRequest(BaseModel):
    """Batch создание сущностей (до 200)."""
    items: List["EntityCreate"]

class BulkUpdateItem(BaseModel):
    entity_id: str
    updates: Dict[str, Any]

class BulkUpdateRequest(BaseModel):
    items: List[BulkUpdateItem]

class BulkDeleteRequest(BaseModel):
    entity_ids: List[str]

class BulkErrorItem(BaseModel):
    index: int
    entity_id: Optional[str] = None
    error: str

class BulkCreateResponse(BaseModel):
    created: List[EntityResponse]
    errors: List[BulkErrorItem]

class BulkUpdateResponse(BaseModel):
    updated: List[EntityResponse]
    errors: List[BulkErrorItem]

class BulkDeleteResponse(BaseModel):
    deleted: List[str]
    errors: List[BulkErrorItem]


class BulkCardsRequest(BaseModel):
    """Batch загрузка карточек по списку entity_id."""
    entity_ids: List[str]


class EntityTimelineBoundsResponse(BaseModel):
    """Границы timeline по created_at."""
    min_created_at: Optional[datetime]
    max_created_at: Optional[datetime]
    total_entities: int


MergeSide = Literal["survivor", "source"]


class EntityMergeRequest(BaseModel):
    """Слияние source в survivor: survivor сохраняет entity_id и entity_type, source удаляется."""

    survivor_entity_id: str
    source_entity_id: str
    scalar_choices: Dict[str, MergeSide] = Field(
        default_factory=dict,
        description="Для каждого конфликтного скаляра: survivor | source",
    )
    attribute_choices: Dict[str, MergeSide] = Field(
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
    parent_type_id: Optional[str] = None
    name: str
    description: Optional[str] = None
    prompt: Optional[str] = None
    required_fields: Optional[Dict[str, Any]] = None
    optional_fields: Optional[Dict[str, Any]] = None
    icon: Optional[str] = None
    color: Optional[str] = None
    is_event: bool = False
    check_duplicates: bool = True
    is_context_anchor: bool = False
    is_voice_target: bool = False


class EntityTypeUpdate(BaseModel):
    """Обновление типа сущности"""
    name: Optional[str] = None
    description: Optional[str] = None
    parent_type_id: Optional[str] = None
    prompt: Optional[str] = None
    required_fields: Optional[Dict[str, Any]] = None
    optional_fields: Optional[Dict[str, Any]] = None
    icon: Optional[str] = None
    color: Optional[str] = None
    is_context_anchor: Optional[bool] = None
    is_voice_target: Optional[bool] = None


class EntityTypeResponse(BaseModel):
    """Response с типом сущности"""
    model_config = ConfigDict(from_attributes=True)

    type_id: str
    company_id: str
    namespace: str
    parent_type_id: Optional[str]
    name: str
    description: Optional[str]
    prompt: Optional[str]
    required_fields: Dict[str, Any]
    optional_fields: Dict[str, Any]
    public_fields: List[str]
    icon: Optional[str]
    color: Optional[str]
    is_system: bool
    is_event: bool
    check_duplicates: bool
    weight_coefficient: float
    is_context_anchor: bool
    is_voice_target: bool
    extractable: bool
    created_at: datetime
    list_entity_type: str
    list_entity_subtype: Optional[str] = None


class RelationshipTypeCreate(BaseModel):
    """Создание типа связи"""
    type_id: str
    name: str
    description: Optional[str] = None
    prompt: Optional[str] = None
    is_directed: bool = True
    inverse_type_id: Optional[str] = None
    icon: Optional[str] = None
    color: Optional[str] = None
    weight_default: float = 1.0


class RelationshipTypeResponse(BaseModel):
    """Response с типом связи"""
    model_config = ConfigDict(from_attributes=True)
    
    type_id: str
    company_id: str
    name: str
    description: Optional[str]
    prompt: Optional[str]
    is_directed: bool
    inverse_type_id: Optional[str]
    icon: Optional[str]
    color: Optional[str]
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
    attributes: Optional[Dict[str, Any]] = None


class RelationshipResponse(BaseModel):
    """Response со связью"""
    model_config = ConfigDict(from_attributes=True)
    
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
    attributes: Dict[str, Any]
    created_at: datetime
    updated_at: datetime



class SearchMentionsRequest(BaseModel):
    """Запрос на поиск упоминаний в тексте"""
    text: str = Field(description="Текст для поиска упоминаний")
    namespace: Optional[str] = Field(None, description="Namespace для ограничения поиска")


class AIAnalyzeRequest(BaseModel):
    """Запрос на AI анализ текста"""
    text: str = Field(description="Текст для анализа")
    extract_entity_types: Optional[List[str]] = Field(
        default=None,
        description="Типы для извлечения (None = все)"
    )
    extract_relationship_types: Optional[List[str]] = Field(
        default=None,
        description="Типы связей для извлечения (None = все кроме linked)"
    )
    mentioned_entity_ids: Optional[List[str]] = Field(
        default=None,
        description="ID entities, упомянутых через @"
    )
    namespace: Optional[str] = Field(
        default=None,
        description="Namespace для ограничения типов и дедупликации"
    )


class NamespaceCreateRequest(BaseModel):
    """Создание namespace из шаблона."""
    name: str = Field(..., description="Имя namespace")
    description: Optional[str] = Field(default=None, description="Описание namespace")
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
    description: Optional[str] = None
    is_default: bool = False
    crm_settings: Optional[NamespaceCRMSettings] = None
    integration_badges: List[NamespaceIntegrationBadge] = Field(default_factory=list)


class NamespaceUpdateRequest(BaseModel):
    """Обновление существующего namespace."""
    description: Optional[str] = None
    allowed_type_ids: Optional[List[str]] = None
    crm_settings: Optional[NamespaceCRMSettings] = None


class TaskBoardStagesApiResponse(BaseModel):
    """Стадии доски задач для namespace и текущего фильтра подтипа."""

    board_key: str
    stages: List[BoardStage]


class TaskBoardEditorBoardResponse(BaseModel):
    """Одна доска в редакторе стадий пространства."""

    board_key: str
    label: str
    stages: List[BoardStage]
    uses_custom_preset: bool


class TaskBoardEditorStateResponse(BaseModel):
    """Сводка досок задач для экрана настройки namespace."""

    boards: List[TaskBoardEditorBoardResponse]


class NamespaceEditabilityResponse(BaseModel):
    """Ограничения редактирования namespace."""
    namespace: str
    has_entities: bool
    entity_count: int
    used_type_ids: List[str]
    current_allowed_type_ids: List[str]
    can_update_allowed_types: bool
    can_add_types: bool
    locked_type_ids: List[str]
    removable_type_ids: List[str]
    all_spaces_type_ids: List[str]
    lock_reason: Optional[str] = None


class NamespaceTemplateResponse(BaseModel):
    """Шаблон namespace."""
    template_id: str
    name: str
    description: Optional[str] = None
    icon: Optional[str] = None
    is_system: bool = False
    entity_type_ids: List[str]


class NamespaceTemplateCreateRequest(BaseModel):
    template_id: str
    name: str
    description: Optional[str] = None
    icon: Optional[str] = None


class NamespaceTemplateUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    icon: Optional[str] = None
    crm_settings: Optional[NamespaceCRMSettings] = None


class NamespaceTemplateTypeUpsertRequest(BaseModel):
    type_id: str
    parent_type_id: Optional[str] = None
    name: str
    description: Optional[str] = None
    prompt: Optional[str] = None
    required_fields: Dict[str, Any] = Field(default_factory=dict)
    optional_fields: Dict[str, Any] = Field(default_factory=dict)
    icon: Optional[str] = None
    color: Optional[str] = None
    is_event: bool = False
    check_duplicates: bool = True
    weight_coefficient: float = 1.0
    namespace_ids: List[str] = Field(default_factory=list)
    is_context_anchor: bool = False
    is_voice_target: bool = False


class NamespaceTemplateTypeResponse(BaseModel):
    type_id: str
    parent_type_id: Optional[str] = None
    name: str
    description: Optional[str] = None
    prompt: Optional[str] = None
    required_fields: Dict[str, Any]
    optional_fields: Dict[str, Any]
    icon: Optional[str] = None
    color: Optional[str] = None
    is_event: bool
    check_duplicates: bool
    weight_coefficient: float
    namespace_ids: List[str]
    is_context_anchor: bool
    is_voice_target: bool


class NamespaceTemplateDetailsResponse(BaseModel):
    template_id: str
    name: str
    description: Optional[str] = None
    icon: Optional[str] = None
    is_system: bool
    types: List[NamespaceTemplateTypeResponse]
    entity_type_ids: List[str]
    crm_settings: Optional[NamespaceCRMSettings] = None


class NamespaceTemplateSchemaFieldType(BaseModel):
    type_id: str
    label: str
    supports_enum_values: bool = False
    supports_enum_set: bool = False


class NamespaceTemplateSchemaEnumSet(BaseModel):
    enum_set_id: str
    label: str
    values: List[str]


class NamespaceTemplateSchemaOperator(BaseModel):
    operator_id: str
    label: str


class NamespaceTemplateSchemaOptionsResponse(BaseModel):
    field_types: List[NamespaceTemplateSchemaFieldType]
    enum_sets: List[NamespaceTemplateSchemaEnumSet]
    operators: List[NamespaceTemplateSchemaOperator]
    defaults: Dict[str, Any] = Field(default_factory=dict)
    validation_limits: Dict[str, int] = Field(default_factory=dict)


class AIExtractedEntity(BaseModel):
    """Entity извлеченная AI (без БД полей)"""
    model_config = {"extra": "allow"}  # Разрешаем дополнительные поля от AI

    draft_entity_id: Optional[str] = Field(
        default=None,
        description="Стабильный id строки черновика; выставляет только CRM после analyze",
    )
    entity_type: str
    name: str
    entity_subtype: Optional[str] = None
    description: Optional[str] = None
    attributes: Optional[Dict[str, Any]] = None
    note_date: Optional[str] = None
    confidence: Optional[float] = None
    # Поля для tasks
    due_date: Optional[str] = None
    priority: Optional[str] = None
    assignees: Optional[List[str]] = None
    
    # Поля дедупликации (заполняются после проверки)
    dedup_action: Optional[Literal["create", "merge"]] = None
    dedup_existing_id: Optional[str] = None
    dedup_existing_name: Optional[str] = None
    dedup_confidence: Optional[float] = None


class AIAnalyzeRelationshipExtracted(BaseModel):
    """
    Связь в сыром JSON от skill analyze (flows).
    Только текстовые концы; после ответа CRM превращает в AIAnalysisRelationshipDraft.
    """

    model_config = ConfigDict(extra="ignore")

    source_type: str
    source_name: str
    target_type: str
    target_name: str
    relationship_type: str
    weight: float
    confidence: float = Field(ge=0.0, le=1.0)
    attributes: Optional[Dict[str, Any]] = None


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
    attributes: Optional[Dict[str, Any]] = None


class AIAnalyzeResponse(BaseModel):
    """Результат AI анализа"""
    note: Optional[AIExtractedEntity] = Field(
        default=None,
        description="Извлеченная заметка с подтипом"
    )
    entities: List[AIExtractedEntity] = Field(
        default_factory=list,
        description="Извлеченные entities"
    )
    relationships: List[AIAnalysisRelationshipDraft] = Field(
        default_factory=list,
        description="Связи черновика (только draft-id концов)"
    )
    attachment_summaries: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Резюме по каждому вложению [{filename, summary}]",
    )
    known_entity_id_map: Dict[str, str] = Field(
        default_factory=dict,
        description="draft_entity_id → real entity_id для known entities (member, company)",
    )


class AIAnalysisDraftStored(BaseModel):
    """Снимок черновика analyze в attributes заметки (каноническая схема)."""
    draft_version: int
    updated_at: str
    note: Optional[AIExtractedEntity] = None
    entities: List[AIExtractedEntity] = Field(default_factory=list)
    relationships: List[AIAnalysisRelationshipDraft] = Field(default_factory=list)
    known_entity_id_map: Dict[str, str] = Field(
        default_factory=dict,
        description="draft_entity_id → real entity_id для known entities (member, company); не отображаются в UI",
    )


class DraftEntityPatch(BaseModel):
    draft_entity_id: str
    name: Optional[str] = None
    description: Optional[str] = None
    attributes: Optional[Dict[str, Any]] = None
    entity_subtype: Optional[str] = None
    note_date: Optional[str] = None
    due_date: Optional[str] = None
    priority: Optional[str] = None
    assignees: Optional[List[str]] = None


class DraftRelationshipPatch(BaseModel):
    draft_relationship_id: str
    weight: Optional[float] = None
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    attributes: Optional[Dict[str, Any]] = None


class AIAnalysisDraftPatchRequest(BaseModel):
    expected_version: int
    remove_entity_draft_ids: List[str] = Field(default_factory=list)
    remove_relationship_draft_ids: List[str] = Field(default_factory=list)
    patch_entities: List[DraftEntityPatch] = Field(default_factory=list)
    patch_relationships: List[DraftRelationshipPatch] = Field(default_factory=list)


class AIAnalysisDraftApplyResult(BaseModel):
    created_entity_ids: List[str] = Field(default_factory=list)
    updated_entity_ids: List[str] = Field(default_factory=list)
    created_relationship_ids: List[str] = Field(default_factory=list)


class NoteProcessingConfig(BaseModel):
    """Конфигурация конвейера обработки заметки (analyze + apply)."""
    extract_entity_types: Optional[List[str]] = Field(
        default=None,
        description="Типы сущностей для извлечения (None = все типы namespace)",
    )
    extract_relationship_types: Optional[List[str]] = Field(
        default=None,
        description="Типы связей для извлечения (None = все с prompt)",
    )
    mentioned_entity_ids: Optional[List[str]] = Field(
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
    created_entity_ids: List[str] = Field(default_factory=list)
    updated_entity_ids: List[str] = Field(default_factory=list)
    created_relationship_ids: List[str] = Field(default_factory=list)


class DeduplicateResult(BaseModel):
    """Результат проверки на дубликат"""
    is_duplicate: bool
    confidence: float
    reason: str
    action: Literal["merge", "create"]
    existing_entity_id: Optional[str] = None
    existing_entity_name: Optional[str] = None
    merged_attributes: Optional[Dict[str, Any]] = None
    merged_description: Optional[str] = None


class LaraWorkspaceSummaryResponse(BaseModel):
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
    source_file_id: Optional[str] = Field(default=None, description="Один file_id в shared files (legacy)")
    source_file_ids: Optional[List[str]] = Field(
        default=None,
        description="Несколько file_id; можно вместе с source_text",
    )
    source_text: Optional[str] = Field(
        default=None,
        description="Текст из мастера (лимит см. CRM knowledge import)",
    )
    extract_entity_types: Optional[List[str]] = Field(
        default=None,
        description="Для mode=graph: типы сущностей (None = все типы пространства)",
    )
    split_by_headings: bool = Field(default=False, description="Нарезка по заголовкам markdown")
    chunk_max_chars: int = Field(default=50_000, ge=2000, le=500_000)


class KnowledgeImportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    import_id: str
    company_id: str
    namespace: str
    user_id: str
    mode: str
    status: str
    extract_entity_types: Optional[List[str]] = None
    source_file_id: Optional[str] = None
    source_file_ids: Optional[List[str]] = None
    source_text_sha256: Optional[str] = None
    split_by_headings: bool = False
    chunk_max_chars: int = 50_000
    taskiq_task_id: Optional[str] = None
    notes_created_count: int = 0
    entities_created_count: int = 0
    relationships_created_count: int = 0
    created_entity_ids: List[str] = Field(default_factory=list)
    created_relationship_ids: List[str] = Field(default_factory=list)
    attachment_document_ids: List[str] = Field(default_factory=list)
    cancel_requested: bool = False
    error_message: Optional[str] = None
    chunk_errors: Optional[List[Dict[str, Any]]] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    review_completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class KnowledgeImportCreatedEntityItem(BaseModel):
    entity_id: str
    name: str
    entity_type: str
    entity_subtype: Optional[str] = None
    status: str


class KnowledgeImportCreatedEntitiesResponse(BaseModel):
    import_id: str
    namespace: str
    status: str
    review_completed_at: Optional[datetime] = None
    relationships_created_count: int = 0
    entities: List[KnowledgeImportCreatedEntityItem] = Field(default_factory=list)
    missing_entity_ids: List[str] = Field(default_factory=list)


class StructuredKnowledgeImportRequest(BaseModel):
    """Запрос структурированного импорта (массовое создание без LLM)."""

    namespace: str
    entities: List[Dict[str, Any]] = Field(default_factory=list)
    relationships: List[Dict[str, Any]] = Field(default_factory=list)


# ── Unified task models ────────────────────────────────────────────────────────

class NoteMarkdownFormatQueuedResponse(BaseModel):
    """Ответ POST …/notes/{note_id}/format-markdown — задача поставлена в TaskIQ."""

    status: Literal["queued"] = "queued"
    note_id: str


class TaskResponse(BaseModel):
    """Ответ с данными задачи из crm_tasks."""

    model_config = ConfigDict(from_attributes=True)

    task_id: str
    task_type: str
    status: str
    stage: str
    progress_pct: int = 0
    error_message: Optional[str] = None
    data: Dict[str, Any] = Field(default_factory=dict)
    taskiq_task_id: Optional[str] = None
    cancel_requested: bool = False
    company_id: str
    namespace: str
    user_id: str
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class StartKnowledgeImportRequest(BaseModel):
    """Запуск импорта знаний через /tasks/knowledge-import."""

    namespace: str = Field(..., description="Пространство назначения")
    mode: Literal["notes_only", "graph"] = Field(...)
    source_file_id: Optional[str] = Field(default=None)
    source_file_ids: Optional[List[str]] = Field(default=None)
    source_text: Optional[str] = Field(default=None)
    extract_entity_types: Optional[List[str]] = Field(default=None)
    split_by_headings: bool = Field(default=False)
    chunk_max_chars: int = Field(default=50_000, ge=2000, le=500_000)


class StartNoteAnalyzeRequest(BaseModel):
    """Запуск анализа заметки через /tasks/note-analyze."""

    note_id: str
    mode: Literal["analyze", "apply", "process"] = Field(default="analyze")
    include_attachments: bool = Field(default=True)
    attachment_chars_limit_per_file: int = Field(default=40_000, ge=5_000)
    check_duplicates: bool = Field(default=True)
    extract_entity_types: Optional[List[str]] = Field(default=None)
    extract_relationship_types: Optional[List[str]] = Field(default=None)
    mentioned_entity_ids: Optional[List[str]] = Field(default=None)


class TaskCreatedEntitiesResponse(BaseModel):
    """Список сущностей созданных задачей knowledge_import."""

    task_id: str
    namespace: str
    status: str
    review_completed_at: Optional[str] = None
    relationships_created_count: int = 0
    entities: List[KnowledgeImportCreatedEntityItem] = Field(default_factory=list)
    missing_entity_ids: List[str] = Field(default_factory=list)


class StartDailySummaryRequest(BaseModel):
    """Запуск пересчёта дневной сводки через /tasks/daily-summary."""

    namespace: str = Field(..., description="Пространство назначения")
    date_str: str = Field(..., description="Дата в формате YYYY-MM-DD")
    reason: str = Field(default="manual")


class StartPeriodSummaryRequest(BaseModel):
    """Запуск пересчёта сводки за период через /tasks/period-summary."""

    namespace: str = Field(..., description="Пространство назначения")
    date_from: str = Field(..., description="Начало периода YYYY-MM-DD")
    date_to: str = Field(..., description="Конец периода YYYY-MM-DD")
    reason: str = Field(default="manual")

