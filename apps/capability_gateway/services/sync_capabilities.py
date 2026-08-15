"""Sync SDK capabilities: definitions + SyncClient invoke helper."""

from __future__ import annotations

from collections.abc import Awaitable
from typing import TypeAlias

from pydantic import BaseModel, ValidationError

from core.capabilities import CAPABILITY_LANGUAGES, CapabilityDefinition
from core.clients.service_client import ServiceClientError
from core.clients.sync_client import SyncClient
from core.clients.sync_models import (
    SyncAddChannelMemberArgs,
    SyncChannelNotificationSettingsArgs,
    SyncCreateChannelArgs,
    SyncCreateThreadArgs,
    SyncDeleteMessageArgs,
    SyncEditMessageArgs,
    SyncGetThreadArgs,
    SyncListChannelMembersArgs,
    SyncListChannelsArgs,
    SyncListMessagesArgs,
    SyncListThreadMessagesArgs,
    SyncListThreadsArgs,
    SyncMarkChannelReadArgs,
    SyncMarkMessageReadArgs,
    SyncReactMessageArgs,
    SyncSendMessageArgs,
    SyncUpdateChannelArgs,
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
        "list_messages",
        "List Sync messages",
        "Lists root-lane messages of a Sync channel.",
        SyncListMessagesArgs,
    ),
    (
        "send_message",
        "Send Sync message",
        "Sends a text/plain Sync message as the current actor.",
        SyncSendMessageArgs,
    ),
    (
        "edit_message",
        "Edit Sync message",
        "Replaces the text of an existing Sync message.",
        SyncEditMessageArgs,
    ),
    (
        "delete_message",
        "Delete Sync message",
        "Deletes a Sync message.",
        SyncDeleteMessageArgs,
    ),
    (
        "react_message",
        "React to Sync message",
        "Adds or updates an emoji reaction on a message.",
        SyncReactMessageArgs,
    ),
    (
        "mark_message_read",
        "Mark Sync message read",
        "Marks a message as read for the current actor.",
        SyncMarkMessageReadArgs,
    ),
    (
        "list_channels",
        "List Sync channels",
        "Lists Sync channels where the current actor is a member.",
        SyncListChannelsArgs,
    ),
    (
        "list_channel_members",
        "List Sync channel members",
        "Lists members of a Sync channel.",
        SyncListChannelMembersArgs,
    ),
    (
        "mark_channel_read",
        "Mark Sync channel read",
        "Marks a channel as read for the current actor.",
        SyncMarkChannelReadArgs,
    ),
    (
        "create_channel",
        "Create Sync channel",
        "Creates a topic or direct Sync channel.",
        SyncCreateChannelArgs,
    ),
    (
        "update_channel",
        "Update Sync channel",
        "Patches channel name and/or is_private.",
        SyncUpdateChannelArgs,
    ),
    (
        "add_channel_member",
        "Add Sync channel member",
        "Adds a user to a Sync channel.",
        SyncAddChannelMemberArgs,
    ),
    (
        "channel_notification_settings",
        "Update Sync channel notifications",
        "Mutes or unmutes notifications for a channel.",
        SyncChannelNotificationSettingsArgs,
    ),
    (
        "list_threads",
        "List Sync threads",
        "Lists threads in a Sync channel.",
        SyncListThreadsArgs,
    ),
    (
        "get_thread",
        "Get Sync thread",
        "Returns a thread by thread_id.",
        SyncGetThreadArgs,
    ),
    (
        "create_thread",
        "Create Sync thread",
        "Creates a thread from a root message.",
        SyncCreateThreadArgs,
    ),
    (
        "list_thread_messages",
        "List Sync thread messages",
        "Lists messages inside a thread.",
        SyncListThreadMessagesArgs,
    ),
)

SYNC_CLIENT_METHOD_NAMES: frozenset[str] = frozenset(spec[0] for spec in SYNC_CAPABILITY_SPECS)


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
    if method == "list_messages" and isinstance(args, SyncListMessagesArgs):
        return client.list_messages(args)
    if method == "send_message" and isinstance(args, SyncSendMessageArgs):
        return client.send_message(args)
    if method == "edit_message" and isinstance(args, SyncEditMessageArgs):
        return client.edit_message(args)
    if method == "delete_message" and isinstance(args, SyncDeleteMessageArgs):
        return client.delete_message(args)
    if method == "react_message" and isinstance(args, SyncReactMessageArgs):
        return client.react_message(args)
    if method == "mark_message_read" and isinstance(args, SyncMarkMessageReadArgs):
        return client.mark_message_read(args)
    if method == "list_channels" and isinstance(args, SyncListChannelsArgs):
        return client.list_channels(args)
    if method == "list_channel_members" and isinstance(args, SyncListChannelMembersArgs):
        return client.list_channel_members(args)
    if method == "mark_channel_read" and isinstance(args, SyncMarkChannelReadArgs):
        return client.mark_channel_read(args)
    if method == "create_channel" and isinstance(args, SyncCreateChannelArgs):
        return client.create_channel(args)
    if method == "update_channel" and isinstance(args, SyncUpdateChannelArgs):
        return client.update_channel(args)
    if method == "add_channel_member" and isinstance(args, SyncAddChannelMemberArgs):
        return client.add_channel_member(args)
    if method == "channel_notification_settings" and isinstance(
        args, SyncChannelNotificationSettingsArgs
    ):
        return client.channel_notification_settings(args)
    if method == "list_threads" and isinstance(args, SyncListThreadsArgs):
        return client.list_threads(args)
    if method == "get_thread" and isinstance(args, SyncGetThreadArgs):
        return client.get_thread(args)
    if method == "create_thread" and isinstance(args, SyncCreateThreadArgs):
        return client.create_thread(args)
    if method == "list_thread_messages" and isinstance(args, SyncListThreadMessagesArgs):
        return client.list_thread_messages(args)
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
