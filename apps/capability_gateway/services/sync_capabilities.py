"""Sync SDK capabilities: definitions + SyncClient invoke helper (hot-path subset)."""

from __future__ import annotations

from collections.abc import Awaitable
from typing import TypeAlias

from pydantic import BaseModel, ValidationError

from core.capabilities import CAPABILITY_LANGUAGES, CapabilityDefinition
from core.clients.service_client import ServiceClientError
from core.clients.sync_client import SyncClient
from core.clients.sync_models import (
    SyncListChannelsArgs,
    SyncListMessagesArgs,
    SyncListThreadsArgs,
    SyncSendMessageArgs,
)
from core.types import JsonObject, JsonValue, require_json_object

SyncArgsModel: TypeAlias = type[BaseModel]

_SYNC_OUTPUT_SCHEMA: JsonObject = {
    "type": "object",
    "description": "Brief JSON from SyncClient (product-level fields, no HTTP envelope).",
}


def _input_schema(model: SyncArgsModel) -> JsonObject:
    return require_json_object(model.model_json_schema(), f"{model.__name__}.json_schema")


def _definition(
    *,
    method: str,
    title: str,
    description: str,
    args_model: SyncArgsModel,
) -> CapabilityDefinition:
    return CapabilityDefinition(
        name=f"sync.{method}",
        title=title,
        description=description,
        input_schema=_input_schema(args_model),
        output_schema=_SYNC_OUTPUT_SCHEMA,
        languages=list(CAPABILITY_LANGUAGES),
        tags=["sync"],
        sdk_namespace="sync",
        sdk_method=method,
    )


SYNC_CAPABILITY_SPECS: tuple[tuple[str, str, str, SyncArgsModel], ...] = (
    (
        "list_channels",
        "List Sync channels",
        "Lists Sync channels where the current actor is a member.",
        SyncListChannelsArgs,
    ),
    (
        "send_message",
        "Send Sync message",
        "Sends a text/plain Sync message as the current actor.",
        SyncSendMessageArgs,
    ),
    (
        "list_messages",
        "List Sync messages",
        "Lists root-lane messages of a Sync channel.",
        SyncListMessagesArgs,
    ),
    (
        "list_threads",
        "List Sync threads",
        "Lists threads in a Sync channel.",
        SyncListThreadsArgs,
    ),
)


def sync_capability_definitions() -> dict[str, CapabilityDefinition]:
    return {
        f"sync.{method}": _definition(
            method=method,
            title=title,
            description=description,
            args_model=args_model,
        )
        for method, title, description, args_model in SYNC_CAPABILITY_SPECS
    }


def sync_args_model_for(method: str) -> SyncArgsModel:
    for spec_method, _title, _description, args_model in SYNC_CAPABILITY_SPECS:
        if spec_method == method:
            return args_model
    raise ValueError(f"Unknown sync capability method: {method}")


def _sync_method_call(method: str, args: BaseModel) -> Awaitable[JsonObject]:
    client = SyncClient()
    if method == "list_channels" and isinstance(args, SyncListChannelsArgs):
        return client.list_channels(args)
    if method == "send_message" and isinstance(args, SyncSendMessageArgs):
        return client.send_message(args)
    if method == "list_messages" and isinstance(args, SyncListMessagesArgs):
        return client.list_messages(args)
    if method == "list_threads" and isinstance(args, SyncListThreadsArgs):
        return client.list_threads(args)
    raise ValueError(f"Unsupported sync capability invoke: {method}")


async def invoke_sync_client(method: str, kwargs: JsonObject) -> JsonValue:
    """Parse kwargs with the method's model and call SyncClient (Context must be active)."""
    args_model = sync_args_model_for(method)
    try:
        args = args_model.model_validate(kwargs)
    except ValidationError as exc:
        raise ValueError(str(exc)) from exc
    try:
        return await _sync_method_call(method, args)
    except ServiceClientError as exc:
        raise ValueError(str(exc)) from exc
