"""CRM entity/note tools — thin wrappers over CrmClient / LaraClient.

Tag: crm. Namespace from session. Never invent entity_id.
crm_create_note uses LaraClient.propose_create_note / apply_create_note.
"""

from __future__ import annotations

from typing import Literal

from apps.flows.src.services.lara_client import LaraClient
from apps.flows.src.state import ExecutionState
from apps.flows.src.tools.decorator import tool
from core.clients.crm_client import CrmClient
from core.clients.crm_models import (
    CrmAnalyzeNoteTextArgs,
    CrmApplyAnalysisDraftArgs,
    CrmCreateActivityTaskArgs,
    CrmCreateEntityArgs,
    CrmCreateNoteAndAnalyzeArgs,
    CrmCreateNoteArgs,
    CrmCreateRelationshipArgs,
    CrmDailySummaryArgs,
    CrmDeleteEntityArgs,
    CrmDiscardAnalysisDraftArgs,
    CrmGetEntityArgs,
    CrmListActivityTasksArgs,
    CrmListEntityTypesArgs,
    CrmListNotesArgs,
    CrmMergeEntitiesArgs,
    CrmPeriodSummaryArgs,
    CrmSearchEntitiesArgs,
    CrmUpdateEntityArgs,
)
from core.types import JsonObject

_TAGS = ["crm"]
_TAGS_ACTIVITY = ["crm", "worktracker"]


@tool(
    name="crm_search_entities",
    description=(
        "Гибридный поиск по сущностям CRM (полнотекст + семантика, как строка «Поиск» в списке сущностей). "
        "Не добавляй фильтры по типу или пространству, если пользователь об этом не просил. "
        "Ответ — JSON: hits и blocks для чата."
    ),
    tags=_TAGS,
    parameters_model=CrmSearchEntitiesArgs,
)
async def crm_search_entities(
    query: str,
    entity_type: str | None = None,
    entity_subtype: str | None = None,
    namespace: str | None = None,
    limit: int = 100,
    *,
    state: ExecutionState,
) -> JsonObject:
    _ = state
    return await CrmClient().search_entities(
        query=query,
        entity_type=entity_type,
        entity_subtype=entity_subtype,
        namespace=namespace,
        limit=limit,
    )


@tool(
    name="crm_create_note",
    description=(
        "Создаёт заметку в CRM NetWorkle. Передай name (заголовок), description (текст). "
        "note_date — ISO дата YYYY-MM-DD (опционально). namespace — опционально, иначе берётся из контекста. "
        "Возвращает JSON: entity, blocks (карточка для чата)."
    ),
    tags=_TAGS,
    parameters_model=CrmCreateNoteArgs,
)
async def crm_create_note(
    name: str | None = None,
    description: str | None = None,
    note_date: str | None = None,
    namespace: str | None = None,
    mode: Literal["propose", "apply"] = "propose",
    pending_action_id: str | None = None,
    idempotency_key: str | None = None,
    *,
    state: ExecutionState,
    lara_client: LaraClient,
) -> JsonObject:
    client = lara_client
    clean_note_date = str(note_date).strip() if note_date and str(note_date).strip() else None

    if mode == "propose":
        if name is None or description is None:
            raise ValueError("name and description are required for mode=propose")
        return await client.propose_create_note(
            name=name,
            description=description,
            note_date=clean_note_date,
            namespace=namespace,
            state=state,
            idempotency_key=idempotency_key,
        )

    if not pending_action_id:
        raise ValueError("pending_action_id is required for mode=apply")
    return await client.apply_create_note(
        pending_action_id=pending_action_id,
        state=state,
        idempotency_key=idempotency_key,
    )


@tool(
    name="crm_create_note_and_analyze",
    description=(
        "Создаёт заметку в CRM и сразу запускает AI-анализ того же текста (извлечение сущностей). "
        "Передай name, description. Опционально note_date (YYYY-MM-DD), extract_entity_types, mentioned_entity_ids, namespace."
    ),
    tags=_TAGS,
    parameters_model=CrmCreateNoteAndAnalyzeArgs,
)
async def crm_create_note_and_analyze(
    name: str,
    description: str,
    note_date: str | None = None,
    extract_entity_types: list[str] | None = None,
    mentioned_entity_ids: list[str] | None = None,
    namespace: str | None = None,
    *,
    state: ExecutionState,
) -> JsonObject:
    _ = state
    return await CrmClient().create_note_and_analyze(
        name=name,
        description=description,
        note_date=note_date,
        extract_entity_types=extract_entity_types,
        mentioned_entity_ids=mentioned_entity_ids,
        namespace=namespace,
    )


@tool(
    name="crm_analyze_note_text",
    description=(
        "Запускает AI-анализ заметки (mode=analyze): пишет ai_analysis_draft, "
        "не применяет изменения в граф. Обязательно: note_id. "
        "После согласия пользователя — crm_apply_analysis_draft или crm_discard_analysis_draft. "
        "Не вызывать без явного согласия на анализ."
    ),
    tags=_TAGS,
    parameters_model=CrmAnalyzeNoteTextArgs,
)
async def crm_analyze_note_text(
    note_id: str,
    extract_entity_types: list[str] | None = None,
    mentioned_entity_ids: list[str] | None = None,
    *,
    state: ExecutionState,
) -> JsonObject:
    _ = state
    return await CrmClient().analyze_note_text(
        note_id=note_id,
        extract_entity_types=extract_entity_types,
        mentioned_entity_ids=mentioned_entity_ids,
    )


@tool(
    name="crm_get_entity",
    description=(
        "Загружает сущность CRM по entity_id (GET /crm/api/v1/entities/{id}). "
        "Возвращает JSON и card-блок для чата."
    ),
    tags=_TAGS,
    parameters_model=CrmGetEntityArgs,
)
async def crm_get_entity(entity_id: str, *, state: ExecutionState) -> JsonObject:
    _ = state
    return await CrmClient().get_entity(entity_id)


@tool(
    name="crm_create_entity",
    description=(
        "Создаёт сущность CRM (POST /crm/api/v1/entities): entity_type и name обязательны. "
        "namespace берётся из active_namespace если не указан. Для confirm-first заметок используй crm_create_note."
    ),
    tags=_TAGS,
    parameters_model=CrmCreateEntityArgs,
)
async def crm_create_entity(
    entity_type: str,
    name: str,
    entity_subtype: str | None = None,
    namespace: str | None = None,
    description: str | None = None,
    attributes: JsonObject | None = None,
    tags: list[str] | None = None,
    *,
    state: ExecutionState,
) -> JsonObject:
    _ = state
    return await CrmClient().create_entity(
        entity_type=entity_type,
        name=name,
        entity_subtype=entity_subtype,
        namespace=namespace,
        description=description,
        attributes=attributes,
        tags=tags,
    )


@tool(
    name="crm_create_relationship",
    description=("Создаёт связь (POST /crm/api/v1/relationships между source и target)."),
    tags=_TAGS,
    parameters_model=CrmCreateRelationshipArgs,
)
async def crm_create_relationship(
    source_entity_id: str,
    target_entity_id: str,
    relationship_type: str,
    namespace: str | None = None,
    weight: float = 1.0,
    confidence: float = 1.0,
    *,
    state: ExecutionState,
) -> JsonObject:
    _ = state
    return await CrmClient().create_relationship(
        source_entity_id=source_entity_id,
        target_entity_id=target_entity_id,
        relationship_type=relationship_type,
        namespace=namespace,
        weight=weight,
        confidence=confidence,
    )


@tool(
    name="crm_list_entity_types",
    description=("Каталог типов для namespace (GET /crm/api/v1/entity-types?namespace=)."),
    tags=_TAGS,
    parameters_model=CrmListEntityTypesArgs,
)
async def crm_list_entity_types(
    namespace: str | None = None,
    *,
    state: ExecutionState,
) -> JsonObject:
    _ = state
    return await CrmClient().list_entity_types(namespace=namespace)


@tool(
    name="crm_daily_summary",
    description=(
        "Сводка заметок за один день "
        "(POST /crm/api/v1/entities/daily-summary, date YYYY-MM-DD). "
        "Для диапазона дат — crm_period_summary."
    ),
    tags=_TAGS,
    parameters_model=CrmDailySummaryArgs,
)
async def crm_daily_summary(
    date: str,
    namespace: str | None = None,
    force_rebuild: bool = False,
    *,
    state: ExecutionState,
) -> JsonObject:
    _ = state
    return await CrmClient().daily_summary(
        date=date,
        namespace=namespace,
        force_rebuild=force_rebuild,
    )


@tool(
    name="crm_update_entity",
    description=(
        "Updates a CRM entity (PUT /crm/api/v1/entities/{entity_id}). "
        "Pass only fields to change. Never invent entity_id."
    ),
    tags=_TAGS,
    parameters_model=CrmUpdateEntityArgs,
)
async def crm_update_entity(
    entity_id: str,
    name: str | None = None,
    description: str | None = None,
    status: str | None = None,
    entity_type: str | None = None,
    entity_subtype: str | None = None,
    tags: list[str] | None = None,
    note_date: str | None = None,
    *,
    state: ExecutionState,
) -> JsonObject:
    _ = state
    return await CrmClient().update_entity(
        entity_id=entity_id,
        name=name,
        description=description,
        status=status,
        entity_type=entity_type,
        entity_subtype=entity_subtype,
        tags=tags,
        note_date=note_date,
    )


@tool(
    name="crm_delete_entity",
    description=(
        "Cascade-deletes a CRM entity "
        "(DELETE /crm/api/v1/entities/{entity_id}). Confirm with the user first."
    ),
    tags=_TAGS,
    parameters_model=CrmDeleteEntityArgs,
)
async def crm_delete_entity(entity_id: str, *, state: ExecutionState) -> JsonObject:
    _ = state
    return await CrmClient().delete_entity(entity_id)


@tool(
    name="crm_list_notes",
    description=(
        "Lists CRM notes by note_date range "
        "(POST /crm/api/v1/entities/query, entity_type=note). "
        "date_from required; date_to optional (defaults to date_from)."
    ),
    tags=_TAGS,
    parameters_model=CrmListNotesArgs,
)
async def crm_list_notes(
    date_from: str,
    date_to: str | None = None,
    namespace: str | None = None,
    query: str | None = None,
    limit: int = 50,
    cursor: str | None = None,
    *,
    state: ExecutionState,
) -> JsonObject:
    _ = state
    return await CrmClient().list_notes(
        date_from=date_from,
        date_to=date_to,
        namespace=namespace,
        query=query,
        limit=limit,
        cursor=cursor,
    )


@tool(
    name="crm_apply_analysis_draft",
    description=(
        "Applies note AI analysis draft to the CRM graph "
        "(POST /crm/api/v1/tasks/note-analyze mode=apply). "
        "Use after crm_analyze_note_text when the user accepts the draft. Analyze ≠ apply."
    ),
    tags=_TAGS,
    parameters_model=CrmApplyAnalysisDraftArgs,
)
async def crm_apply_analysis_draft(note_id: str, *, state: ExecutionState) -> JsonObject:
    _ = state
    return await CrmClient().apply_analysis_draft(note_id)


@tool(
    name="crm_discard_analysis_draft",
    description=(
        "Discards note AI analysis draft without applying "
        "(DELETE /crm/api/v1/entities/notes/{note_id}/analysis-draft)."
    ),
    tags=_TAGS,
    parameters_model=CrmDiscardAnalysisDraftArgs,
)
async def crm_discard_analysis_draft(note_id: str, *, state: ExecutionState) -> JsonObject:
    _ = state
    return await CrmClient().discard_analysis_draft(note_id)


@tool(
    name="crm_merge_entities",
    description=(
        "Merges source entity into survivor "
        "(POST /crm/api/v1/entities/merge). Survivor keeps entity_id; source is deleted."
    ),
    tags=_TAGS,
    parameters_model=CrmMergeEntitiesArgs,
)
async def crm_merge_entities(
    survivor_entity_id: str,
    source_entity_id: str,
    *,
    state: ExecutionState,
) -> JsonObject:
    _ = state
    return await CrmClient().merge_entities(
        survivor_entity_id=survivor_entity_id,
        source_entity_id=source_entity_id,
    )


@tool(
    name="crm_period_summary",
    description=(
        "Period notes summary "
        "(POST /crm/api/v1/entities/period-summary, date_from/date_to YYYY-MM-DD)."
    ),
    tags=_TAGS,
    parameters_model=CrmPeriodSummaryArgs,
)
async def crm_period_summary(
    date_from: str,
    date_to: str,
    namespace: str | None = None,
    force_rebuild: bool = False,
    *,
    state: ExecutionState,
) -> JsonObject:
    _ = state
    return await CrmClient().period_summary(
        date_from=date_from,
        date_to=date_to,
        namespace=namespace,
        force_rebuild=force_rebuild,
    )


@tool(
    name="crm_create_activity_task",
    description=(
        "Creates CRM activity task pair: CRMEntity(task) + WorkItem(crm_activity) "
        "(POST /crm/api/v1/activity-tasks). Returns entity_id and work_item_id. "
        "Further work mutations — load work-items tools."
    ),
    tags=_TAGS_ACTIVITY,
    parameters_model=CrmCreateActivityTaskArgs,
)
async def crm_create_activity_task(
    title: str,
    description: str | None = None,
    namespace: str | None = None,
    entity_subtype: str | None = None,
    priority: str | None = None,
    due_date: str | None = None,
    assignees: list[str] | None = None,
    tags: list[str] | None = None,
    *,
    state: ExecutionState,
) -> JsonObject:
    _ = state
    return await CrmClient().create_activity_task(
        title=title,
        description=description,
        namespace=namespace,
        entity_subtype=entity_subtype,
        priority=priority,
        due_date=due_date,
        assignees=assignees,
        tags=tags,
    )


@tool(
    name="crm_list_activity_tasks",
    description=(
        "Lists CRM activity WorkItems "
        "(GET /crm/api/v1/activity-tasks). For state/board mutations use work_item_* tools."
    ),
    tags=_TAGS_ACTIVITY,
    parameters_model=CrmListActivityTasksArgs,
)
async def crm_list_activity_tasks(
    namespace: str | None = None,
    work_item_state: str | None = None,
    limit: int = 50,
    offset: int = 0,
    *,
    state: ExecutionState,
) -> JsonObject:
    _ = state
    return await CrmClient().list_activity_tasks(
        namespace=namespace,
        work_item_state=work_item_state,
        limit=limit,
        offset=offset,
    )
