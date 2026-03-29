"""Клиент LiveKit SFU: управление комнатами и генерация access tokens."""

from __future__ import annotations

from livekit.api import (
    AccessToken,
    CreateRoomRequest,
    DeleteRoomRequest,
    EncodedFileOutput,
    EncodedFileType,
    LiveKitAPI,
    RoomCompositeEgressRequest,
    S3Upload,
    StopEgressRequest,
    VideoGrants,
)
from livekit.protocol.egress import EgressInfo, ListEgressRequest


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

    async def list_egress(self, *, room_name: str, active: bool | None = None) -> list[EgressInfo]:
        """Возвращает egress-процессы для комнаты."""
        if room_name == "":
            raise ValueError("room_name обязателен для list_egress.")
        request = ListEgressRequest(room_name=room_name)
        if active is not None:
            request.active = active
        async with LiveKitAPI(self._api_url(), self._api_key, self._api_secret) as api:
            response = await api.egress.list_egress(request)
        return list(response.items)

    async def start_room_composite_egress_to_s3(
        self,
        *,
        room_name: str,
        filepath: str,
        s3_access_key: str,
        s3_secret_key: str,
        s3_region: str,
        s3_bucket: str,
        s3_endpoint: str | None = None,
        audio_only: bool = False,
    ) -> EgressInfo:
        """Запускает room egress и пишет файл сразу в S3."""
        if room_name == "":
            raise ValueError("room_name обязателен для старта egress.")
        if filepath == "":
            raise ValueError("filepath обязателен для старта egress.")
        if s3_access_key == "":
            raise ValueError("s3_access_key обязателен для старта egress.")
        if s3_secret_key == "":
            raise ValueError("s3_secret_key обязателен для старта egress.")
        if s3_region == "":
            raise ValueError("s3_region обязателен для старта egress.")
        if s3_bucket == "":
            raise ValueError("s3_bucket обязателен для старта egress.")

        s3_upload = S3Upload(
            access_key=s3_access_key,
            secret=s3_secret_key,
            region=s3_region,
            bucket=s3_bucket,
        )
        if s3_endpoint is not None and s3_endpoint != "":
            s3_upload.endpoint = s3_endpoint
            s3_upload.force_path_style = True

        request = RoomCompositeEgressRequest(
            room_name=room_name,
            layout="grid",
            audio_only=audio_only,
            file_outputs=[
                EncodedFileOutput(
                    file_type=EncodedFileType.MP4,
                    filepath=filepath,
                    s3=s3_upload,
                )
            ],
        )
        async with LiveKitAPI(self._api_url(), self._api_key, self._api_secret) as api:
            return await api.egress.start_room_composite_egress(request)

    async def stop_egress(self, *, egress_id: str) -> None:
        """Останавливает egress-процесс по id."""
        if egress_id == "":
            raise ValueError("egress_id обязателен для stop_egress.")
        async with LiveKitAPI(self._api_url(), self._api_key, self._api_secret) as api:
            await api.egress.stop_egress(StopEgressRequest(egress_id=egress_id))

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
