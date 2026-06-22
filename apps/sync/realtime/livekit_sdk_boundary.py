"""Typed reads for LiveKit SDK objects at the sync realtime boundary.

LiveKit SDK отдаёт protobuf-объекты (ParticipantInfo/TrackInfo/EgressInfo). isinstance против
runtime_checkable Protocol с data-member для protobuf-дескрипторов возвращает False даже при
заполненном поле, поэтому читаем значение через hasattr-гард (строгая проверка формы: нет
атрибута -> raise) и cast к Protocol для типобезопасного доступа.
"""

from __future__ import annotations

from typing import Protocol, cast


class LiveKitEgressInfo(Protocol):
    egress_id: str


class LiveKitParticipant(Protocol):
    identity: str


class LiveKitTrack(Protocol):
    sid: str


def read_livekit_egress_id(egress_info: object) -> str:
    if not hasattr(egress_info, "egress_id"):
        raise RuntimeError("LiveKit egress_info missing egress_id")
    egress_id = cast(LiveKitEgressInfo, egress_info).egress_id
    if egress_id == "":
        raise RuntimeError("LiveKit не вернул egress_id после старта записи.")
    return egress_id


def read_livekit_participant_identity(participant: object) -> str | None:
    if not hasattr(participant, "identity"):
        raise RuntimeError("LiveKit participant missing identity")
    identity = cast(LiveKitParticipant, participant).identity
    if identity == "":
        return None
    return identity


def read_livekit_track_sid(track: object) -> str | None:
    if not hasattr(track, "sid"):
        raise RuntimeError("LiveKit track missing sid")
    track_sid = cast(LiveKitTrack, track).sid
    if track_sid == "":
        return None
    return track_sid
