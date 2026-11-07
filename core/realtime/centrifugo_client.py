"""HTTP API Centrifugo. Вызывается только из процесса realtime."""

from __future__ import annotations

import httpx2

from core.config import get_settings
from core.http import get_httpx_client
from core.logging import get_logger
from core.realtime.models import UserPresenceSnapshot
from core.types import JsonObject, JsonValue, parse_json_object, require_json_object

logger = get_logger(__name__)


def _api_key() -> str:
    key = get_settings().realtime.centrifugo_api_key
    if key is None or not key.strip():
        raise ValueError("realtime.centrifugo_api_key is required")
    return key.strip()


def _api_url(method_path: str) -> str:
    base = get_settings().realtime.centrifugo_api_url.rstrip("/")
    if not base:
        raise ValueError("realtime.centrifugo_api_url is required")
    if not method_path.startswith("/"):
        raise ValueError(f"Centrifugo API path must start with /: {method_path!r}")
    return f"{base}{method_path}"


def _headers() -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "X-API-Key": _api_key(),
    }


def _raise_for_centrifugo_payload(payload: JsonObject, *, path: str) -> JsonObject:
    error = payload.get("error")
    if error is not None:
        raise RuntimeError(f"Centrifugo {path} error: {error}")
    result = payload.get("result")
    if result is None:
        raise RuntimeError(f"Centrifugo {path}: missing result")
    return require_json_object(result, f"centrifugo.{path}.result")


async def centrifugo_publish(channel: str, data: JsonObject) -> None:
    if not channel:
        raise ValueError("Centrifugo publish channel is required")
    path = "/publish"
    async with get_httpx_client(timeout=10.0) as client:
        try:
            response = await client.post(
                _api_url(path),
                headers=_headers(),
                json={"channel": channel, "data": data},
            )
            _ = response.raise_for_status()
        except httpx2.HTTPError as exc:
            raise RuntimeError(f"Centrifugo publish failed for {channel}") from exc
    payload = parse_json_object(response.text, "centrifugo.publish.response")
    _ = _raise_for_centrifugo_payload(payload, path=path)
    logger.debug("centrifugo.published", channel=channel)


async def centrifugo_presence_stats(channel: str) -> UserPresenceSnapshot:
    if not channel.startswith("user:"):
        raise ValueError(f"presence_stats expects user: channel, got {channel!r}")
    user_id = channel.removeprefix("user:")
    if not user_id:
        raise ValueError("user channel is missing user_id")
    path = "/presence_stats"
    async with get_httpx_client(timeout=10.0) as client:
        try:
            response = await client.post(
                _api_url(path),
                headers=_headers(),
                json={"channel": channel},
            )
            _ = response.raise_for_status()
        except httpx2.HTTPError as exc:
            raise RuntimeError(f"Centrifugo presence_stats failed for {channel}") from exc
    payload = parse_json_object(response.text, "centrifugo.presence_stats.response")
    result = _raise_for_centrifugo_payload(payload, path=path)
    num_clients_value: JsonValue = result.get("num_clients")
    if not isinstance(num_clients_value, int):
        raise RuntimeError(f"Centrifugo presence_stats.num_clients must be int, got {num_clients_value!r}")
    if num_clients_value < 0:
        raise RuntimeError(f"Centrifugo presence_stats.num_clients is negative: {num_clients_value}")
    return UserPresenceSnapshot(
        user_id=user_id,
        connected=num_clients_value > 0,
        num_clients=num_clients_value,
    )


async def centrifugo_channels() -> JsonObject:
    """Метод `channels` Centrifugo API → {channel: {num_clients, ...}}."""
    path = "/channels"
    async with get_httpx_client(timeout=10.0) as client:
        try:
            response = await client.post(
                _api_url(path),
                headers=_headers(),
                json={},
            )
            _ = response.raise_for_status()
        except httpx2.HTTPError as exc:
            raise RuntimeError("Centrifugo channels failed") from exc
    payload = parse_json_object(response.text, "centrifugo.channels.response")
    return _raise_for_centrifugo_payload(payload, path=path)
