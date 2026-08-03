"""Pydantic input models for Sync REST client and Flows tools."""

from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

ChannelTypeLiteral = Literal["direct", "topic"]


class SyncListMessagesArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    channel_id: str = Field(
        ...,
        min_length=1,
        description="channel_id from sync_list_channels / UI context / inbox. Never invent.",
    )
    limit: int = Field(
        20,
        ge=1,
        le=200,
        description="How many root-lane messages to return (1–200).",
    )
    before: str | None = Field(
        None,
        description="Opaque cursor next_cursor — older page. Not together with after.",
    )
    after: str | None = Field(
        None,
        description="Opaque cursor prev_cursor — newer page. Not together with before.",
    )


class SyncSendMessageArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    channel_id: str = Field(
        ...,
        min_length=1,
        description="Destination channel_id. Only from tools/context.",
    )
    text: str = Field(
        ...,
        min_length=1,
        description="text/plain body (Markdown). Do not send without an explicit user request.",
    )
    thread_id: str | None = Field(
        None,
        description="thread_id for a reply in a thread. Omit — root lane.",
    )
    parent_message_id: str | None = Field(
        None,
        description="message_id being replied to in the lane (not thread_id).",
    )
    mentioned_user_ids: list[str] | None = Field(
        None,
        description=(
            "user_id participants for @mention — only from team_resolve_user / "
            "team_list_members / sync_list_channel_members."
        ),
    )


class SyncEditMessageArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    channel_id: str = Field(..., min_length=1, description="channel_id of the message.")
    message_id: str = Field(..., min_length=1, description="message_id from list/send.")
    text: str = Field(..., min_length=1, description="New text/plain body.")


class SyncDeleteMessageArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    channel_id: str = Field(..., min_length=1, description="channel_id of the message.")
    message_id: str = Field(..., min_length=1, description="message_id for soft-delete.")


class SyncReactMessageArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    channel_id: str = Field(..., min_length=1, description="channel_id of the message.")
    message_id: str = Field(..., min_length=1, description="message_id from list.")
    emoji: str | None = Field(
        None,
        description="Emoji reaction. null/omit — clear own reaction.",
    )


class SyncMarkMessageReadArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    channel_id: str = Field(..., min_length=1, description="channel_id.")
    message_id: str = Field(..., min_length=1, description="message_id for status read.")


class SyncListChannelsArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    namespace: str | None = Field(
        None,
        description="Filter by company_workspace namespace. Omit — all membership channels.",
    )
    limit: int = Field(50, ge=1, le=200, description="Limit (1–200).")
    offset: int = Field(0, ge=0, description="Pagination offset.")


class SyncListChannelMembersArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    channel_id: str = Field(
        ...,
        min_length=1,
        description="channel_id from sync_list_channels / context.",
    )


class SyncMarkChannelReadArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    channel_id: str = Field(..., min_length=1, description="channel_id for mark_read.")


class SyncCreateChannelArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    type: ChannelTypeLiteral = Field(
        ...,
        description="direct (exactly one peer in member_ids) or topic (name + namespace).",
    )
    name: str | None = Field(None, description="Topic channel name. For direct usually omit.")
    namespace: str | None = Field(
        None,
        description="Required for topic. For direct omit → default.",
    )
    member_ids: list[str] | None = Field(
        None,
        description=(
            "For direct — exactly one peer user_id from team_resolve_user. "
            "For topic — optional extra members."
        ),
    )
    is_private: bool = Field(False, description="Private topic.")


class SyncUpdateChannelArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    channel_id: str = Field(..., min_length=1, description="channel_id to update.")
    name: str | None = Field(None, description="New name. Omit — unchanged.")
    is_private: bool | None = Field(None, description="New privacy flag. Omit — unchanged.")


class SyncAddChannelMemberArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    channel_id: str = Field(..., min_length=1, description="channel_id.")
    user_id: str = Field(
        ...,
        min_length=1,
        description="user_id from team_resolve_user / team_list_members. Never invent.",
    )
    role: Literal["member", "admin"] = Field(
        "member",
        description="Member role: member|admin.",
    )


class SyncChannelNotificationSettingsArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    channel_id: str = Field(..., min_length=1, description="channel_id.")
    notifications_muted: bool = Field(
        ...,
        description="true — mute channel toasts; false — unmute.",
    )


class SyncListThreadsArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    channel_id: str = Field(..., min_length=1, description="channel_id owning the threads.")
    limit: int = Field(50, ge=1, le=200, description="Limit.")
    offset: int = Field(0, ge=0, description="Offset.")


class SyncGetThreadArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    thread_id: str = Field(..., min_length=1, description="thread_id from list/create.")


class SyncCreateThreadArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    channel_id: str = Field(
        ...,
        min_length=1,
        description="channel_id (REST path; server takes channel from root message).",
    )
    root_message_id: str = Field(
        ...,
        min_length=1,
        description="message_id of the root lane message for the new thread.",
    )
    title: str | None = Field(None, description="Optional thread title.")


class SyncListThreadMessagesArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    channel_id: str = Field(..., min_length=1, description="channel_id of the thread.")
    thread_id: str = Field(..., min_length=1, description="thread_id.")
    limit: int = Field(50, ge=1, le=200, description="Message limit.")
    offset: int = Field(0, ge=0, description="Offset.")


__all__ = [
    "ChannelTypeLiteral",
    "SyncListMessagesArgs",
    "SyncSendMessageArgs",
    "SyncEditMessageArgs",
    "SyncDeleteMessageArgs",
    "SyncReactMessageArgs",
    "SyncMarkMessageReadArgs",
    "SyncListChannelsArgs",
    "SyncListChannelMembersArgs",
    "SyncMarkChannelReadArgs",
    "SyncCreateChannelArgs",
    "SyncUpdateChannelArgs",
    "SyncAddChannelMemberArgs",
    "SyncChannelNotificationSettingsArgs",
    "SyncListThreadsArgs",
    "SyncGetThreadArgs",
    "SyncCreateThreadArgs",
    "SyncListThreadMessagesArgs",
]
