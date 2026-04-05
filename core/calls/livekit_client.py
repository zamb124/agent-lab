"""Клиент LiveKit SFU: управление комнатами и генерация access tokens."""

from __future__ import annotations

from typing import Any

from livekit.api import (
    AccessToken,
    AudioCodec,
    CreateRoomRequest,
    DeleteRoomRequest,
    EncodedFileOutput,
    EncodedFileType,
    EncodingOptions,
    LiveKitAPI,
    RoomCompositeEgressRequest,
    S3Upload,
    SegmentedFileOutput,
    SegmentedFileProtocol,
    SegmentedFileSuffix,
    StopEgressRequest,
    TrackCompositeEgressRequest,
    VideoGrants,
)
from livekit.protocol.egress import EgressInfo, ListEgressRequest

from core.models.billing_models import UsageType
from core.tracing import attributes as trace_attributes
from core.tracing.operation_span import traced_operation


def _livekit_traced_attrs(
    *,
    company_id: str,
    user_id: str,
    base: dict[str, Any],
) -> dict[str, Any]:
    cid = company_id.strip()
    uid = user_id.strip()
    if cid == "":
        raise ValueError("company_id обязателен для трейсируемой операции LiveKit.")
    if uid == "":
        raise ValueError("user_id обязателен для трейсируемой операции LiveKit.")
    return {
        trace_attributes.ATTR_TENANT_COMPANY_ID: cid,
        trace_attributes.ATTR_USER_ID: uid,
        **base,
    }


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

    async def create_room(self, room_name: str, *, company_id: str, user_id: str) -> None:
        """Создаёт LiveKit комнату. Если уже существует — не ошибка."""
        async with traced_operation(
            "livekit.room.create",
            event_type="livekit.room",
            operation_category="livekit",
            billing_usage_type=UsageType.TOOL_CALL.value,
            billing_resource_name="livekit:room_create",
            billing_quantity=1,
            billing_pending_settlement=True,
            extra_attributes=_livekit_traced_attrs(
                company_id=company_id,
                user_id=user_id,
                base={
                    trace_attributes.ATTR_LIVEKIT_OPERATION: "create_room",
                    trace_attributes.ATTR_LIVEKIT_ROOM: room_name,
                },
            ),
        ):
            async with LiveKitAPI(self._api_url(), self._api_key, self._api_secret) as api:
                await api.room.create_room(CreateRoomRequest(name=room_name))

    async def delete_room(self, room_name: str, *, company_id: str, user_id: str) -> None:
        """Удаляет LiveKit комнату."""
        async with traced_operation(
            "livekit.room.delete",
            event_type="livekit.room",
            operation_category="livekit",
            extra_attributes=_livekit_traced_attrs(
                company_id=company_id,
                user_id=user_id,
                base={
                    trace_attributes.ATTR_LIVEKIT_OPERATION: "delete_room",
                    trace_attributes.ATTR_LIVEKIT_ROOM: room_name,
                },
            ),
        ):
            async with LiveKitAPI(self._api_url(), self._api_key, self._api_secret) as api:
                await api.room.delete_room(DeleteRoomRequest(room=room_name))

    async def list_egress(
        self,
        *,
        room_name: str,
        active: bool | None = None,
        api: LiveKitAPI | None = None,
    ) -> list[EgressInfo]:
        """Возвращает egress-процессы для комнаты."""
        if room_name == "":
            raise ValueError("room_name обязателен для list_egress.")
        request = ListEgressRequest(room_name=room_name)
        if active is not None:
            request.active = active
        if api is not None:
            response = await api.egress.list_egress(request)
            return list(response.items)
        async with LiveKitAPI(self._api_url(), self._api_key, self._api_secret) as inner:
            response = await inner.egress.list_egress(request)
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
        company_id: str,
        user_id: str,
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
        async with traced_operation(
            "livekit.egress.room_composite_s3",
            event_type="livekit.egress",
            operation_category="livekit_egress",
            billing_usage_type=UsageType.TOOL_CALL.value,
            billing_resource_name="livekit:egress_composite",
            billing_quantity=1,
            billing_pending_settlement=True,
            extra_attributes=_livekit_traced_attrs(
                company_id=company_id,
                user_id=user_id,
                base={
                    trace_attributes.ATTR_LIVEKIT_OPERATION: "start_room_composite_egress",
                    trace_attributes.ATTR_LIVEKIT_ROOM: room_name,
                    "platform.livekit.audio_only": audio_only,
                },
            ),
        ) as span:
            async with LiveKitAPI(self._api_url(), self._api_key, self._api_secret) as api:
                info = await api.egress.start_room_composite_egress(request)
            eid = getattr(info, "egress_id", None) or ""
            if eid:
                span.set_attribute(trace_attributes.ATTR_LIVEKIT_EGRESS_ID, eid)
            return info

    async def start_track_composite_segmented_audio_to_s3(
        self,
        *,
        room_name: str,
        audio_track_id: str,
        filepath_prefix: str,
        segment_duration_seconds: int,
        s3_access_key: str,
        s3_secret_key: str,
        s3_region: str,
        s3_bucket: str,
        company_id: str,
        user_id: str,
        s3_endpoint: str | None = None,
        api: LiveKitAPI | None = None,
    ) -> EgressInfo:
        """Сегментированный egress одного аудиотрека (микрофон) в S3 для «речи в ленту»."""
        if room_name == "":
            raise ValueError("room_name обязателен для старта track composite egress.")
        if audio_track_id == "":
            raise ValueError("audio_track_id обязателен для старта track composite egress.")
        if filepath_prefix == "":
            raise ValueError("filepath_prefix обязателен для старта track composite egress.")
        if segment_duration_seconds <= 0:
            raise ValueError("segment_duration_seconds должен быть больше 0.")
        if s3_access_key == "":
            raise ValueError("s3_access_key обязателен для старта track composite egress.")
        if s3_secret_key == "":
            raise ValueError("s3_secret_key обязателен для старта track composite egress.")
        if s3_region == "":
            raise ValueError("s3_region обязателен для старта track composite egress.")
        if s3_bucket == "":
            raise ValueError("s3_bucket обязателен для старта track composite egress.")

        s3_upload = S3Upload(
            access_key=s3_access_key,
            secret=s3_secret_key,
            region=s3_region,
            bucket=s3_bucket,
        )
        if s3_endpoint is not None and s3_endpoint != "":
            s3_upload.endpoint = s3_endpoint
            s3_upload.force_path_style = True

        segment_out = SegmentedFileOutput(
            protocol=SegmentedFileProtocol.DEFAULT_SEGMENTED_FILE_PROTOCOL,
            filename_prefix=filepath_prefix,
            segment_duration=segment_duration_seconds,
            filename_suffix=SegmentedFileSuffix.TIMESTAMP,
            s3=s3_upload,
        )
        request = TrackCompositeEgressRequest(
            room_name=room_name,
            audio_track_id=audio_track_id,
            segment_outputs=[segment_out],
            advanced=EncodingOptions(
                audio_codec=AudioCodec.AAC,
                audio_bitrate=128,
            ),
        )
        async with traced_operation(
            "livekit.egress.track_composite_segmented",
            event_type="livekit.egress",
            operation_category="livekit_egress",
            billing_usage_type=UsageType.TOOL_CALL.value,
            billing_resource_name="livekit:egress_segmented",
            billing_quantity=1,
            billing_pending_settlement=True,
            extra_attributes=_livekit_traced_attrs(
                company_id=company_id,
                user_id=user_id,
                base={
                    trace_attributes.ATTR_LIVEKIT_ROOM: room_name,
                    "platform.livekit.audio_track_id": audio_track_id,
                },
            ),
        ) as span:
            if api is not None:
                info = await api.egress.start_track_composite_egress(request)
            else:
                async with LiveKitAPI(self._api_url(), self._api_key, self._api_secret) as inner:
                    info = await inner.egress.start_track_composite_egress(request)
            eid = getattr(info, "egress_id", None) or ""
            if eid:
                span.set_attribute(trace_attributes.ATTR_LIVEKIT_EGRESS_ID, eid)
            return info

    async def stop_egress(
        self,
        *,
        egress_id: str,
        company_id: str,
        user_id: str,
        api: LiveKitAPI | None = None,
    ) -> EgressInfo:
        """Останавливает egress-процесс по id."""
        if egress_id == "":
            raise ValueError("egress_id обязателен для stop_egress.")
        request = StopEgressRequest(egress_id=egress_id)
        async with traced_operation(
            "livekit.egress.stop",
            event_type="livekit.egress",
            operation_category="livekit_egress",
            extra_attributes=_livekit_traced_attrs(
                company_id=company_id,
                user_id=user_id,
                base={trace_attributes.ATTR_LIVEKIT_EGRESS_ID: egress_id},
            ),
        ):
            if api is not None:
                return await api.egress.stop_egress(request)
            async with LiveKitAPI(self._api_url(), self._api_key, self._api_secret) as inner:
                return await inner.egress.stop_egress(request)

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
