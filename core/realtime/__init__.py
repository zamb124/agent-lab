"""Публичный API слоя realtime bus."""

from core.realtime.channels import (
    BROADCAST_CHANNEL,
    SESSION_JWT_ISSUER,
    centrifugo_channels_for_delivery,
    company_channel,
    session_jwt_channels,
    session_jwt_meta,
    user_channel,
)
from core.realtime.command_owners import is_command_event_type, owner_service_for_event_type
from core.realtime.models import (
    BusProcessingState,
    CentrifugoRpcInbound,
    CentrifugoRpcResponse,
    RealtimeCommandAccepted,
    UserPresenceBatchRequest,
    UserPresenceBatchResponse,
    UserPresenceSnapshot,
)
from core.realtime.presence import fetch_user_presence, fetch_users_presence, is_user_connected
from core.realtime.submit import (
    bind_local_event_ingest,
    local_event_ingest_bound,
    submit_platform_event,
    unbind_local_event_ingest,
)

__all__ = [
    "BROADCAST_CHANNEL",
    "BusProcessingState",
    "CentrifugoRpcInbound",
    "CentrifugoRpcResponse",
    "RealtimeCommandAccepted",
    "SESSION_JWT_ISSUER",
    "UserPresenceBatchRequest",
    "UserPresenceBatchResponse",
    "UserPresenceSnapshot",
    "bind_local_event_ingest",
    "centrifugo_channels_for_delivery",
    "company_channel",
    "fetch_user_presence",
    "fetch_users_presence",
    "is_command_event_type",
    "is_user_connected",
    "local_event_ingest_bound",
    "owner_service_for_event_type",
    "session_jwt_channels",
    "session_jwt_meta",
    "submit_platform_event",
    "unbind_local_event_ingest",
    "user_channel",
]
