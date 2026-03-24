"""Клиент LiveKit SFU: управление комнатами и генерация access tokens."""

from __future__ import annotations

from livekit.api import (
    AccessToken,
    CreateRoomRequest,
    DeleteRoomRequest,
    LiveKitAPI,
    VideoGrants,
)


class LiveKitClient:
    """Тонкая обёртка над livekit-api SDK для управления SFU-комнатами."""

    def __init__(self, *, url: str, api_key: str, api_secret: str) -> None:
        if not api_key:
            raise ValueError("livekit_api_key не задан в конфигурации")
        if not api_secret:
            raise ValueError("livekit_api_secret не задан в конфигурации")
        self._url = url
        self._api_key = api_key
        self._api_secret = api_secret

    def _api_url(self) -> str:
        """Преобразует ws(s):// → http(s):// для server-side Twirp API."""
        url = self._url
        if url.startswith("ws://"):
            return "http://" + url[5:]
        if url.startswith("wss://"):
            return "https://" + url[6:]
        return url

    async def create_room(self, room_name: str) -> None:
        """Создаёт LiveKit комнату. Если уже существует — не ошибка."""
        async with LiveKitAPI(self._api_url(), self._api_key, self._api_secret) as api:
            await api.room.create_room(CreateRoomRequest(name=room_name))

    async def delete_room(self, room_name: str) -> None:
        """Удаляет LiveKit комнату."""
        async with LiveKitAPI(self._api_url(), self._api_key, self._api_secret) as api:
            await api.room.delete_room(DeleteRoomRequest(room=room_name))

    def generate_token(self, *, room_name: str, identity: str, can_publish: bool = True) -> str:
        """
        Генерирует JWT access token для подключения клиента к LiveKit комнате.

        Токен подписывается api_secret и содержит VideoGrants.
        """
        grants = VideoGrants(
            room_join=True,
            room=room_name,
            can_publish=can_publish,
            can_subscribe=True,
        )
        token = (
            AccessToken(self._api_key, self._api_secret)
            .with_identity(identity)
            .with_grants(grants)
        )
        return token.to_jwt()
