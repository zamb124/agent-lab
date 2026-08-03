"""CRM SDK capabilities: definitions + CrmClient invoke helper (hot-path subset)."""

from __future__ import annotations

from collections.abc import Awaitable
from typing import TypeAlias

from pydantic import BaseModel, ValidationError

from core.capabilities import CAPABILITY_LANGUAGES, CapabilityDefinition
from core.clients.crm_client import CrmClient
from core.clients.crm_models import (
    CrmCapabilityCreateNoteArgs,
    CrmGetEntityArgs,
    CrmListNotesArgs,
    CrmSearchEntitiesArgs,
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
        "create_note",
        "Create CRM note",
        "Creates a note entity in the active namespace (no Lara confirmation).",
        CrmCapabilityCreateNoteArgs,
    ),
    (
        "list_notes",
        "List CRM notes",
        "Lists notes by note_date range. date_from required; date_to optional.",
        CrmListNotesArgs,
    ),
)


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
    if method == "create_note" and isinstance(args, CrmCapabilityCreateNoteArgs):
        return client.create_note(
            name=args.name,
            description=args.description,
            note_date=args.note_date,
            namespace=args.namespace,
        )
    if method == "list_notes" and isinstance(args, CrmListNotesArgs):
        return client.list_notes(args)
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
