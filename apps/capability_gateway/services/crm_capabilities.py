"""CRM SDK capabilities: definitions + CrmClient invoke helper."""

from __future__ import annotations

from collections.abc import Awaitable
from typing import TypeAlias

from pydantic import BaseModel, ValidationError

from core.capabilities import CAPABILITY_LANGUAGES, CapabilityDefinition
from core.clients.crm_client import CrmClient
from core.clients.crm_models import (
    CrmAnalyzeNoteTextArgs,
    CrmApplyAnalysisDraftArgs,
    CrmCapabilityCreateNoteArgs,
    CrmCreateActivityTaskArgs,
    CrmCreateEntityArgs,
    CrmCreateNoteAndAnalyzeArgs,
    CrmCreateRelationshipArgs,
    CrmDailySummaryArgs,
    CrmDeleteEntityArgs,
    CrmDeleteRelationshipArgs,
    CrmDiscardAnalysisDraftArgs,
    CrmEntityRelatedArgs,
    CrmGetEntityArgs,
    CrmKnowledgeImportStatusArgs,
    CrmListActivityTasksArgs,
    CrmListEntityTypesArgs,
    CrmListNotesArgs,
    CrmListRelationshipsArgs,
    CrmListRelationshipTypesArgs,
    CrmListSuggestsArgs,
    CrmMergeEntitiesArgs,
    CrmPeriodSummaryArgs,
    CrmSearchEntitiesArgs,
    CrmShortestPathArgs,
    CrmSuggestIdArgs,
    CrmUpdateEntityArgs,
)
from core.clients.service_client import ServiceClientError
from core.types import JsonObject, JsonValue, require_json_object

CrmArgsModel: TypeAlias = type[BaseModel]

_CRM_OUTPUT_SCHEMA: JsonObject = {
    "type": "object",
    "description": "Brief JSON from CrmClient (product-level fields, no HTTP envelope).",
}


def _input_schema(model: CrmArgsModel) -> JsonObject:
    return require_json_object(model.model_json_schema(), f"{model.__name__}.json_schema")


def _definition(
    *,
    method: str,
    title: str,
    description: str,
    args_model: CrmArgsModel,
) -> CapabilityDefinition:
    return CapabilityDefinition(
        name=f"crm.{method}",
        title=title,
        description=description,
        input_schema=_input_schema(args_model),
        output_schema=_CRM_OUTPUT_SCHEMA,
        languages=list(CAPABILITY_LANGUAGES),
        tags=["crm"],
        sdk_namespace="crm",
        sdk_method=method,
    )


CRM_CAPABILITY_SPECS: tuple[tuple[str, str, str, CrmArgsModel], ...] = (
    (
        "search_entities",
        "Search CRM entities",
        "Hybrid entity search (text + semantic). Prefer short keyword queries.",
        CrmSearchEntitiesArgs,
    ),
    (
        "get_entity",
        "Get CRM entity",
        "Returns entity JSON and chat card blocks for entity_id.",
        CrmGetEntityArgs,
    ),
    (
        "create_entity",
        "Create CRM entity",
        "Creates a CRM entity in the active namespace.",
        CrmCreateEntityArgs,
    ),
    (
        "update_entity",
        "Update CRM entity",
        "Patches name, description, status, type, tags or note_date.",
        CrmUpdateEntityArgs,
    ),
    (
        "delete_entity",
        "Delete CRM entity",
        "Deletes an entity by entity_id.",
        CrmDeleteEntityArgs,
    ),
    (
        "merge_entities",
        "Merge CRM entities",
        "Merges source_entity_id into survivor_entity_id.",
        CrmMergeEntitiesArgs,
    ),
    (
        "create_note",
        "Create CRM note",
        "Creates a note entity in the active namespace (no Lara confirmation).",
        CrmCapabilityCreateNoteArgs,
    ),
    (
        "create_note_and_analyze",
        "Create CRM note and analyze",
        "Creates a note and runs note-analyze in one call.",
        CrmCreateNoteAndAnalyzeArgs,
    ),
    (
        "analyze_note_text",
        "Analyze CRM note",
        "Runs note-analyze on an existing note_id.",
        CrmAnalyzeNoteTextArgs,
    ),
    (
        "list_notes",
        "List CRM notes",
        "Lists notes by note_date range. date_from required; date_to optional.",
        CrmListNotesArgs,
    ),
    (
        "apply_analysis_draft",
        "Apply CRM note analysis draft",
        "Applies the pending analysis draft for a note.",
        CrmApplyAnalysisDraftArgs,
    ),
    (
        "discard_analysis_draft",
        "Discard CRM note analysis draft",
        "Discards the pending analysis draft for a note.",
        CrmDiscardAnalysisDraftArgs,
    ),
    (
        "list_entity_types",
        "List CRM entity types",
        "Lists entity types available in the namespace.",
        CrmListEntityTypesArgs,
    ),
    (
        "daily_summary",
        "CRM daily summary",
        "Builds or returns the daily notes summary for a date.",
        CrmDailySummaryArgs,
    ),
    (
        "period_summary",
        "CRM period summary",
        "Builds or returns a notes summary for a date range.",
        CrmPeriodSummaryArgs,
    ),
    (
        "create_activity_task",
        "Create CRM activity task",
        "Creates a CRM task entity with a paired WorkItem.",
        CrmCreateActivityTaskArgs,
    ),
    (
        "list_activity_tasks",
        "List CRM activity tasks",
        "Lists activity tasks in the namespace.",
        CrmListActivityTasksArgs,
    ),
    (
        "create_relationship",
        "Create CRM relationship",
        "Creates a relationship between two entities.",
        CrmCreateRelationshipArgs,
    ),
    (
        "list_relationships",
        "List CRM relationships",
        "Lists relationships, optionally filtered by entity_id.",
        CrmListRelationshipsArgs,
    ),
    (
        "delete_relationship",
        "Delete CRM relationship",
        "Deletes a relationship by relationship_id.",
        CrmDeleteRelationshipArgs,
    ),
    (
        "list_relationship_types",
        "List CRM relationship types",
        "Lists relationship types in the company catalog.",
        CrmListRelationshipTypesArgs,
    ),
    (
        "entity_related",
        "List related CRM entities",
        "Lists entities related to entity_id.",
        CrmEntityRelatedArgs,
    ),
    (
        "shortest_path",
        "CRM shortest path",
        "Finds a shortest relationship path between two entities.",
        CrmShortestPathArgs,
    ),
    (
        "list_suggests",
        "List CRM suggests",
        "Lists AI suggests in the namespace.",
        CrmListSuggestsArgs,
    ),
    (
        "resolve_suggest",
        "Resolve CRM suggest",
        "Resolves a suggest by suggest_id.",
        CrmSuggestIdArgs,
    ),
    (
        "dismiss_suggest",
        "Dismiss CRM suggest",
        "Dismisses a suggest by suggest_id.",
        CrmSuggestIdArgs,
    ),
    (
        "knowledge_import_status",
        "CRM knowledge import status",
        "Returns knowledge-import job status for the namespace.",
        CrmKnowledgeImportStatusArgs,
    ),
)

CRM_CLIENT_METHOD_NAMES: frozenset[str] = frozenset(spec[0] for spec in CRM_CAPABILITY_SPECS)


def crm_capability_definitions() -> dict[str, CapabilityDefinition]:
    return {
        f"crm.{method}": _definition(
            method=method,
            title=title,
            description=description,
            args_model=args_model,
        )
        for method, title, description, args_model in CRM_CAPABILITY_SPECS
    }


def crm_args_model_for(method: str) -> CrmArgsModel:
    for spec_method, _title, _description, args_model in CRM_CAPABILITY_SPECS:
        if spec_method == method:
            return args_model
    raise ValueError(f"Unknown crm capability method: {method}")


def _crm_method_call(method: str, args: BaseModel) -> Awaitable[JsonObject]:
    client = CrmClient()
    if method == "search_entities" and isinstance(args, CrmSearchEntitiesArgs):
        return client.search_entities(args)
    if method == "get_entity" and isinstance(args, CrmGetEntityArgs):
        return client.get_entity(args)
    if method == "create_entity" and isinstance(args, CrmCreateEntityArgs):
        return client.create_entity(args)
    if method == "update_entity" and isinstance(args, CrmUpdateEntityArgs):
        return client.update_entity(args)
    if method == "delete_entity" and isinstance(args, CrmDeleteEntityArgs):
        return client.delete_entity(args)
    if method == "merge_entities" and isinstance(args, CrmMergeEntitiesArgs):
        return client.merge_entities(args)
    if method == "create_note" and isinstance(args, CrmCapabilityCreateNoteArgs):
        return client.create_note(args)
    if method == "create_note_and_analyze" and isinstance(args, CrmCreateNoteAndAnalyzeArgs):
        return client.create_note_and_analyze(args)
    if method == "analyze_note_text" and isinstance(args, CrmAnalyzeNoteTextArgs):
        return client.analyze_note_text(args)
    if method == "list_notes" and isinstance(args, CrmListNotesArgs):
        return client.list_notes(args)
    if method == "apply_analysis_draft" and isinstance(args, CrmApplyAnalysisDraftArgs):
        return client.apply_analysis_draft(args)
    if method == "discard_analysis_draft" and isinstance(args, CrmDiscardAnalysisDraftArgs):
        return client.discard_analysis_draft(args)
    if method == "list_entity_types" and isinstance(args, CrmListEntityTypesArgs):
        return client.list_entity_types(args)
    if method == "daily_summary" and isinstance(args, CrmDailySummaryArgs):
        return client.daily_summary(args)
    if method == "period_summary" and isinstance(args, CrmPeriodSummaryArgs):
        return client.period_summary(args)
    if method == "create_activity_task" and isinstance(args, CrmCreateActivityTaskArgs):
        return client.create_activity_task(args)
    if method == "list_activity_tasks" and isinstance(args, CrmListActivityTasksArgs):
        return client.list_activity_tasks(args)
    if method == "create_relationship" and isinstance(args, CrmCreateRelationshipArgs):
        return client.create_relationship(args)
    if method == "list_relationships" and isinstance(args, CrmListRelationshipsArgs):
        return client.list_relationships(args)
    if method == "delete_relationship" and isinstance(args, CrmDeleteRelationshipArgs):
        return client.delete_relationship(args)
    if method == "list_relationship_types" and isinstance(args, CrmListRelationshipTypesArgs):
        return client.list_relationship_types(args)
    if method == "entity_related" and isinstance(args, CrmEntityRelatedArgs):
        return client.entity_related(args)
    if method == "shortest_path" and isinstance(args, CrmShortestPathArgs):
        return client.shortest_path(args)
    if method == "list_suggests" and isinstance(args, CrmListSuggestsArgs):
        return client.list_suggests(args)
    if method == "resolve_suggest" and isinstance(args, CrmSuggestIdArgs):
        return client.resolve_suggest(args)
    if method == "dismiss_suggest" and isinstance(args, CrmSuggestIdArgs):
        return client.dismiss_suggest(args)
    if method == "knowledge_import_status" and isinstance(args, CrmKnowledgeImportStatusArgs):
        return client.knowledge_import_status(args)
    raise ValueError(f"Unsupported crm capability invoke: {method}")


async def invoke_crm_client(method: str, kwargs: JsonObject) -> JsonValue:
    """Parse kwargs with the method's model and call CrmClient (Context must be active)."""
    args_model = crm_args_model_for(method)
    try:
        args = args_model.model_validate(kwargs)
    except ValidationError as exc:
        raise ValueError(str(exc)) from exc
    try:
        return await _crm_method_call(method, args)
    except ServiceClientError as exc:
        raise ValueError(str(exc)) from exc
